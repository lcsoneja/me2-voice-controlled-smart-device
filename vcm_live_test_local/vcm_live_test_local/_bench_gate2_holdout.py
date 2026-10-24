"""Measure Gate 2 holdout accuracy for every shipped model.

No package ships a per-model holdout table (verified: zero holdout fields across all
reports), and the take-bank results only cover 7 models. The ME2 holdout clips are present
locally, so this measures the ranking directly:

  202 clips: 186 labeled commands (all 19 classes) + 16 out-of-scope clips

For each model in the server's Gate 2 registry it reports:
  * acc        fraction of the 186 commands whose top-1 class matches the label
               (NEGATIVE is masked, so a rejection is never counted as a hit)
  * oos_reject fraction of the 16 OOS clips that the model rejects
  * ms_clip    mean inference time per clip on this machine

Writes gate1_web/data/gate2_holdout.json, sorted by accuracy descending, which the one-shot
dashboard reads to build its model dropdown.
"""

import gc
import json
import pathlib
import re
import sys
import time
import wave

import numpy as np

import gate1_server as gs

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "gate1_web" / "data" / "gate2_holdout.json"

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
        raise SystemExit(
            "cannot read " + str(path) + ": " + type(exc).__name__
        ) from exc
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
            continue  # the PID / threshold-reject layers append one extra reject score
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
        return True  # the appended reject score won
    return bag(labels[best_i]) in REJECT


def main() -> int:
    index_path = HERE / "recordings/index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(
            "cannot read " + str(index_path) + ": " + type(exc).__name__
        ) from exc
    recs = index["recordings"] if isinstance(index, dict) else index
    holdout = [
        r
        for r in recs
        if "me2h" in str(r.get("id")) or "me2holdout" in str(r.get("file"))
    ]
    commands = [r for r in holdout if str(r.get("action") or "").strip()]
    oos = [r for r in holdout if not str(r.get("action") or "").strip()]
    print(
        "holdout clips="
        + str(len(holdout))
        + " commands="
        + str(len(commands))
        + " oos="
        + str(len(oos))
    )

    clips = []
    for rec in commands + oos:
        path = HERE / "recordings" / str(rec["file"])
        if not path.is_file():
            print("missing " + str(path))
            continue
        clips.append((rec, load_wav(path)))

    rows = []
    names = sorted(gs.GATE2_PACKAGE_RUNNERS)
    for index_no, name in enumerate(names, 1):
        try:
            runner = gs.Gate2PackageRunner(name)
        except (OSError, RuntimeError, ValueError, ImportError) as exc:
            print("SKIP " + name + " (" + type(exc).__name__ + ")")
            continue
        labels = list(runner.labels)
        correct = rejected_ok = seen_cmd = seen_oos = 0
        elapsed = 0.0
        for rec, clip in clips:
            started = time.perf_counter()
            try:
                probs = probs_for(name, runner, clip)
            except (RuntimeError, ValueError):
                elapsed += (time.perf_counter() - started) * 1000
                continue
            elapsed += (time.perf_counter() - started) * 1000
            expected = rec.get("action")
            if str(expected or "").strip():
                seen_cmd += 1
                if same_command(top_intent(labels, probs), expected):
                    correct += 1
            else:
                seen_oos += 1
                if rejected(labels, probs):
                    rejected_ok += 1
        acc = round(correct / seen_cmd, 4) if seen_cmd else 0.0
        oos_reject = round(rejected_ok / seen_oos, 4) if seen_oos else None
        rows.append(
            {
                "model": name,
                "acc": acc,
                "correct": correct,
                "n": seen_cmd,
                "oos_reject": oos_reject,
                "ms_clip": round(elapsed / max(1, len(clips)), 2),
            }
        )
        print(
            str(index_no).rjust(2)
            + "/"
            + str(len(names))
            + " "
            + name.ljust(30)
            + " acc="
            + str(round(100 * acc, 1))
            + "% ("
            + str(correct)
            + "/"
            + str(seen_cmd)
            + ")"
            + " oos_reject="
            + str(None if oos_reject is None else round(100 * oos_reject, 1))
            + " ms="
            + str(rows[-1]["ms_clip"])
        )
        del runner
        gc.collect()

    rows.sort(key=lambda r: (-r["acc"], -(r["oos_reject"] or 0), r["model"]))
    payload = {
        "schema": 1,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": {
            "name": "ME2 class holdout",
            "clips": len(clips),
            "commands": len(commands),
            "oos": len(oos),
            "note": "top-1 over 19 command classes with NEGATIVE/NEG masked",
        },
        "models": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(
        "TOP5 "
        + ", ".join(r["model"] + "=" + str(round(100 * r["acc"], 1)) for r in rows[:5])
    )
    print("wrote " + str(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
