"""One-shot VCM architecture: the wake word gates a SINGLE 5 s Gate 2 capture.

A deliberately simpler pipeline than the streaming dashboard:

    mic -> Gate 1 (always listening)
          -> wake word  =>  play a response, open ONE 5 s recording window (red dot)
          -> Gate 2 runs ONCE over that clip
          -> one intent, then stop until re-armed

In the full pipeline Gate 2 is scored every tick while the wake latch is open. Here Gate 2
never runs before a wake word, and after its single pass the connection sits in "done" until
an operator re-arms it.

Reused from gate1_server so behaviour matches the rest of the project:
  * Gate 1 windowing, ``_wake_candidate``, and the 2-of-3 agreement vote
  * the Gate 2 runner registry, including the PID and threshold-reject variants
  * ``_g2_candidate_intent`` (NEGATIVE is masked, so it is never reported as a command)
  * ``assistant_clip`` for the spoken acknowledgement

Window geometry matters. The shipped Gate 2 models have different native windows; V64P
needs 148 frames x hop 640 = 5.92 s, which is LONGER than the 5 s capture. Feeding the model
a segment shorter than its window makes it classify padded audio and answer NEGATIVE or STOP,
as an early test run showed. So when the native window is longer than the capture, one window
ending at the capture end is used (it covers the whole capture plus the tail of pre-wake
audio); only when the window is shorter than the capture is it slid at half-window steps.

Served at ``/oneshot.html`` (page) and ``/ws/oneshot`` (socket).
"""

from __future__ import annotations

import contextlib
import importlib
import json
import re
import time
import wave
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from aiohttp import web

HERE = Path(__file__).resolve().parent
PAGE = HERE / "gate1_web" / "oneshot.html"

CAPTURE_SECONDS = 5.0
# End-of-speech cut: end the capture when speech has been silent for the tail
# interval, but never before the minimum (a wake word alone must not be a take).
EOS_MIN_SECONDS = 0.8
EOS_TAIL_SECONDS = 0.7
EOS_SPEECH_FLOOR = 0.02
G1_TICK_SECONDS = 0.5
G1_VOTES = 3
G1_VOTES_NEEDED = 2
G2_STEP_FRACTION = 0.5
WAKE_SLUG = "wake"
MEMORY_SECONDS = 30.0
# Measured-best first: v3_f32 wake 94.2% vs v12 79.1% on the identical 206-take set.
G1_PREFERENCE = (
    "gate1v3_f32",
    "gate1v3_f16",
    "gate1v12_f16",
    "gate1v8_f32",
    "gate1v8_f16",
)
G2_PREFERENCE = ("gate2v64p_paired_owner", "gate2v64d_expandedneg", "gate2v56_v54")


def register_routes(app: web.Application) -> None:
    """Attach the one-shot page and socket without disturbing existing routes."""
    app.router.add_get("/oneshot.html", page)
    app.router.add_get("/ws/oneshot", ws_oneshot)
    app.router.add_get("/api/oneshot/recordings", api_recordings)
    app.router.add_post("/api/oneshot/recordings/score", api_recordings_score)
    app.router.add_post("/api/oneshot/recordings/delete", api_recordings_delete)
    app.router.add_get("/api/oneshot/recordings/audio", api_recordings_audio)
    app.router.add_post("/api/oneshot/recordings/tag", api_recordings_tag)
    app.router.add_get("/api/oneshot/sessions", api_sessions)
    app.router.add_post("/api/oneshot/sessions", api_sessions_new)
    app.router.add_post("/api/oneshot/results/export", api_results_export)
    app.router.add_post("/api/oneshot/results/save", api_results_save)
    app.router.add_get("/api/oneshot/leaderboard", api_leaderboard)
    app.router.add_post("/api/oneshot/leaderboard/score", api_leaderboard_score)
    app.router.add_post("/api/oneshot/leaderboard/reset", api_leaderboard_reset)


# Recordings lab for this page: score saved takes against every Gate 2 model, and delete takes.
# The holdout clips the ranking benchmark measures (me2h*) are never deleted from here.
MAX_SCORE_RECORDINGS = 12
HOLDOUT_PREFIX = "me2h"

# Shipped models use compact class names (lightson) while take labels use underscored ones
# (LIGHT_ON). bag() ignores word order and separators, and the map covers the rest, so a correct
# hit is never reported as a miss.
_INTENT_ALIASES = {
    "settimer": "timer",
    "alarmset": "alarm",
    "tempup": "temperature",
    "tempdown": "temperature",
    "lightsdim": "brightness",
    "lightsbright": "brightness",
    "lightson": "lighton",
    "lightsoff": "lightoff",
    "reminderset": "createreminder",
    "remindercheck": "listreminders",
    "checkreminders": "listreminders",
    "mediaplay": "playmusic",
    "mediapause": "pause",
    "medianext": "next",
    "silence": "stop",
}


