"""Score the synthetic wake clips on each shipped wake model (Nova/Piattos/Negative).

Run: py -3.12 _probe_wake_models.py
"""
import math
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local")
import gate1_server as server


def as_float(value) -> float:
    """Probe-safe float: fail with a message instead of a traceback."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"probe: unexpected numeric value {value!r}") from exc


CLIPS = {
  "wake_nova": "gate1_wake_nova_f01_pitchhigh_normal.wav",
  "wake_piattos": "gate1_wake_piattos_m01_pitchnorm_fast.wav",
  "cmd_CALL": "gate2_CALL_f04_pitchlow_normal.wav",
  "cmd_STOP": "gate2_STOP_f06_pitchhigh_normal.wav",
}
def load(name):
    with wave.open(str(Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local/synthetic_samples") / name), "rb") as w:
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    pad = max(0, server.WIN_SAMPLES - y.shape[0])
    return np.concatenate([np.zeros(pad, dtype=np.float32), y])[-server.WIN_SAMPLES:]

gates = server.Gates()
models = [k for k in ("gate1v8_f32", "gate1v12_f16", "gate1v10_f16") if k in gates.g1_variants]
for key in models:
    print(f"--- {key} ---")
    for tag, name in CLIPS.items():
        probs, labels, _ = gates.infer_g1_variant(key, load(name))
        top = labels[max(range(len(probs)), key=lambda i: probs[i])]
        print(f"  {tag:14s} nova={probs[0]:.3f} piattos={probs[1]:.3f} negative={(as_float(probs[2]) if len(probs) > 2 else math.nan):.3f}  top={top}")
