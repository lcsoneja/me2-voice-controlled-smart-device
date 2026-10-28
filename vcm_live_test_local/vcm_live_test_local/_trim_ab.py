"""A/B: raw 5 s captures vs trim-to-speech re-centered windows, on the ME2 holdout.

The holdout clips may be archived out of recordings/ (blank start), so this reads the
newest _archive_me2h_holdout_* folder when the live index has no holdout entries. Each
real clip is scored twice through every Gate 2 model: RAW (the 5 s capture as recorded)
and TRIM (energy-based speech span re-centered inside a window of digital silence,
matching the training recipe). OOS clips are scored for the rejection column only.

Prints per-model raw vs trim accuracy and the deltas; writes nothing.
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


def rejected(labels: list[str], probs: list[float]) -> bool:
    best_i = 0
    best_p = -1.0
    for i, p in enumerate(probs):
        try:
            value = float(p)
        except (TypeError, ValueError):
            continue
        if value > best_p:
            best_p = value
            best_i = i
    if best_i >= len(labels):
        return True
    return bag(labels[best_i]) in REJECT


def load_holdout():
    """(root_dir, records) for the ME2 holdout set; live index first, archive fallback."""
    idx_path = HERE / "recordings" / "index.json"
    if idx_path.is_file():
        try:
            data = json.loads(idx_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if data:
            recs = data["recordings"] if isinstance(data, dict) else data
            holdout = [
                r
                for r in recs
                if "me2h" in str(r.get("id")) or "me2holdout" in str(r.get("file"))
            ]
            if holdout:
                return HERE / "recordings", holdout
    for arch in sorted(HERE.glob("_archive_me2h_holdout_*"), reverse=True):
        for sub in ("", "recordings"):
            base = arch / sub if sub else arch
            idx = base / "index.json"
            if not idx.is_file():
                continue
            try:
                data = json.loads(idx.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            recs = data["recordings"] if isinstance(data, dict) else data
            holdout = [
                r
                for r in recs
                if "me2h" in str(r.get("id")) or "me2holdout" in str(r.get("file"))
            ]
            if holdout and any((base / str(r.get("file"))).is_file() for r in holdout):
                return base, holdout
    raise SystemExit("no holdout clips found (live index and archives)")


def main() -> int:
    root, recs = load_holdout()
    commands = [r for r in recs if str(r.get("action") or "").strip()]
    oos = [r for r in recs if not str(r.get("action") or "").strip()]
    real = [r for r in commands if "(real)" in str(r.get("label") or "").lower()]
    print(
        "root="
        + root.name
        + " real="
        + str(len(real))
        + " oos="
        + str(len(oos))
    )
    clips = []
    for rec in real + oos:
        path = root / str(rec["file"])
        if not path.is_file():
            continue
        clips.append((rec, load_wav(path)))
    if not clips:
        raise SystemExit("no clips loaded")

    rows = []
    names = sorted(gs.GATE2_PACKAGE_RUNNERS)
    for name in names:
        try:
            if name == "gate2v124_ensemble4way":
                runner = gs.Gate2V124EnsembleRunner(name)
            else:
                runner = gs.Gate2PackageRunner(name)
        except (OSError, RuntimeError, ValueError, ImportError) as exc:
            print("SKIP " + name + " (" + type(exc).__name__ + ")")
            continue
        labels = list(runner.labels)
        frames = int(getattr(runner, "frames", gs.TARGET_148))
        window = max(1, frames * gs.HOP)
        raw_hits = trim_hits = seen = raw_rej = trim_rej = seen_oos = 0
        speech_len = []
        speech_start = []
        no_trim = 0
        started = time.perf_counter()
        for rec, clip in clips:
            expected = rec.get("action")
            if str(expected or "").strip():
                seen += 1
                try:
                    raw_p = probs_for(name, runner, clip)
                except (RuntimeError, ValueError):
                    continue
                trimmed = op._trim_to_speech(clip, gs.SR)
                if trimmed is None:
                    no_trim += 1
                    trim_clip = clip
                else:
                    speech, start = trimmed
                    speech_len.append(speech.shape[0] / gs.SR)
                    speech_start.append(start / gs.SR)
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
                if same_command(top_intent(labels, raw_p), expected):
                    raw_hits += 1
                if same_command(top_intent(labels, trim_p), expected):
                    trim_hits += 1
            else:
                seen_oos += 1
                try:
                    raw_p = probs_for(name, runner, clip)
                    trim_p = probs_for(name, runner, trim_from(clip, window, name))
                except (RuntimeError, ValueError):
                    continue
                if rejected(labels, raw_p):
                    raw_rej += 1
                if rejected(labels, trim_p):
                    trim_rej += 1
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
                "raw_rej": round(100 * raw_rej / seen_oos, 1) if seen_oos else None,
                "trim_rej": round(100 * trim_rej / seen_oos, 1) if seen_oos else None,
                "ms": round((time.perf_counter() - started) * 1000 / max(1, len(clips)), 2),
                "speech_s": round(statistics.median(speech_len), 2) if speech_len else None,
                "start_s": round(statistics.median(speech_start), 2) if speech_start else None,
                "no_trim": no_trim,
            }
        )
        print(
            name.ljust(30)
            + " raw="
            + str(raw_acc)
            + "% trim="
            + str(trim_acc)
            + "% d="
            + ("%+.1f" % rows[-1]["delta"])
            + " rej="
            + str(rows[-1]["raw_rej"])
            + "/"
            + str(rows[-1]["trim_rej"])
            + " speech="
            + str(rows[-1]["speech_s"])
            + "s start="
            + str(rows[-1]["start_s"])
            + "s"
        )
        del runner
        gc.collect()

    rows.sort(key=lambda r: (-r["raw"], -r["trim"], r["model"]))
    print("")
    helpers = [r for r in rows if r["delta"] > 0]
    hurts = [r for r in rows if r["delta"] < 0]
    neutral = [r for r in rows if r["delta"] == 0]
    print(
        "SUMMARY models="
        + str(len(rows))
        + " trim helps="
        + str(len(helpers))
        + " hurts="
        + str(len(hurts))
        + " neutral="
        + str(len(neutral))
    )
    if rows:
        top = rows[:10]
        print(
            "TOP10 raw mean delta="
            + str(round(sum(r["delta"] for r in top) / len(top), 2))
            + " pts"
        )
    med_len = [r["speech_s"] for r in rows if r["speech_s"] is not None]
    med_start = [r["start_s"] for r in rows if r["start_s"] is not None]
    if med_len:
        print("median speech span=" + str(statistics.median(med_len)) + "s")
    if med_start:
        print("median speech start=" + str(statistics.median(med_start)) + "s")
    return 0


def trim_from(clip: np.ndarray, window: int, name: str) -> np.ndarray:
    """Trim variant for the OOS clips (rejection path)."""
    trimmed = op._trim_to_speech(clip, gs.SR)
    if trimmed is None:
        return clip
    speech, _ = trimmed
    if speech.shape[0] >= window:
        return speech[:window].copy()
    left = (window - speech.shape[0]) // 2
    pad = np.zeros(window, dtype=speech.dtype)
    pad[left : left + speech.shape[0]] = speech
    return pad


if __name__ == "__main__":
    sys.exit(main())