"""Numpy reference implementation of Gate 1 - verifies the JS port of the
web monitor. Compares a hand-rolled forward pass (conv/BN/pool/BiGRU/dense)
against the trained Keras model on a WAV file.

  python gate1_forward_reference.py [wavfile]
"""

import importlib.util
import json
import sys
import wave
from pathlib import Path

import tensorflow as tf  # heavyweight: needed to load the Keras reference model

import numpy as np

HERE = Path(__file__).parent

spec = importlib.util.spec_from_file_location("live_session", HERE / "live_session.py")
assert spec is not None and spec.loader is not None, "failed to load live_session.py spec"
ls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ls)

LABELS = ["Nova", "Piattos", "Negative"]


def load_export() -> dict:
    path = HERE / "gate1_web" / "gate1_weights.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to load gate1 weights export {path}: {e}") from e


def conv2d_same(x: np.ndarray, k: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Stride-1, padding=same convolution. x: (H,W,Cin), k: (kh,kw,Cin,Cout)."""
    kh, kw, cin, cout = k.shape
    pt, pb = (kh - 1) // 2, kh - 1 - (kh - 1) // 2
    pl, pr = (kw - 1) // 2, kw - 1 - (kw - 1) // 2
    xp = np.pad(x, ((pt, pb), (pl, pr), (0, 0)), mode="constant")
    H, W, _ = x.shape
    out = np.zeros((H, W, cout), dtype=np.float32)
    for oc in range(cout):
        acc = np.zeros((H, W), dtype=np.float32)
        for ic in range(cin):
            for ki in range(kh):
                for kj in range(kw):
                    acc += xp[ki : ki + H, kj : kj + W, ic] * k[ki, kj, ic, oc]
        out[:, :, oc] = acc + b[oc]
    return out


def maxpool2(x: np.ndarray) -> np.ndarray:
    H, W, C = x.shape
    x = x[: (H // 2) * 2, : (W // 2) * 2]
    stacked = np.stack([x[0::2, 0::2], x[1::2, 0::2], x[0::2, 1::2], x[1::2, 1::2]], axis=0)
    return stacked.max(axis=0).astype(np.float32)


def bn(x: np.ndarray, gamma, beta, mean, var, eps: float = 0.001) -> np.ndarray:
    g = np.asarray(gamma, dtype=np.float32)
    b = np.asarray(beta, dtype=np.float32)
    m = np.asarray(mean, dtype=np.float32)
    v = np.asarray(var, dtype=np.float32)
    return (g * (x - m) / np.sqrt(v + eps) + b).astype(np.float32)


def gru_run(seq: np.ndarray, kernel: np.ndarray, rec: np.ndarray, bias: np.ndarray,
            units: int, update_mode: int, reverse: bool = False) -> np.ndarray:
    if reverse:
        seq = seq[::-1]
    b0 = bias[0]
    b1 = bias[1]
    h = np.zeros(units, dtype=np.float32)
    for t in range(seq.shape[0]):
        mx = seq[t] @ kernel
        mi = h @ rec
        z = 1.0 / (1.0 + np.exp(-(mx[:units] + mi[:units] + b0[:units])))
        r = 1.0 / (1.0 + np.exp(-(mx[units : 2 * units] + mi[units : 2 * units] + b0[units : 2 * units])))
        hh = np.tanh(mx[2 * units :] + b0[2 * units :] + r * (mi[2 * units :] + b1[2 * units :]))
        if update_mode == 0:
            h = (1.0 - z) * hh + z * h
        else:
            h = z * hh + (1.0 - z) * h
    return h.astype(np.float32)


def forward_numpy(feats: np.ndarray, export: dict, update_mode: int) -> np.ndarray:
    # export layer indices (InputLayer excluded): 0 conv,1 bn,2 pool,3 conv,4 bn,
    # 5 pool,6 reshape,7 bigru,8 dropout,9 dense
    L = export["layers"]
    x = feats
    # NOTE: the trained Conv2D layers carry activation="relu" internally, so the
    # order is conv -> relu -> BN (not conv -> BN -> relu).
    x = bn(np.maximum(conv2d_same(x, np.array(L[0]["weights"][0], dtype=np.float32),
                                  np.array(L[0]["weights"][1], dtype=np.float32)), 0), *L[1]["weights"])
    x = maxpool2(x)
    x = bn(np.maximum(conv2d_same(x, np.array(L[3]["weights"][0], dtype=np.float32),
                                  np.array(L[3]["weights"][1], dtype=np.float32)), 0), *L[4]["weights"])
    x = maxpool2(x)                                   # (18, 15, 64)
    seq = x.reshape(x.shape[0], -1).astype(np.float32)  # (18, 960)
    W = L[7]["weights"]
    units = int(np.asarray(W[1]).shape[0])  # recurrent kernel is (units, 3*units)
    hf = gru_run(seq, np.array(W[0], dtype=np.float32), np.array(W[1], dtype=np.float32),
                 np.array(W[2], dtype=np.float32), units, update_mode, reverse=False)
    hb = gru_run(seq, np.array(W[3], dtype=np.float32), np.array(W[4], dtype=np.float32),
                 np.array(W[5], dtype=np.float32), units, update_mode, reverse=True)
    h = np.concatenate([hf, hb]).astype(np.float32)   # (128,)
    logits = h @ np.array(L[9]["weights"][0], dtype=np.float32) + np.array(L[9]["weights"][1], dtype=np.float32)
    e = np.exp(logits - logits.max())
    return (e / e.sum()).astype(np.float32)


def main() -> int:
    export = load_export()

    wav = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "synthetic_samples" / "gate2_PLAY_MUSIC_f02_pitchnorm_fast.wav")
    try:
        with wave.open(wav, "rb") as w:
            y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    except (OSError, wave.Error) as e:
        print(f"Error: cannot read {wav}: {e}")
        return 1

    fx = ls.FeatureExtractor(HERE / "vcm8" / "training" / "feature_stats.npz")
    feats = fx.extract_features(y, sr_in=ls.DEFAULT_SAMPLE_RATE)[0]

    model = tf.keras.models.load_model(HERE / "vcm8" / "training" / "runs" / "gate1_v1" / "best_model.keras", compile=False)
    keras_probs = model(feats[None].astype(np.float32), training=False).numpy()[0]
    print("keras  :", dict(zip(LABELS, np.round(keras_probs, 4).tolist(), strict=False)))

    ok = False
    for mode in (0, 1):
        probs = forward_numpy(feats, export, mode)
        diff = float(np.abs(probs - keras_probs).max())
        print(f"numpy update_mode={mode}:", dict(zip(LABELS, np.round(probs, 4).tolist(), strict=False)), f"maxdiff={diff:.2e}")
        if diff < 1e-3:
            ok = True
    print("PARITY:", "OK (update_mode matches Keras)" if ok else "MISMATCH - inspect GRU convention")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
