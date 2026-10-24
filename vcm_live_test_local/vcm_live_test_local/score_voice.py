"""Score a recording_voice.py collection folder against the current models.

Reads expected labels from manifest.csv, runs the full gate pipeline once per
recording (models loaded a single time), and prints an overall + per-class report.

Usage:
  python score_voice.py voice_data/voice_20261003_000023
  python score_voice.py voice_data/voice_20261003_000023 --show-misses
"""

import argparse
import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("live_session", HERE / "live_session.py")
assert spec is not None and spec.loader is not None, "failed to load live_session.py spec"
ls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ls)


def main() -> int:
    parser = argparse.ArgumentParser(description="Score collected voice recordings against the VCM pipeline.")
    parser.add_argument("folder", type=str, help="A voice_data/<session> folder containing manifest.csv")
    parser.add_argument("--show-misses", action="store_true", help="List every missed recording")
    args = parser.parse_args()

    folder = Path(args.folder)
    manifest = folder / "manifest.csv"
    if not manifest.is_file():
        print(f"Error: no manifest.csv in {folder}")
        return 1

    rows = []
    try:
        with open(manifest, newline="", encoding="utf-8") as mf:
            for row in csv.DictReader(mf):
                wav = folder / row["filename"]
                if wav.is_file():
                    rows.append(row)
    except OSError as e:
        print(f"Error: cannot read manifest {manifest}: {e}")
        return 1
    if not rows:
        print(f"Error: no recordings found in {folder}")
        return 1

    print(f"Scoring {len(rows)} recordings from {folder} (loading models once)...")
    pipeline = ls.VCMModelPipeline(HERE, HERE / ls.DEFAULT_REGISTRY_PATH, HERE / ls.DEFAULT_FEATURE_STATS_PATH)

    per_class: dict[str, dict[str, int]] = defaultdict(lambda: {"ok": 0, "miss": 0})
    misses: list[str] = []
    for row in rows:
        expected = row["value"] if row["value"] else row["intent"]
        audio, sr_in = ls.read_audio_file(folder / row["filename"])
        out = pipeline.run_pipeline(audio, sr=sr_in, min_confidence=0.0)
        g2 = out["gate2"]
        sp = out.get("specialist")
        if row["category"] == "wake":
            g1 = out.get("gate1", {})
            pred = g1.get("predicted_label") if g1.get("status") == "EVALUATED" else None
            conf = g1.get("confidence", 0.0)
        else:
            pred = sp["predicted_label"] if sp else g2["predicted_label"]
            conf = out["effective_confidence"]
        ok = pred == expected
        per_class[expected]["ok" if ok else "miss"] += 1
        if not ok:
            gate2_pred = g2["predicted_label"]
            detail = f"pred={pred} (conf {conf:.2f}, gate2={gate2_pred})"
            if row["value"] and row["category"] != "wake" and gate2_pred != row["intent"]:
                detail += " [intent-level miss]"
            misses.append(f"  {row['filename']:<28} expected={expected:<14} {detail}")

    total_ok = sum(c["ok"] for c in per_class.values())
    total = sum(c["ok"] + c["miss"] for c in per_class.values())
    print("\n" + "=" * 70)
    print(f" REAL-VOICE SCORE: {total_ok} / {total} ({total_ok / total * 100:.1f}%)")
    print("=" * 70)
    print(f"{'class':<18}{'ok':>4}{'miss':>6}   accuracy")
    for label in sorted(per_class):
        c = per_class[label]
        n = c["ok"] + c["miss"]
        acc = c["ok"] / n * 100 if n else 0.0
        bar = "#" * int(acc / 5)
        print(f"{label:<18}{c['ok']:>4}{c['miss']:>6}   {acc:5.1f}% {bar}")

    if args.show_misses and misses:
        print("\nMISSED RECORDINGS:")
        for m in misses:
            print(m)

    weak = [lbl for lbl, c in per_class.items() if c["miss"] > c["ok"]]
    print("\nRecommendations:")
    if weak:
        print(f" - Weakest classes (more misses than hits): {', '.join(sorted(weak))}")
        print("   -> collect more with: python recording_voice.py --reps 3 --only <class>")
    else:
        print(" - No class is net-failing. Keep collecting (--reps 3) before DGX retraining.")
    print(" - Keep this folder as a frozen test set OR add it to training - never both.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
