"""Voice data collection for VCM accuracy improvement.

Guided recorder: walks you through every command class with a suggested phrase,
records N repetitions each, saves WAVs + manifest.csv in a timestamped folder,
and prints a per-class collection report with accuracy recommendations.

Usage:
  python recording_voice.py                 # 1 pass over all 34 items
  python recording_voice.py --reps 3        # 3 recordings per item (~100 samples)
  python recording_voice.py --predict       # also show live model predictions
  python recording_voice.py --device 2      # pick a specific mic
  python recording_voice.py --only ALARM    # collect only items matching a filter
"""

import argparse
import csv
import importlib.util
import re
import sys
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("live_session", HERE / "live_session.py")
assert spec is not None and spec.loader is not None, "failed to load live_session.py spec"
ls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ls)

SR = ls.DEFAULT_SAMPLE_RATE
TARGET_PER_CLASS = 50  # real-voice utterances per class for meaningful gains


def safe_label(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", text) or "item"


# (category, intent, value, suggested phrase)
PLAN: list[tuple[str, str, str, str]] = [
    # Wake words
    ("wake", "", "Nova", "Nova"),
    ("wake", "", "Piattos", "Piattos"),
    ("wake", "", "Negative", "<anything that is NOT a command>"),
    # Direct intents
    ("intent", "PLAY_MUSIC", "", "play some music"),
    ("intent", "WEATHER", "", "what's the weather today"),
    ("intent", "TIME", "", "what time is it"),
    ("intent", "LIGHT_ON", "", "turn on the lights"),
    ("intent", "LIGHT_OFF", "", "turn off the lights"),
    ("intent", "PAUSE", "", "pause the music"),
    ("intent", "STOP", "", "stop"),
    ("intent", "NEXT", "", "next song"),
    ("intent", "VOLUME_UP", "", "turn the volume up"),
    ("intent", "VOLUME_DOWN", "", "turn the volume down"),
    ("intent", "CALL", "", "call mom"),
    ("intent", "MESSAGE", "", "send a message to john"),
    ("intent", "LIST_REMINDERS", "", "list my reminders"),
    # Specialist values (numeric + others)
    ("value", "TIMER", "10 seconds", "set a timer for 10 seconds"),
    ("value", "TIMER", "30 seconds", "set a timer for 30 seconds"),
    ("value", "TIMER", "1 minute", "set a timer for 1 minute"),
    ("value", "ALARM", "6 AM", "set an alarm for 6 am"),
    ("value", "ALARM", "8 AM", "set an alarm for 8 am"),
    ("value", "ALARM", "9 PM", "set an alarm for 9 pm"),
    ("value", "TEMPERATURE", "18 degrees", "set the temperature to 18 degrees"),
    ("value", "TEMPERATURE", "22 degrees", "set the temperature to 22 degrees"),
    ("value", "TEMPERATURE", "26 degrees", "set the temperature to 26 degrees"),
    ("value", "BRIGHTNESS", "20 percent", "set brightness to 20 percent"),
    ("value", "BRIGHTNESS", "60 percent", "set brightness to 60 percent"),
    ("value", "BRIGHTNESS", "100 percent", "set brightness to 100 percent"),
    ("value", "COLOR", "Red", "make the lights red"),
    ("value", "COLOR", "Blue", "make the lights blue"),
    ("value", "COLOR", "Green", "make the lights green"),
    ("value", "CREATE_REMINDER", "Drink water", "remind me to drink water"),
    ("value", "CREATE_REMINDER", "Study", "remind me to study"),
    ("value", "CREATE_REMINDER", "Exercise", "remind me to exercise"),
]


def data_label(item: tuple[str, str, str, str]) -> str:
    cat, intent, value, _ = item
    return value if cat in ("value", "wake") else intent


def main() -> int:
    parser = argparse.ArgumentParser(description="Record real-voice training data for the VCM.")
    parser.add_argument("--out", type=str, default=None, help="Output folder (default: voice_data/<timestamp>)")
    parser.add_argument("--reps", type=int, default=1, help="Recordings per item (default: 1; use 3+ for real gains)")
    parser.add_argument("--device", type=str, default=None, help="Audio input device index or name")
    parser.add_argument("--predict", action="store_true", help="Show live model predictions after each take")
    parser.add_argument("--only", type=str, default=None, help="Only items whose label/phrase contains this text")
    args = parser.parse_args()

    items = PLAN
    if args.only:
        needle = args.only.lower()
        items = [it for it in PLAN if needle in data_label(it).lower() or needle in it[3].lower()]
        if not items:
            print(f"No plan items match filter: {args.only}")
            return 1

    now = datetime.now().astimezone()
    out_dir = Path(args.out) if args.out else HERE / "voice_data" / now.strftime("voice_%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    recorder = ls.LiveAudioRecorder(device=args.device, show_meter=True)
    pipeline = None
    if args.predict:
        print("Loading models for live prediction feedback (one-time)...")
        pipeline = ls.VCMModelPipeline(HERE, HERE / ls.DEFAULT_REGISTRY_PATH, HERE / ls.DEFAULT_FEATURE_STATS_PATH)

    print("\n" + "=" * 78)
    print(f" VOICE DATA COLLECTION - {len(items)} items x {args.reps} reps -> {out_dir}")
    print("=" * 78)
    print("Tips for accuracy: speak naturally, vary speed/wording slightly across reps,")
    print("keep ~20cm from the mic, and leave a short pause before/after each phrase.")
    print("Commands: <Enter> record | s skip item | q quit\n")

    manifest_path = out_dir / "manifest.csv"
    try:
        with open(manifest_path, "w", newline="", encoding="utf-8") as mf:
            writer = csv.writer(mf)
            writer.writerow(["filename", "category", "intent", "value", "phrase", "duration_s", "recorded_at"])
            seq = 0
            counts: dict[str, int] = {}

            try:
                for idx, item in enumerate(items, 1):
                    cat, intent, value, phrase = item
                    label = data_label(item)
                    print(f"\n[{idx}/{len(items)}] {label}  (suggested: '{phrase}')")

                    for rep in range(1, args.reps + 1):
                        cmd = input(f"  rep {rep}/{args.reps} - press Enter to record (s/q): ").strip().lower()
                        if cmd == "q":
                            raise KeyboardInterrupt
                        if cmd == "s":
                            print("  skipped item.")
                            break

                        while True:
                            waveform, meta = recorder.record_attempt()
                            disp = meta.get("disposition")
                            if waveform is None or disp != "CAPTURED":
                                print(f"  capture problem ({disp}) - say it again.")
                                retry = input("  press Enter to retry, s to skip item: ").strip().lower()
                                if retry == "s":
                                    break
                                continue

                            seq += 1
                            fname = f"{seq:03d}_{safe_label(label)}.wav"
                            pcm = (np.clip(waveform, -1.0, 1.0) * 32767).astype(np.int16)
                            with wave.open(str(out_dir / fname), "wb") as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(SR)
                                wf.writeframes(pcm.tobytes())
                            dur = round(len(waveform) / SR, 2)
                            writer.writerow([fname, cat, intent, value, phrase, dur, datetime.now().astimezone().isoformat()])
                            mf.flush()
                            counts[label] = counts.get(label, 0) + 1
                            line = f"  saved {fname} ({dur}s)"

                            if pipeline is not None:
                                out2 = pipeline.run_pipeline(waveform, sr=SR, min_confidence=0.0)
                                g2 = out2["gate2"]
                                sp = out2.get("specialist")
                                if cat == "wake":
                                    g1 = out2.get("gate1", {})
                                    pred = g1.get("predicted_label") if g1.get("status") == "EVALUATED" else None
                                    conf = g1.get("confidence", 0.0)
                                else:
                                    pred = sp["predicted_label"] if sp else g2["predicted_label"]
                                    conf = out2["effective_confidence"]
                                verdict = "OK " if pred == label else "MISS"
                                line += f" | model: {pred} (conf {conf:.2f}) [{verdict}]"
                            print(line)
                            break
            except KeyboardInterrupt:
                print("\nCollection stopped by user.")
    except OSError as e:
        print(f"Error: cannot write manifest {manifest_path}: {e}")
        return 1

    print("\n" + "=" * 78)
    print(" COLLECTION REPORT")
    print("=" * 78)
    total = sum(counts.values())
    print(f" Total recordings : {total} in {out_dir}")
    print(f"{'class':<24}{'count':>6}   vs target {TARGET_PER_CLASS}")
    for label in sorted({data_label(it) for it in items}):
        c = counts.get(label, 0)
        bar = "#" * min(c, 30)
        flag = "" if c >= TARGET_PER_CLASS else ("  <-- collect more" if c else "  <-- MISSING")
        print(f"{label:<24}{c:>6}   {bar}{flag}")
    print("\nNext steps for accuracy:")
    print(" 1. Keep a frozen personal test set: record one extra pass and do NOT add it to training.")
    print(" 2. Sync to DGX for retraining:")
    print(f"    scp -r {out_dir} leandro.soneja@ai-n003:~/vcm_live_test_local/voice_data/")
    print(" 3. Priority classes: 6 AM / 8 AM / 9 PM (gate3b is data-limited), then all intents with real voice.")
    print(" 4. After retraining, pull models and run: python live_session.py --selfcheck")
    return 0


if __name__ == "__main__":
    sys.exit(main())