def _bag(value: Any) -> str:
    parts = [p for p in re.split(r"[^a-z]+", str(value or "").lower()) if p]
    return "".join(sorted(parts))


def _same_command(predicted: Any, expected: Any) -> bool:
    if not str(expected or "").strip():
        return False
    left, right = _bag(predicted), _bag(expected)
    return _INTENT_ALIASES.get(left, left) == _INTENT_ALIASES.get(right, right)


def _load_clip(path: Path) -> np.ndarray:
    """16 kHz mono WAV as float32, exactly what the runners expect."""
    with wave.open(str(path), "rb") as handle:
        width = handle.getsampwidth()
        raw = handle.readframes(handle.getnframes())
    if width == 2:
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if width == 4:
        return np.frombuffer(raw, dtype=np.float32).copy()
    raise RuntimeError("unsupported sample width " + str(width))


def _recording_rows(store: Any) -> list[dict[str, Any]]:
    """Saved takes, newest first, with the holdout clips flagged."""
    rows = []
    for entry in store.list():
        rec_id = str(entry.get("id") or "")
        rows.append(
            {
                "id": rec_id,
                "file": str(entry.get("file") or ""),
                "session": str(entry.get("session") or ""),
                "label": entry.get("label") or "",
                "action": str(entry.get("action") or ""),
                "wake_word": entry.get("wake_word") or "",
                "duration_s": entry.get("duration_s"),
                "created": str(entry.get("created") or ""),
                "holdout": rec_id.startswith(HOLDOUT_PREFIX),
            }
        )
    rows.sort(key=lambda row: row["created"], reverse=True)
    return rows


async def api_recordings(request: web.Request) -> web.Response:
    """Takes for the recordings pane."""
    rows = _recording_rows(request.app["lab"].store)
    return web.json_response({"recordings": rows, "count": len(rows)})


async def api_recordings_delete(request: web.Request) -> web.Response:
    """Move takes to the trash folder by id, or every take with {"all": true}.

    Nothing the user recorded is hard-deleted: the wav moves to a dated
    recordings/_trash_* folder and the entry stays in trash_manifest.json, so a
    take can always be replayed after new models arrive. Holdout clips are
    refused: the Gate 2 ranking is measured on them.
    """
    store = request.app["lab"].store
    try:
        body = await request.json()
    except (TypeError, ValueError):
        body = {}
    if not isinstance(body, dict):
        body = {}
    wanted = (
        [str(i) for i in body.get("ids") or []]
        if isinstance(body.get("ids"), list)
        else []
    )
    if body.get("all"):
        wanted = [row["id"] for row in _recording_rows(store)]
    outcome = store.trash_takes(wanted)
    return web.json_response(
        {
            "deleted": outcome["moved"],
            "refused_holdout": outcome["refused"],
            "missing": outcome["missing"],
            "trashed_to": outcome["trash_dir"],
            "remaining": len(_recording_rows(store)),
        }
    )


async def api_recordings_score(request: web.Request) -> web.Response:
    """Score takes against Gate 2 models: one row per take, one result per model.

    Body: {"ids": "all" | [...], "models": "all" | [...]}. Returns the matrix plus a per-model
    summary; both the batch button and the per-recording view read the same response.
    """
    gs = importlib.import_module("gate1_server")
    gates = request.app["gates"]
    store = request.app["lab"].store
    try:
        body = await request.json()
    except (TypeError, ValueError):
        body = {}
    if not isinstance(body, dict):
        body = {}

    labelled = [row for row in _recording_rows(store) if row["action"].strip()]
    by_id = {row["id"]: row for row in labelled}
    wanted = body.get("ids")
    if isinstance(wanted, str) and wanted == "all":
        selected = labelled
    elif isinstance(wanted, list) and wanted:
        selected = [by_id[str(i)] for i in wanted if str(i) in by_id]
    else:
        selected = labelled[:MAX_SCORE_RECORDINGS]
    capped = len(selected) > MAX_SCORE_RECORDINGS
    selected = selected[:MAX_SCORE_RECORDINGS]

    requested = body.get("models")
    known = sorted(gs.GATE2_PACKAGE_RUNNERS)
    models = (
        known
        if (not requested or requested == "all")
        else [str(name) for name in requested if str(name) in known]
    )
    if not selected:
        return web.json_response({"error": "no takes with an intent label"}, status=400)
    if not models:
        return web.json_response(
            {"error": "no known Gate 2 models requested"}, status=400
        )

    takes, tally = _score_matrix(gs, gates, store, selected, models)
    summary = _summary_rows(models, tally)
    return web.json_response(
        {
            "takes": takes,
            "summary": summary,
            "capped": capped,
            "limit": MAX_SCORE_RECORDINGS,
        }
    )


