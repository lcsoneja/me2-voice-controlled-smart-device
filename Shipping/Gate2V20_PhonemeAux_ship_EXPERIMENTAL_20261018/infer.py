#!/usr/bin/env python3
"""Offline Gate2v20 phoneme-auxiliary intent intent inference from a WAV file (CPU, no cloud, no LLM).

Usage: python infer.py AUDIO.wav [--model tflite/gate2v20_phoneme_aux_intent_float16.tflite] [--topk 3]
Preprocessing mirrors training exactly: 16 kHz mono, mel(n_fft=1024, hop=640,
win=1024, n_mels=60, center, power=2), log1p, center-crop/pad to 148 frames,
scalar z-score normalization (Gate2v6 train-only stats).
"""
import argparse, json
from pathlib import Path
import numpy as np
import soundfile as sf
import librosa
import tensorflow as tf

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "preprocessing_spec.json").read_text())
LABELS = json.loads((HERE / "labels.json").read_text())["labels"]
MEAN, STD = SPEC["stats_mean"], SPEC["stats_std"]

def preprocess(path):
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim == 2:
        y = y.mean(axis=1)
    if sr != 16000:
        y = librosa.resample(y, orig_sr=sr, target_sr=16000).astype(np.float32)
    s = librosa.feature.melspectrogram(y=y, sr=16000, n_fft=SPEC["n_fft"], hop_length=SPEC["hop_length"], win_length=SPEC["win_length"], n_mels=SPEC["n_mels"], center=SPEC["center"], power=2.0)
    x = np.log1p(s).T
    if len(x) < 148:
        x = np.pad(x, ((0, 148 - len(x)), (0, 0)), mode="constant")
    else:
        start = (len(x) - 148) // 2
        x = x[start:start + 148]
    x = ((x.astype(np.float32) - MEAN) / STD)[..., None]
    return x[None, ...]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("wav")
    ap.add_argument("--model", default=str(HERE / "tflite/gate2v20_phoneme_aux_intent_float16.tflite"))
    ap.add_argument("--topk", type=int, default=3)
    a = ap.parse_args()
    interp = tf.lite.Interpreter(model_path=a.model)
    interp.allocate_tensors()
    x = preprocess(a.wav)
    idet, odet = interp.get_input_details()[0], interp.get_output_details()[0]
    interp.set_tensor(idet["index"], x.astype(idet["dtype"]))
    interp.invoke()
    probs = interp.get_tensor(odet["index"])[0].astype(np.float32)
    top = np.argsort(probs)[::-1][: a.topk]
    for k in top:
        print(f"{LABELS[k]}\t{probs[k]:.4f}")

if __name__ == "__main__":
    main()
