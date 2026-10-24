"""Standalone V77 sanity: load the package, score a real command take + a speech-OOS take."""

import wave

import numpy as np

import gate1_server

WIN = 94720


def load_wav(path):
    with wave.open(str(path), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.astype(np.float32) / 32768.0


def window_of(audio):
    if len(audio) >= WIN:
        return audio[-WIN:]
    return np.concatenate([np.zeros(WIN - len(audio), dtype=np.float32), audio])


runner = gate1_server.Gate2PackageRunner("gate2v77_speech_neg")
print("labels:", len(runner.labels), "| last:", runner.labels[-1])

for rid, fname, expect in (
    ("me2w_0000", "recordings/me2w_0000_me2wake.wav", "PLAY_MUSIC (real command)"),
    ("me2h_0201", "recordings/me2h_0201_me2holdout.wav", "NEG (speech-OOS trap)"),
):
    audio = load_wav(fname)
    probs = runner.predict(window_of(audio))
    order = np.argsort(probs)[::-1]
    top3 = [(runner.labels[i], round(float(probs[i]), 3)) for i in order[:3]]
    print(rid, "->", top3, "| expect:", expect)
