"""Why does gate1v4 fire Nova/Piattos randomly? Empirical diagnosis.

Scores NON-WAKE speech (TTS command clips) through gate1v4 AND gate1v3 at
multiple sliding positions. Confirms whether the silence-only negative class
(v4) causes false wakes on speech that v3 (speech negatives included) rejected.
"""
import importlib.util
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
spec = importlib.util.spec_from_file_location("ls", HERE.parent / "live_session.py")
assert spec is not None and spec.loader is not None, "failed to load live_session.py spec"
ls = importlib.util.module_from_spec(spec)
sys.argv = ["x"]
spec.loader.exec_module(ls)
gs = importlib.import_module("gate1_server")

WIN = gs.WIN_SAMPLES
g = gs.Gates()
labels_all = g.labels

# gate1v3 is no longer in Gates (v4 swap) - load it standalone for comparison.
v3_interp = gs._make_interpreter(HERE / "gate1v3_float32.tflite")
v3_ind = v3_interp.get_input_details()[0]
v3_out = v3_interp.get_output_details()[0]["index"]
v3_pre = gs.Preproc("feature_stats_v3_148.npz", 148)


def infer_v3(win):
    feats = v3_pre.extract(win).astype(v3_ind["dtype"])
    v3_interp.set_tensor(v3_ind["index"], feats)
    v3_interp.invoke()
    return [float(v) for v in v3_interp.get_tensor(v3_out)[0]]


def infer_any(model, win):
    return g.infer(model, win) if model == "gate1v4" else infer_v3(win)

V3_LABELS = ["nova", "piattos", "negative"]  # lowercase, v3 label order


def labels_for(model):
    if model == "gate1v3":
        return V3_LABELS
    return labels_all[model]


def wake_prob_of(probs):
    return max(probs[0], probs[1])  # max(nova, piattos) - same order for both models

NON_WAKE = [
    "gate2_CALL_f04_pitchlow_normal.wav",
    "gate2_PLAY_MUSIC_f02_pitchnorm_fast.wav",
    "gate2_WEATHER_m04_pitchhigh_normal.wav",
    "gate2_STOP_f06_pitchhigh_normal.wav",
    "gate2_TIME_m02_pitchlow_normal.wav",
]
POSITIONS = [0.15, 0.35, 0.5, 0.65, 0.85]


def wav(fname):
    with wave.open(str(HERE.parent / "synthetic_samples" / fname), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def wake_prob(probs):
    return max(probs[0], probs[1])  # max(nova, piattos)


def main() -> int:
    fires = {"gate1v4": 0, "gate1v3": 0}
    total = 0
    print("Model | file | pos | top | wake_prob | fires(>=0.5)")
    print("-" * 78)
    for model in ("gate1v4", "gate1v3"):
        for fname in NON_WAKE:
            y = wav(fname)
            for pos in POSITIONS:
                buf = np.zeros(WIN, dtype=np.float32)
                start = int((WIN - len(y)) * pos)
                if start < 0:
                    buf[:] = y[-WIN:]
                else:
                    buf[start : start + len(y)] = y
                probs = infer_any(model, buf)
                labels = labels_for(model)
                top_i = int(np.argmax(probs))
                wp = wake_prob_of(probs)
                fired = wp >= 0.5
                total += 1
                if fired:
                    fires[model] += 1
                if model == "gate1v4" or fired:
                    print(f"{model} | {fname[:26]:<26} | {pos:.2f} | {labels[top_i]:<9} | {wp:.3f} | {'FIRE' if fired else '-'}")
    print()
    print("False-wake fires on NON-WAKE speech:")
    for m in ("gate1v4", "gate1v3"):
        print(f"  {m}: {fires[m]}/{total} positions ({fires[m] / total * 100:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())


