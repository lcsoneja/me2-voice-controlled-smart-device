"""Gate 1 wake-word live monitor.

Rolling 5.92 s mic buffer; inference every 1 s on the latest window (even on
silence). Prints timestamp, class probabilities, and wake/no-wake per window.

Uses the exact trained stack from the repo: live_session.py pipeline
(Keras checkpoints, v1 log-mel 60x74 preprocessing, registry labels,
DEFAULT_MIN_CONFIDENCE = 0.5 threshold). Gate 1 input is (1, 74, 60, 1):
the 5.92 s window is center-cropped to 74 frames (2.92 s) by the trained
preprocessing - same behavior as live_session.py.

  python gate1_monitor.py                  # live mic, runs until Ctrl+C
  python gate1_monitor.py --duration 15    # auto-stop (for automated tests)
  python gate1_monitor.py --wav FILE       # score one file as a single window
"""

import argparse
import importlib.util
import queue
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent

spec = importlib.util.spec_from_file_location("live_session", HERE / "live_session.py")
assert spec is not None and spec.loader is not None, "failed to load live_session.py spec"
ls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ls)

SR = ls.DEFAULT_SAMPLE_RATE
WINDOW_S = 5.92          # rolling capture window (user spec; = 148 frames)
STRIDE_S = 1.0           # inference cadence (user spec)
MIN_CONF = ls.DEFAULT_MIN_CONFIDENCE  # 0.5, from the tool/handoff - not invented
WINDOW_SAMPLES = int(WINDOW_S * SR)


def probs_line(labels: list[str], probs: np.ndarray) -> str:
    return "  ".join(f"{l}:{p:.3f}" for l, p in zip(labels, probs))


def score(pipeline, labels: list[str], wake_labels: list[str], waveform: np.ndarray) -> dict:
    feats = pipeline.feature_extractor.extract_features(waveform, sr_in=SR)
    vec = pipeline.models["gate1"](feats, training=False).numpy()[0]
    idx = int(np.argmax(vec))
    label, conf = labels[idx], float(vec[idx])
    return {
        "label": label,
        "conf": conf,
        "wake": label in wake_labels and conf >= MIN_CONF,
        "probs": probs_line(labels, vec),
        "frames": int(feats.shape[1]),
    }


def print_result(res: dict) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    mark = "WAKE" if res["wake"] else "no-wake"
    print(f"{ts}  {res['probs']}  -> {mark} ({res['label']} {res['conf']:.3f}) [{res['frames']}f]", flush=True)


def live(args, pipeline, labels: list[str], wake_labels: list[str]) -> None:
    import sounddevice as sd

    q: queue.Queue = queue.Queue()
    stream = sd.InputStream(
        samplerate=SR, channels=1, dtype="float32", blocksize=1024,
        callback=lambda ind, frames, t, status: q.put(ind.copy()),
        device=args.device,
    )
    stream.start()
    print(f"mic open. rolling window {WINDOW_S}s ({WINDOW_SAMPLES} samples). "
          f"inference every {STRIDE_S}s. gate1 input (1,74,60,1) -> 2.92s center window.")
    print("waiting for first full window...")

    buf = np.empty(0, dtype=np.float32)
    last_infer: float | None = None
    start = time.time()
    try:
        while True:
            if args.duration and time.time() - start > args.duration:
                print("duration reached, stopping.")
                break
            try:
                block = q.get(timeout=0.2).flatten()
            except queue.Empty:
                continue
            buf = np.concatenate([buf, block])[-WINDOW_SAMPLES:]
            if len(buf) < WINDOW_SAMPLES:
                continue  # startup: buffer not full yet
            now = time.time()
            if last_infer is None or now - last_infer >= STRIDE_S:
                last_infer = now
                print_result(score(pipeline, labels, wake_labels, buf))
    except KeyboardInterrupt:
        print("\nstopped by user.")
    finally:
        stream.stop()
        stream.close()


def wav_mode(args, pipeline, labels: list[str], wake_labels: list[str]) -> None:
    import wave

    with wave.open(str(args.wav), "rb") as w:
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    print(f"file: {args.wav} ({len(y)/SR:.2f}s) - scored as a single window:")
    print_result(score(pipeline, labels, wake_labels, y))


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate 1 wake-word live monitor (rolling 5.92s window, 1s stride).")
    ap.add_argument("--duration", type=float, default=None, help="auto-stop after N seconds (for automated tests)")
    ap.add_argument("--device", type=str, default=None, help="input device index or name")
    ap.add_argument("--wav", type=str, default=None, help="score one WAV file as a single window and exit")
    args = ap.parse_args()

    try:
        pipeline = ls.VCMModelPipeline(HERE, HERE / ls.DEFAULT_REGISTRY_PATH, HERE / ls.DEFAULT_FEATURE_STATS_PATH)
    except Exception as e:
        print(f"[FATAL] {e}")
        return 1

    labels = list(pipeline.models_meta["gate1"]["labels"])
    wake_labels = [l for l in labels if l.lower() != "negative"]
    print(f"gate1: {ls.CHECKPOINT_PATHS['gate1']}  labels={labels}  wake={wake_labels}  threshold={MIN_CONF}")

    if args.wav:
        wav_mode(args, pipeline, labels, wake_labels)
        return 0
    live(args, pipeline, labels, wake_labels)
    return 0


if __name__ == "__main__":
    sys.exit(main())
