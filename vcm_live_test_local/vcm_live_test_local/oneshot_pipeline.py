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

import importlib
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
    """Delete takes by id, or every take with {"all": true}.

    Holdout clips are refused rather than deleted: the Gate 2 ranking is measured on them.
    """
    store = request.app["lab"].store
    try:
        body = await request.json()
    except (TypeError, ValueError):
        body = {}
    if not isinstance(body, dict):
        body = {}
    wanted = [str(i) for i in body.get("ids") or []] if isinstance(body.get("ids"), list) else []
    if body.get("all"):
        wanted = [row["id"] for row in _recording_rows(store)]
    deleted: list[str] = []
    refused: list[str] = []
    missing: list[str] = []
    for rec_id in wanted:
        if rec_id.startswith(HOLDOUT_PREFIX):
            refused.append(rec_id)
        elif store.delete(rec_id):
            deleted.append(rec_id)
        else:
            missing.append(rec_id)
    return web.json_response(
        {
            "deleted": deleted,
            "refused_holdout": refused,
            "missing": missing,
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
        return web.json_response({"error": "no known Gate 2 models requested"}, status=400)

    takes = []
    tally: dict[str, list[int]] = {name: [0, 0] for name in models}
    for take in selected:
        # Resolve against the recordings folder and reject anything that escapes it: the index
        # is a file on disk, so a bad entry must not turn into reading an arbitrary path.
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
                    "conf": None if conf is None or not np.isfinite(conf) else round(float(conf), 4),
                    "match": bool(hit),
                }
            )
        takes.append({**take, "results": results})

    summary = [
        {
            "model": name,
            "correct": tally[name][0],
            "scored": tally[name][1],
            "acc": round(tally[name][0] / tally[name][1], 4) if tally[name][1] else None,
        }
        for name in models
    ]
    summary.sort(key=lambda row: (-(row["acc"] or 0.0), row["model"]))
    return web.json_response(
        {"takes": takes, "summary": summary, "capped": capped, "limit": MAX_SCORE_RECORDINGS}
    )


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
            if kind == "arm" and state != "recording":
                state = "armed"
                recent.clear()
                last_g1_at = total
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

        # The single Gate 2 pass runs once the 5 s window is complete.
        if state == "recording" and total - capture_from >= capture_samples:
            lo = capture_from - base
            hi = lo + capture_samples
            clip = buf[lo:hi].copy()
            pre = buf[:lo].copy()
            started = time.perf_counter()
            best, scored, model_name = _classify_capture(
                gs, gates, gate2_name, clip, pre, thresholds
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            state = "done"
            await send(
                {
                    "type": "intent",
                    "state": state,
                    "shot": shots,
                    "intent": best["intent"] if best else None,
                    "conf": best["conf"] if best else None,
                    "top1": best["top1"] if best else None,
                    "at_s": best["at_s"] if best else None,
                    "windows_scored": scored,
                    "gate2_model": model_name,
                    "latency_ms": round(latency_ms, 1),
                    "capture_seconds": round(clip.size / gs.SR, 2),
                }
            )

    return ws