LEADERBOARD_NAME = "leaderboard.json"


def _leaderboard_path(store: Any) -> Path:
    return Path(store.root) / LEADERBOARD_NAME


def _load_board(store: Any) -> tuple[int, dict[str, dict[str, Any]]]:
    """The stored board as (epoch, models); a bare models dict is an older file."""
    try:
        data = json.loads(_leaderboard_path(store).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0, {}
    if isinstance(data, dict) and isinstance(data.get("models"), dict):
        return int(data.get("epoch", 0)), data["models"]
    return 0, (data if isinstance(data, dict) else {})


def _save_board(store: Any, epoch: int, models: dict[str, dict[str, Any]]) -> None:
    # Best effort: a read-only recordings folder must not break scoring.
    with contextlib.suppress(OSError):
        payload = {"epoch": epoch, "models": models}
        _leaderboard_path(store).write_text(
            json.dumps(payload, indent=1), encoding="utf-8"
        )


def _leaderboard_rows(board: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Running ranking: highest accuracy first, then the most evidence, then name."""
    rows = [
        {
            "model": name,
            "correct": int(entry.get("correct", 0)),
            "scored": int(entry.get("scored", 0)),
            "runs": int(entry.get("runs", 0)),
            "acc": round(int(entry.get("correct", 0)) / int(entry["scored"]), 4)
            if int(entry.get("scored", 0))
            else None,
        }
        for name, entry in board.items()
    ]
    rows.sort(key=lambda row: (-(row["acc"] or 0.0), -row["scored"], row["model"]))
    return rows


def _score_matrix(
    gs, gates, store: Any, selected: list, models: list
) -> tuple[list, dict]:
    """Run every selected take through every model: one row per take, one result per model."""
    takes = []
    tally: dict[str, list[int]] = {name: [0, 0] for name in models}
    for take in selected:
        # Resolve against the recordings folder and reject anything that escapes it: the index is
        # a file on disk, so a bad entry must not turn into reading an arbitrary path.
        candidate = (store.root / take["file"]).resolve()
        try:
            candidate.relative_to(store.root.resolve())
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        clip = _load_clip(candidate)
        results = []
        for name in models:
            runner = _load_runner(gs, gates, name)
            probs = _gate2_probs(gs, gates, name, runner, clip)
            intent, conf = gs._g2_candidate_intent(probs, list(runner.labels), {}, 0.0)
            hit = _same_command(intent, take["action"])
            if conf is not None and np.isfinite(conf):
                tally[name][1] += 1
                tally[name][0] += 1 if hit else 0
            results.append(
                {
                    "model": name,
                    "intent": str(intent or ""),
                    "conf": None
                    if conf is None or not np.isfinite(conf)
                    else round(float(conf), 4),
                    "match": bool(hit),
                }
            )
        takes.append({**take, "results": results})
    return takes, tally


def _summary_rows(models: list, tally: dict) -> list[dict[str, Any]]:
    rows = [
        {
            "model": name,
            "correct": tally[name][0],
            "scored": tally[name][1],
            "acc": round(tally[name][0] / tally[name][1], 4)
            if tally[name][1]
            else None,
        }
        for name in models
    ]
    rows.sort(key=lambda row: (-(row["acc"] or 0.0), row["model"]))
    return rows


def _selection(gs, store: Any, body: dict) -> tuple[list, list, bool]:
    """Takes and models requested by a body, honouring the per-run cap."""
    labelled = [row for row in _recording_rows(store) if row["action"].strip()]
    by_id = {row["id"]: row for row in labelled}
    wanted = body.get("ids")
    if isinstance(wanted, str) and wanted == "all":
        selected = labelled
    elif isinstance(wanted, list) and wanted:
        selected = [by_id[str(i)] for i in wanted if str(i) in by_id]
    else:
        selected = labelled[:MAX_SCORE_RECORDINGS]
    capped = len(selected) > MAX_SCORE_RECORDINGS
    selected = selected[:MAX_SCORE_RECORDINGS]

    requested = body.get("models")
    known = sorted(gs.GATE2_PACKAGE_RUNNERS)
    models = (
        known
        if (not requested or requested == "all")
        else [str(name) for name in requested if str(name) in known]
    )
    return selected, models, capped


async def api_leaderboard(request: web.Request) -> web.Response:
    """The running ranking accumulated across scoring runs."""
    _, models = _load_board(request.app["lab"].store)
    rows = _leaderboard_rows(models)
    return web.json_response({"ranking": rows, "models": len(rows)})


async def api_leaderboard_reset(request: web.Request) -> web.Response:
    """Forget the accumulated ranking and start a fresh comparison."""
    epoch, _ = _load_board(request.app["lab"].store)
    _save_board(request.app["lab"].store, epoch + 1, {})
    return web.json_response({"ranking": [], "models": 0, "epoch": epoch + 1})


async def api_leaderboard_score(request: web.Request) -> web.Response:
    """Score takes and fold the outcome into the running ranking.

    Body: {"ids": "all" | [...], "models": "all" | [...], "reset": bool}. Passing a single
    model name scores just that one (the Setup pane's choice), "all" scores every registered one.
    """
    gs = importlib.import_module("gate1_server")
    gates = request.app["gates"]
    store = request.app["lab"].store
    try:
        body = await request.json()
    except (TypeError, ValueError):
        body = {}
    if not isinstance(body, dict):
        body = {}

    selected, models, capped = _selection(gs, store, body)
    if not selected:
        return web.json_response({"error": "no takes with an intent label"}, status=400)
    if not models:
        return web.json_response(
            {"error": "no known Gate 2 models requested"}, status=400
        )

    epoch, board = _load_board(store)
    if body.get("reset"):
        epoch += 1
        board = {}
        _save_board(store, epoch, {})
    takes, tally = _score_matrix(gs, gates, store, selected, models)
    for name in models:
        entry = board.setdefault(name, {"correct": 0, "scored": 0, "runs": 0})
        entry["correct"] = int(entry.get("correct", 0)) + tally[name][0]
        entry["scored"] = int(entry.get("scored", 0)) + tally[name][1]
        entry["runs"] = int(entry.get("runs", 0)) + (1 if tally[name][1] else 0)
    # A reset during the round must win: if the epoch moved while scoring, drop this result
    # instead of writing stale tallies over the cleared board.
    epoch_now, _ = _load_board(store)
    if epoch_now != epoch:
        return web.json_response(
            {
                "takes": takes,
                "summary": _summary_rows(models, tally),
                "ranking": [],
                "reset_detected": True,
                "capped": capped,
                "limit": MAX_SCORE_RECORDINGS,
            }
        )
    _save_board(store, epoch, board)
    return web.json_response(
        {
            "takes": takes,
            "summary": _summary_rows(models, tally),
            "ranking": _leaderboard_rows(board),
            "capped": capped,
            "limit": MAX_SCORE_RECORDINGS,
        }
    )


async def api_recordings_audio(request: web.Request) -> web.FileResponse | web.Response:
    """The WAV of one take, so a saved trial can be played back from its row."""
    entry = request.app["lab"].store.get(request.query.get("id", ""))
    if entry is None:
        raise web.HTTPNotFound(text="no such recording")
    path = request.app["lab"].store.path_of(entry)
    if not path.is_file():
        raise web.HTTPNotFound(text="audio file missing")
    return web.FileResponse(path)


async def api_recordings_tag(request: web.Request) -> web.Response:
    """Re-tag a take after the fact: its intent (action), optionally its label too.

    This is how a trial recorded against the wrong phrase gets corrected without re-recording.
    """
    try:
        body = await request.json()
    except (TypeError, ValueError):
        body = {}
    if not isinstance(body, dict):
        body = {}
    rec_id = str(body.get("id") or "")
    action = str(body.get("action") or "").strip()
    label = str(body.get("label") or "").strip()
    if not rec_id:
        return web.json_response({"error": "id required"}, status=400)
    store = request.app["lab"].store
    if store.get(rec_id) is None:
        return web.json_response({"error": "no such recording"}, status=404)
    meta: dict[str, Any] = {"action": action} if action else {}
    store.update(rec_id, label=label or None, meta=meta or None)
    updated = store.get(rec_id) or {}
    return web.json_response(
        {"id": rec_id, "action": updated.get("action"), "label": updated.get("label")}
    )


async def api_sessions(request: web.Request) -> web.Response:
    store = request.app["lab"].store
    return web.json_response({"sessions": store.list_sessions()})


async def api_sessions_new(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except (TypeError, ValueError):
        body = {}
    label = str((body or {}).get("label") or "") if isinstance(body, dict) else ""
    store = request.app["lab"].store
    return web.json_response({"session": store.create_session(label)})


def _results_matrix(request: web.Request, body: dict) -> dict:
    """Score the requested takes across the requested models: rows + tallies."""
    gs = importlib.import_module("gate1_server")
    gates = request.app["gates"]
    store = request.app["lab"].store
    selected, models, capped = _selection(gs, store, body)
    if not selected or not models:
        raise web.HTTPBadRequest(text="no scoreable takes or models")
    takes, tally = _score_matrix(gs, gates, store, selected, models)
    return {
        "takes": takes,
        "summary": _summary_rows(models, tally),
        "capped": capped,
        "limit": MAX_SCORE_RECORDINGS,
    }


async def _write_results(
    request: web.Request, body: dict, kind: str
) -> tuple[str, dict]:
    """Score and persist a results artifact under recordings/exports/."""
    payload = _results_matrix(request, body)
    store = request.app["lab"].store
    stamp = time.strftime("%Y%m%d_%H%M%S")
    # The test-all flow saves the report straight into the session's own folder
    # (one folder per run: audio + metadata + results together, the standard ML
    # experiment layout); the plain Save/Export buttons use the shared exports/.
    prefix = kind + "_" + stamp if kind == "export" else "report_" + stamp
    if str(body.get("folder") or "") == "auto":
        sessions = {
            str(t.get("session") or "") for t in payload["takes"] if t.get("session")
        }
        if len(sessions) == 1:
            target_dir = store.sessions_dir / next(iter(sessions))
        else:
            target_dir = store.root / "exports"
    else:
        target_dir = store.root / "exports"
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = prefix + (".csv" if kind == "export" else ".json")
    relative = (target_dir.relative_to(store.root) / fname).as_posix()
    target = target_dir / fname
    if kind == "export":
        import csv as csv_module
        from io import StringIO

        buffer = StringIO()
        writer = csv_module.writer(buffer)
        writer.writerow(
            [
                "take_id",
                "created",
                "session",
                "label",
                "expected_action",
                "model",
                "predicted_intent",
                "probability",
                "match",
                "duration_s",
            ]
        )
        for take in payload["takes"]:
            for result in take["results"]:
                writer.writerow(
                    [
                        take.get("id", ""),
                        take.get("created", ""),
                        take.get("session", ""),
                        take.get("label", ""),
                        take.get("action", ""),
                        result["model"],
                        result["intent"],
                        result["conf"],
                        "1" if result["match"] else "0",
                        take.get("duration_s", ""),
                    ]
                )
        try:
            target.write_text(buffer.getvalue(), encoding="utf-8")
        except OSError as exc:
            raise web.HTTPInternalServerError(
                text="cannot write " + str(relative)
            ) from exc
        return relative, {
            **payload,
            "path": relative,
            "rows": len(payload["takes"]) * len(payload["summary"]),
            "csv": buffer.getvalue(),
        }
    data = {
        "exported_at": stamp,
        "sessions": sorted({str(t.get("session") or "") for t in payload["takes"]}),
        **{key: payload[key] for key in ("takes", "summary", "capped", "limit")},
    }
    try:
        target.write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except OSError as exc:
        raise web.HTTPInternalServerError(text="cannot write " + str(relative)) from exc
    return relative, {
        "path": relative,
        "take_count": len(data["takes"]),
        "models": len(data["summary"]),
        "rows": len(data["takes"]) * len(data["summary"]),
        "sessions": data["sessions"],
        "takes": data["takes"],
        "summary": data["summary"],
    }


async def api_results_export(request: web.Request) -> web.Response:
    """Score selected takes across every model, write a CSV, return its path and text."""
    try:
        body = await request.json()
    except (TypeError, ValueError):
        body = {}
    if not isinstance(body, dict):
        body = {}
    _relative, payload = await _write_results(request, body, "export")
    return web.json_response(payload)


async def api_results_save(request: web.Request) -> web.Response:
    """Score selected takes across every model and save the full matrix as JSON."""
    try:
        body = await request.json()
    except (TypeError, ValueError):
        body = {}
    if not isinstance(body, dict):
        body = {}
    _relative, payload = await _write_results(request, body, "results")
    return web.json_response(payload)


async def page(_request: web.Request) -> web.FileResponse:
    if not PAGE.is_file():
        raise web.HTTPNotFound(text="oneshot.html is missing from gate1_web/")
    return web.FileResponse(PAGE)


def _load_runner(gs, gates, name: str) -> Any:
    """Runner for ``name``, sharing instances the server already loaded.

    The model is chosen per connection so an experiment here never mutates the shared
    ``gates.gate2_runner`` that the streaming dashboard is using.
    """
    runner = gates._gate2_extra.get(name)
    if runner is None:
        if name == "gate2v124_ensemble4way":
            runner = gs.Gate2V124EnsembleRunner(name)
        else:
            runner = gs.Gate2PackageRunner(name)
        gates._gate2_extra[name] = runner
    return runner


def _gate2_probs(gs, gates, name: str, runner: Any, segment: np.ndarray) -> list[float]:
    """Gate 2 probabilities for one segment, dispatching like the streaming server."""
    if name in gs.GATE2_PID_CONFIGS:
        return list(runner.predict_pid_clip(segment, name))
    probs = list(runner.predict(segment))
    if name in gs.GATE2_TR_CONFIGS:
        return list(gs._gate2_tr_scores(name, probs))
    return probs


def _decide(
    gs, gates, name: str, runner: Any, thresholds: dict[str, Any], segment: np.ndarray
):
    """One candidate intent for one model window, or None when it rejects."""
    probs = _gate2_probs(gs, gates, name, runner, segment)
    intent, conf = gs._g2_candidate_intent(
        probs, gates.gate2_labels(), thresholds["g2thr"], thresholds["gate2MinConf"]
    )
    if not intent or not np.isfinite(conf):
        return None
    return {
        "intent": str(intent),
        "conf": float(conf),
        "top1": float(np.max(np.asarray(probs, dtype=float))),
    }


def _classify_capture(
    gs, gates, name: str, clip: np.ndarray, pre: np.ndarray, thresholds: dict[str, Any]
):
    """ONE decision from the capture.

    ``clip`` is the 5 s capture; ``pre`` is the audio immediately before it, used when the
    model's native window is longer than the capture. NEGATIVE is masked by
    ``_g2_candidate_intent``, so a rejection can never be reported as a command.
    """
    runner = _load_runner(gs, gates, name)
    frames = int(getattr(runner, "frames", gs.TARGET_148))
    window = max(1, frames * gs.HOP)
    if window >= clip.shape[0]:
        # Native window at least as long as the capture: one window ending at the capture
        # end. Sliding inside a shorter clip would feed the model mostly padding.
        needed = window - clip.shape[0]
        tail = (
            pre[-needed:] if needed and pre.shape[0] else np.zeros(0, dtype=clip.dtype)
        )
        segment = np.concatenate((tail, clip))
        if segment.shape[0] < window:
            segment = np.concatenate(
                (np.zeros(window - segment.shape[0], dtype=clip.dtype), segment)
            )
        best = _decide(gs, gates, name, runner, thresholds, segment[-window:])
        if best is not None:
            best["at_s"] = 0.0
        return best, 1, name

    step = max(1, int(window * G2_STEP_FRACTION))
    best = None
    scored = 0
    start = 0
    while start + window <= clip.shape[0]:
        found = _decide(
            gs, gates, name, runner, thresholds, clip[start : start + window]
        )
        scored += 1
        if found is not None and (best is None or found["conf"] > best["conf"]):
            found["at_s"] = round(start / gs.SR, 2)
            best = found
        start += step
    return best, scored, name


async def ws_oneshot(request: web.Request) -> web.WebSocketResponse:
    gs = importlib.import_module("gate1_server")
    gates = request.app["gates"]
    store = request.app["lab"].store
    ws = web.WebSocketResponse(max_msg_size=16 * 1024 * 1024)
    await ws.prepare(request)

    # Prefer the measured-best wake model for this page. gate1v12 (the deck headline) was
    # measured at 79.1% wake on the same takes where gate1v3_f32 reached 94.2%, so v3 is the
    # default here; the page can still switch models per connection.
    g1_model = next(
        (m for m in G1_PREFERENCE if m in gates.g1_variants), gs.DEFAULT_G1_MODEL
    )

    thresholds: dict[str, Any] = {
        "Nova": 0.5,
        "Piattos": 0.5,
        "gate2MinConf": 0.5,
        "g2thr": {},
    }
    gate2_name = next(
        (m for m in G2_PREFERENCE if m in gs.GATE2_PACKAGE_RUNNERS),
        gates.gate2_active_model(),
    )
    window_samples = int(gs.WIN_SAMPLES)
    tick_samples = int(G1_TICK_SECONDS * gs.SR)
    capture_samples = int(CAPTURE_SECONDS * gs.SR)
    max_samples = int(MEMORY_SECONDS * gs.SR)

    buf = np.zeros(0, dtype=np.float32)
    base = 0
    total = 0
    last_g1_at = 0
    ambient: deque[float] = deque(maxlen=64)
    recent: deque[str | None] = deque(maxlen=G1_VOTES)
    state = "idle"
    capture_from = 0
    shots = 0
    arm_intent = ""
    arm_phrase = ""
    current_session = ""
    nc_enabled = False
    nc: dict[str, Any] = {"enabled": False}
    eos_enabled = False
    eos_capture_end: int | None = None
    speech_last = 0
    last_floor = 0.0

    async def send(obj: dict[str, Any]) -> None:
        try:
            await ws.send_json(obj)
        except (ConnectionResetError, RuntimeError):
            pass

    await send(
        {
            "type": "hello",
            "mode": "oneshot",
            "state": state,
            "capture_seconds": CAPTURE_SECONDS,
            "g1_model": g1_model,
            "g1_order": list(G1_PREFERENCE),
            "gate2_model": gate2_name,
            "g1_tick_seconds": G1_TICK_SECONDS,
            "sessions": store.list_sessions(),
        }
    )

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            import json

            try:
                data = json.loads(msg.data)
            except (TypeError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            kind = str(data.get("type") or "")
            if kind == "session_use":
                requested = str(data.get("id") or "")
                session_meta = store.session(requested)
                if session_meta is None:
                    await send(
                        {
                            "type": "session",
                            "session": "",
                            "label": "",
                            "phrase_pointer": 0,
                            "error": "unknown session",
                        }
                    )
                else:
                    current_session = requested
                    await send(
                        {
                            "type": "session",
                            "session": requested,
                            "label": str(session_meta.get("label") or ""),
                            "phrase_pointer": int(
                                session_meta.get("phrase_pointer") or 0
                            ),
                        }
                    )
            elif kind == "session_new":
                session_meta = store.create_session(str(data.get("label") or ""))
                current_session = str(session_meta.get("id") or "")
                await send(
                    {
                        "type": "session",
                        "session": current_session,
                        "label": str(session_meta.get("label") or ""),
                        "phrase_pointer": 0,
                        "created": True,
                    }
                )
            elif kind == "phrase_state":
                if current_session:
                    store.set_session_phrases(current_session, data.get("pointer", 0))
            elif kind == "options":
                nc_enabled = bool(data.get("nc", False))
                eos_enabled = bool(data.get("eos", False))
                if nc_enabled:
                    nc["enabled"] = True
                else:
                    nc.clear()
                    nc["enabled"] = False
                await send({"type": "options", "nc": nc_enabled, "eos": eos_enabled})
            elif kind == "arm" and state != "recording":
                state = "armed"
                recent.clear()
                last_g1_at = total
                # The page says which phrase it expects; the capture is saved under it so the
                # take is scoreable and the trial list can replay or re-tag it.
                arm_intent = str(data.get("intent") or "").strip()
                arm_phrase = str(data.get("phrase") or "").strip()
                eos_capture_end = None
                speech_last = 0
                if not current_session:
                    session_meta = store.create_session("auto")
                    current_session = str(session_meta.get("id") or "")
                    await send(
                        {
                            "type": "session",
                            "session": current_session,
                            "label": str(session_meta.get("label") or ""),
                            "phrase_pointer": 0,
                            "created": True,
                        }
                    )
                await send({"type": "state", "state": state})
            elif kind == "disarm" and state != "recording":
                state = "idle"
                await send({"type": "state", "state": state})
            elif kind == "g1_model" and state != "recording":
                requested = str(data.get("model") or "")
                if requested in gates.g1_variants:
                    g1_model = requested
                    recent.clear()
                    await send({"type": "model", "g1_model": g1_model})
                else:
                    await send(
                        {"type": "error", "text": "unknown g1 model " + requested}
                    )
            elif kind == "gate2_model" and state != "recording":
                requested = str(data.get("model") or "")
                if requested in gs.GATE2_PACKAGE_RUNNERS:
                    try:
                        _load_runner(gs, gates, requested)
                    except (OSError, RuntimeError, ValueError):
                        await send(
                            {"type": "error", "text": "cannot load " + requested}
                        )
                    else:
                        gate2_name = requested
                        await send({"type": "model", "gate2_model": gate2_name})
            continue

        if msg.type != web.WSMsgType.BINARY:
            continue
        chunk = np.frombuffer(msg.data, dtype=np.float32)
        if chunk.size == 0:
            continue
        buf = np.concatenate((buf, chunk)) if buf.size else chunk.copy()
        total += chunk.size
        if buf.size > max_samples:
            trim = buf.size - max_samples
            buf = buf[trim:]
            base += trim

        # While recording: keep the noise profile fresh and watch for the end of
        # speech so the capture can be cut early instead of always holding 5 s.
        if state == "recording":
            if nc_enabled:
                gs._nc_noise_update(chunk, nc)
            if eos_enabled and eos_capture_end is None:
                tail = chunk if chunk.size >= 800 else buf[-min(buf.size, 800) :]
                tail_rms = gs._level_rms(tail)
                speech_floor = max(last_floor * 2.0 + 1e-4, EOS_SPEECH_FLOOR)
                if tail_rms > speech_floor:
                    speech_last = total
                elif total - capture_from >= int(
                    EOS_MIN_SECONDS * gs.SR
                ) and total - speech_last >= int(EOS_TAIL_SECONDS * gs.SR):
                    eos_capture_end = total - int(EOS_TAIL_SECONDS * gs.SR)
                    await send(
                        {
                            "type": "eos",
                            "capture_seconds": round(
                                max(0, eos_capture_end - capture_from) / gs.SR, 2
                            ),
                        }
                    )

        # Gate 1 listens only while armed, so a capture always starts from a fresh wake word.
        while (
            state == "armed"
            and buf.size >= window_samples
            and total - last_g1_at >= tick_samples
        ):
            last_g1_at = total
            win = buf[-window_samples:]
            wrms = gs._level_rms(win)
            floor = gs._track_ambient(ambient, wrms)
            last_floor = float(floor)
            if nc_enabled:
                # Same canceller the streaming dashboard and the replay use: learn from
                # the raw window, clean the inference window only.
                gs._nc_noise_update(win, nc)
                win = gs._nc_apply(win, nc)
            probs, _labels, _two = gates.infer_g1_variant(g1_model, win)
            wake = gs._wake_candidate(probs, thresholds, wrms, floor)
            recent.append(wake)
            votes = sum(1 for w in recent if w is not None and w == wake)
            await send(
                {
                    "type": "g1",
                    "wake": wake,
                    "votes": votes,
                    "nova": float(probs[0]) if len(probs) > 0 else None,
                    "piattos": float(probs[1]) if len(probs) > 1 else None,
                    "rms": round(float(wrms), 5),
                    "floor": round(float(floor), 5),
                }
            )
            if wake and votes >= G1_VOTES_NEEDED:
                state = "recording"
                capture_from = total
                shots += 1
                clip_info = gs.assistant_clip(wake.lower(), WAKE_SLUG) or {}
                await send(
                    {
                        "type": "wake",
                        "persona": wake,
                        "text": clip_info.get("text", ""),
                        "response_url": clip_info.get("url"),
                        "state": state,
                        "capture_seconds": CAPTURE_SECONDS,
                        "shot": shots,
                    }
                )
                break

        # The single Gate 2 pass runs once the window is complete: 5 s by default,
        # or sooner when the end-of-speech option cut the capture early.
        if state == "recording" and (
            eos_capture_end is not None or total - capture_from >= capture_samples
        ):
            lo = capture_from - base
            if eos_capture_end is not None:
                clip_len = eos_capture_end - capture_from
            else:
                clip_len = capture_samples
            hi = lo + clip_len
            if hi > len(buf):
                hi = len(buf)
                clip_len = max(0, hi - lo)
            clip = buf[lo:hi].copy()
            pre = buf[:lo].copy()
            if nc_enabled and nc.get("profile") is not None:
                clip = gs._nc_apply(clip, nc)
                pre = gs._nc_apply(pre, nc)
            eos_capture_end = None
            speech_last = 0
            started = time.perf_counter()
            best, scored, model_name = _classify_capture(
                gs, gates, gate2_name, clip, pre, thresholds
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            # Every capture becomes a take: the trial list, playback, re-tagging and the
            # background scoreboard all work off the saved clip.
            label = arm_phrase or ("free test shot " + str(shots))
            meta = {"action": arm_intent} if arm_intent else None
            take_id = ""
            try:
                saved = store.save(
                    clip, label=label, meta=meta, session=current_session or None
                )
                take_id = str(saved.get("id") or "")
            except (OSError, ValueError, KeyError):
                take_id = ""
            if take_id:
                verdict = {
                    "intent": str(best["intent"]) if best else "NEGATIVE",
                    "conf": round(float(best["conf"]), 4)
                    if best and best["conf"] is not None and np.isfinite(best["conf"])
                    else None,
                    "match": bool(
                        best
                        and best["intent"]
                        and arm_intent
                        and str(best["intent"]) == arm_intent
                    ),
                }
                try:
                    store.update(take_id, meta={"verdict": verdict})
                except (OSError, ValueError, KeyError):
                    pass
            state = "done"
            await send(
                {
                    "type": "intent",
                    "state": state,
                    "shot": shots,
                    "take_id": take_id,
                    "intent": best["intent"] if best else None,
                    "conf": best["conf"] if best else None,
                    "top1": best["top1"] if best else None,
                    "at_s": best["at_s"] if best else None,
                    "windows_scored": scored,
                    "gate2_model": model_name,
                    "latency_ms": round(latency_ms, 1),
                    "capture_seconds": round(clip.size / gs.SR, 2),
                    "eos": clip.size < capture_samples,
                    "session": current_session,
                }
            )

    return ws
