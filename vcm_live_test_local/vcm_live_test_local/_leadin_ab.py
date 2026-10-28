"""Lead-in A/B: does dropping the wake-word tail help the live contenders?

The saved 5 s takes start at wake detection, so the wake word's tail sits inside
the scoring window (measured: audio present within 50 ms in 187/187 takes). This
scores each of the 153 shipped takes four ways for the live top models:

  raw           the file exactly as recorded
  center        the whole 5 s clip centered in the 5.92 s model window
  drop250       first 0.25 s dropped, then centered
  drop500       first 0.50 s dropped, then centered

Writes _leadin_results.json next to this script.
"""

import gc
import json
import pathlib
import statistics
import sys
import time

import numpy as np

import gate1_server as gs
from _bench_gate2_holdout import load_wav, probs_for, same_command, top_intent

HERE = pathlib.Path(__file__).resolve().parent
SHIP = HERE.parents[1] / "Shipping"
OUT = HERE / "_leadin_results.json"
MODELS = (
    "gate2v21p",
    "gate2v110_ownerft_aggr",
    "gate2v19p",
    "gate2v56_v54",
    "gate2v96c_v93b_rerun",
    "gate2v108_ownerft_v93b",
    "gate2v124_ensemble4way",
)
CONDITIONS = (("raw", None), ("center", 0.0), ("drop250", 0.25), ("drop500", 0.5))


def windowed(clip: np.ndarray, window: int, drop_s: float | None) -> np.ndarray:
    """None keeps the raw clip; otherwise drop a lead-in and centre in the window."""
    if drop_s is None:
        return clip
    if drop_s > 0:
        clip = clip[int(drop_s * gs.SR):]
    if clip.shape[0] >= window:
        start = (clip.shape[0] - window) // 2
        return clip[start : start + window]
    out = np.zeros(window, dtype=clip.dtype)
    left = (window - clip.shape[0]) // 2
    out[left : left + clip.shape[0]] = clip
    return out


def load_takes():
    packages = sorted(SHIP.glob("VoiceSessions_ship_*"))
    if not packages:
        raise SystemExit("no VoiceSessions_ship_* package in " + str(SHIP))
    package = packages[-1]
    takes = []
    for sub in sorted(package.iterdir()):
        if not sub.is_dir() or not sub.name.isdigit():
            continue
        try:
            meta = json.loads((sub / "takes.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print("SKIP " + sub.name + " " + type(exc).__name__)
            continue
        for entry in meta:
            audio = sub / "audio" / str(entry.get("audio") or "")
            action = str(entry.get("action") or "").strip()
            if audio.is_file() and action:
                takes.append((sub.name, audio, action))
    return package, takes


def main() -> int:
    package, takes = load_takes()
    print("package=" + package.name + " takes=" + str(len(takes)))
    clips = [(label, action, load_wav(path)) for label, path, action in takes]
    window = gs.TARGET_148 * gs.HOP
    rows = []
    for name in MODELS:
        try:
            runner = (
                gs.Gate2V124EnsembleRunner(name)
                if name == "gate2v124_ensemble4way"
                else gs.Gate2PackageRunner(name)
            )
        except (OSError, RuntimeError, ValueError, ImportError) as exc:
            print("SKIP " + name + " (" + type(exc).__name__ + ")")
            continue
        labels = list(runner.labels)
        hits = {cond: 0 for cond, _ in CONDITIONS}
        seen = 0
        per_session: dict[str, list[int]] = {}
        started = time.perf_counter()
        for label, action, clip in clips:
            ok = {}
            valid = False
            for cond, drop in CONDITIONS:
                variant = windowed(clip, window, drop)
                try:
                    probs = probs_for(name, runner, variant)
                except (RuntimeError, ValueError):
                    ok[cond] = False
                    continue
                valid = True
                ok[cond] = same_command(top_intent(labels, probs), action)
            if not valid:
                continue
            seen += 1
            for cond, _ in CONDITIONS:
                hits[cond] += 1 if ok[cond] else 0
            bucket = per_session.setdefault(label, [0] * (1 + len(CONDITIONS)))
            bucket[0] += 1
            for index, (cond, _) in enumerate(CONDITIONS):
                bucket[1 + index] += 1 if ok[cond] else 0
        if seen == 0:
            continue
        acc = {cond: round(100 * hits[cond] / seen, 1) for cond, _ in CONDITIONS}
        rows.append(
            {
                "model": name,
                "n": seen,
                "acc": acc,
                "per_session": {
                    key: {
                        "n": bucket[0],
                        "acc": {
                            cond: round(100 * bucket[1 + index] / bucket[0], 1)
                            for index, (cond, _) in enumerate(CONDITIONS)
                        },
                    }
                    for key, bucket in per_session.items()
                },
                "ms": round((time.perf_counter() - started) * 1000 / max(1, seen * 4), 2),
            }
        )
        print(
            name.ljust(28)
            + " raw=" + str(acc["raw"]).rjust(5)
            + "%  center=" + str(acc["center"]).rjust(5)
            + "%  drop250=" + str(acc["drop250"]).rjust(5)
            + "%  drop500=" + str(acc["drop500"]).rjust(5)
        )
        del runner
        gc.collect()
    if rows:
        print()
        for cond, _ in CONDITIONS:
            print(
                "MEAN " + cond.ljust(8)
                + str(round(statistics.mean(r["acc"][cond] for r in rows), 2)).rjust(6)
            )
        best = max(CONDITIONS, key=lambda c: statistics.mean(r["acc"][c[0]] for r in rows))
        print("BEST CONDITION overall: " + best[0])
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "package": package.name,
        "takes": len(clips),
        "conditions": [c for c, _ in CONDITIONS],
        "models": rows,
    }
    try:
        OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    except OSError as exc:
        print("WRITE " + type(exc).__name__)
    print("wrote " + str(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
