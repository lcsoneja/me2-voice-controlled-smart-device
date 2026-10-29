"""A/B on the shipped recorded sessions: raw vs trimmed-to-speech.

Reads the two shipped sessions (86-take and 68-take) from the newest
Shipping/VoiceSessions_ship_* package, scores every take through every Gate 2
model twice - RAW (the file exactly as recorded) and TRIM (speech span
re-centered inside the model window with digital silence, the same pass the
live "trim to speech" option applies) - and reports per-model accuracy, the
ranking change, and which takes flip.

Writes _trim_sessions_results.json next to this script.
"""

import gc
import json
import pathlib
import re
import statistics
import sys
import time
import wave

import numpy as np

import gate1_server as gs
import oneshot_pipeline as op

HERE = pathlib.Path(__file__).resolve().parent
SHIP = HERE.parents[1] / "Shipping"
OUT = HERE / "_trim_sessions_results.json"

RFZ_ALIAS = {
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
REJECT = {"negative", "neg"}


def bag(value: object) -> str:
    parts = re.split(r"[^a-z]+", str(value or "").lower())
    return "".join(sorted(p for p in parts if p))


def same_command(a: object, b: object) -> bool:
    if not str(b or "").strip():
        return False
    left, right = bag(a), bag(b)
    return RFZ_ALIAS.get(left, left) == RFZ_ALIAS.get(right, right)


def load_wav(path: pathlib.Path) -> np.ndarray:
    try:
        with wave.open(str(path), "rb") as handle:
            width = handle.getsampwidth()
            raw = handle.readframes(handle.getnframes())
    except (OSError, wave.Error) as exc:
        raise SystemExit("cannot read " + str(path) + ": " + type(exc).__name__) from exc
    if width == 2:
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if width == 4:
        return np.frombuffer(raw, dtype=np.float32).copy()
    raise SystemExit("unsupported sample width " + str(width) + " in " + str(path))


def probs_for(name: str, runner, clip: np.ndarray) -> list[float]:
    if name in gs.GATE2_PID_CONFIGS:
        return list(runner.predict_pid_clip(clip, name))
    probs = list(runner.predict(clip))
    if name in gs.GATE2_TR_CONFIGS:
        return list(gs._gate2_tr_scores(name, probs))
    return probs


def top_intent(labels: list[str], probs: list[float]) -> str | None:
    best = None
    best_p = -1.0
    for i, p in enumerate(probs):
        try:
            value = float(p)
        except (TypeError, ValueError):
            continue
        if i >= len(labels):
            continue
        if bag(labels[i]) in REJECT:
            continue
        if value > best_p:
            best_p = value
            best = labels[i]
    return best


def load_sessions():
    """(session_label, audio_path, expected_action, phrase) for all shipped takes."""
    packages = sorted(SHIP.glob("VoiceSessions_ship_*"))
    if not packages:
        raise SystemExit("no VoiceSessions_ship_* package in " + str(SHIP))
    package = packages[-1]
    takes = []
    for sub in sorted(package.iterdir()):
        if not sub.is_dir() or not sub.name.isdigit():
            continue
        meta_path = sub / "takes.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print("SKIP " + sub.name + ": " + type(exc).__name__)
            continue
        for entry in meta:
            audio = sub / "audio" / str(entry.get("audio") or "")
            action = str(entry.get("action") or "").strip()
            if not audio.is_file() or not action:
                continue
            takes.append((sub.name, audio, action, str(entry.get("label") or "")))
    return package, takes


def main() -> int:
    package, takes = load_sessions()
    print("package=" + package.name + " takes=" + str(len(takes)))
    clips = [(label, action, phrase, load_wav(path)) for label, path, action, phrase in takes]
    names = sorted(gs.GATE2_PACKAGE_RUNNERS)
    rows = []
    flip_records: dict[str, list[dict]] = {}
    for index_no, name in enumerate(names, 1):
        try:
            if name == "gate2v124_ensemble4way":
                runner = gs.Gate2V124EnsembleRunner(name)
            else:
                runner = gs.Gate2PackageRunner(name)
        except (OSError, RuntimeError, ValueError, ImportError, KeyError, TypeError) as exc:
            print("SKIP " + name + " (" + type(exc).__name__ + ")")
            continue
        labels = list(runner.labels)
        frames = int(getattr(runner, "frames", gs.TARGET_148))
        window = max(1, frames * gs.HOP)
        raw_hits = trim_hits = seen = trimmed_ok = 0
        speech_len = []
        per_session: dict[str, list[int]] = {}
        flips = {"trim_wins": 0, "raw_wins": 0, "tie": 0}
        started = time.perf_counter()
        for session_label, action, phrase, clip in clips:
            try:
                raw_p = probs_for(name, runner, clip)
            except (RuntimeError, ValueError):
                continue
            trimmed = op._trim_to_speech(clip, gs.SR)
            if trimmed is None:
                trim_clip = clip
            else:
                speech, _ = trimmed
                speech_len.append(speech.shape[0] / gs.SR)
                trimmed_ok += 1
                if speech.shape[0] >= window:
                    trim_clip = speech[:window].copy()
                else:
                    left = (window - speech.shape[0]) // 2
                    trim_clip = np.zeros(window, dtype=speech.dtype)
                    trim_clip[left : left + speech.shape[0]] = speech
            try:
                trim_p = probs_for(name, runner, trim_clip)
            except (RuntimeError, ValueError):
                continue
            seen += 1
            r_hit = same_command(top_intent(labels, raw_p), action)
            t_hit = same_command(top_intent(labels, trim_p), action)
            raw_hits += 1 if r_hit else 0
            trim_hits += 1 if t_hit else 0
            if t_hit and not r_hit:
                flips["trim_wins"] += 1
            elif r_hit and not t_hit:
                flips["raw_wins"] += 1
            else:
                flips["tie"] += 1
            bucket = per_session.setdefault(session_label, [0, 0, 0])
            bucket[0] += 1
            bucket[1] += 1 if r_hit else 0
            bucket[2] += 1 if t_hit else 0
            if t_hit != r_hit:
                flip_records.setdefault(name, []).append(
                    {
                        "session": session_label,
                        "phrase": phrase,
                        "expected": action,
                        "raw": str(top_intent(labels, raw_p)),
                        "trim": str(top_intent(labels, trim_p)),
                        "win": "trim" if t_hit else "raw",
                    }
                )
        if seen == 0:
            continue
        raw_acc = round(100 * raw_hits / seen, 1)
        trim_acc = round(100 * trim_hits / seen, 1)
        rows.append(
            {
                "model": name,
                "raw": raw_acc,
                "trim": trim_acc,
                "delta": round(trim_acc - raw_acc, 1),
                "raw_correct": raw_hits,
                "trim_correct": trim_hits,
                "n": seen,
                "flips": flips,
                "per_session": {
                    key: {
                        "n": value[0],
                        "raw": round(100 * value[1] / value[0], 1),
                        "trim": round(100 * value[2] / value[0], 1),
                    }
                    for key, value in sorted(per_session.items())
                },
                "speech_s": round(statistics.median(speech_len), 2) if speech_len else None,
                "trimmed_ok": trimmed_ok,
                "ms": round((time.perf_counter() - started) * 1000 / max(1, seen * 2), 2),
            }
        )
        print(
            str(index_no).rjust(2)
            + "/"
            + str(len(names))
            + " "
            + name.ljust(30)
            + " raw="
            + str(raw_acc)
            + "% trim="
            + str(trim_acc)
            + "% d="
            + format(rows[-1]["delta"], "+.1f")
            + " flips="
            + str(flips["trim_wins"])
            + "/"
            + str(flips["raw_wins"])
        )
        del runner
        gc.collect()

    by_raw = sorted(rows, key=lambda r: (-r["raw"], r["model"]))
    by_trim = sorted(rows, key=lambda r: (-r["trim"], r["model"]))
    print()
    print("RANK_BY_RAW  " + ", ".join(r["model"] + "=" + str(r["raw"]) for r in by_raw[:10]))
    print("RANK_BY_TRIM " + ", ".join(r["model"] + "=" + str(r["trim"]) for r in by_trim[:10]))
    helpers = [r for r in rows if r["delta"] > 0]
    hurts = [r for r in rows if r["delta"] < 0]
    neutral = [r for r in rows if r["delta"] == 0]
    print(
        "SUMMARY models="
        + str(len(rows))
        + " trim_helps="
        + str(len(helpers))
        + " trim_hurts="
        + str(len(hurts))
        + " neutral="
        + str(len(neutral))
    )
    if rows:
        print("MEAN raw=" + str(round(statistics.mean(r["raw"] for r in rows), 1))
              + " trim=" + str(round(statistics.mean(r["trim"] for r in rows), 1)))
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "package": package.name,
        "takes": len(clips),
        "models": rows,
        "rank_by_raw": [r["model"] for r in by_raw],
        "rank_by_trim": [r["model"] for r in by_trim],
        "flips": flip_records,
    }
    try:
        OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    except OSError as exc:
        print("WRITE " + type(exc).__name__)
    print("wrote " + str(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
