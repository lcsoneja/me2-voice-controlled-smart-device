import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local")
import gate1_server as server


def dims(shape) -> tuple[int, ...]:
    """Tensor dims as ints; a probe should fail with a message, not a traceback."""
    try:
        return tuple(int(x) for x in shape)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"probe: unexpected tensor shape {shape!r}") from exc


def as_float(value) -> float:
    """Probe-safe float: fail with a message instead of a traceback."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"probe: unexpected numeric value {value!r}") from exc


SR = 16000
CLIPS = {
  "wake_nova": "gate1_wake_nova_f01_pitchhigh_normal.wav",
  "wake_piattos": "gate1_wake_piattos_m01_pitchnorm_fast.wav",
  "cmd_CALL": "gate2_CALL_f04_pitchlow_normal.wav",
  "cmd_PLAY_MUSIC": "gate2_PLAY_MUSIC_f02_pitchnorm_fast.wav",
  "cmd_STOP": "gate2_STOP_f06_pitchhigh_normal.wav",
}
def load(name):
    with wave.open(str(Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local/synthetic_samples") / name), "rb") as w:
        assert w.getframerate() == SR, (name, w.getframerate())
        return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0)

INTERP = server._make_interpreter(Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/Shipping/Gate1V12_WarpSpecAug_ship_EXPERIMENTAL_20261020/tflite/gate1v12_float16.tflite"))
i = INTERP.get_input_details()[0]
o = INTERP.get_output_details()[0]
print("v12 input", dims(i["shape"]))

for stats_name in ["feature_stats_v10.npz","feature_stats_v3_148.npz","feature_stats_v4_148.npz","feature_stats_v5_148.npz","feature_stats_v8_148.npz"]:
    try:
        pre = server.Preproc(stats_name, server.TARGET_148)
    except Exception as exc:
        print(f"{stats_name}: unavailable ({exc})")
        continue
    print(f"--- {stats_name} (mean={as_float(pre.mean):.5f} std={as_float(pre.std):.5f}) ---")
    for tag, name in CLIPS.items():
        audio = load(name)
        pad = max(0, server.WIN_SAMPLES - audio.shape[0])
        win = np.concatenate([np.zeros(pad, dtype=np.float32), audio])[-server.WIN_SAMPLES:]
        feats = pre.extract(win).astype(i["dtype"])
        INTERP.set_tensor(i["index"], feats)
        INTERP.invoke()
        probs = INTERP.get_tensor(o["index"])[0]
        top = "Nova" if probs[0] >= max(probs[1], probs[2]) else ("Piattos" if probs[1] >= probs[2] else "Negative")
        print(f"  {tag:14s} nova={probs[0]:.3f} piattos={probs[1]:.3f} negative={probs[2]:.3f}  top={top}")
