"""Build a synthetic-wake test take and register it (wake 1.2 s in, silence to 7 s)."""
import json
import math
import pathlib
import wave

import numpy as np

STORE = pathlib.Path("recordings")

def load16k(path):
    with wave.open(str(path), "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        n = w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype=np.int16 if sw == 2 else np.uint8)
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1).astype(np.int16)
    if sr != 16000:
        idx = np.linspace(0, len(data) - 1, int(round(len(data) * 16000 / sr)))
        data = np.interp(idx, np.arange(len(data)), data.astype(np.float64)).astype(np.int16)
    return data

clips = sorted(STORE.glob("wakegen_*_raw.wav"))
print("raw clips:", [c.name for c in clips])
if not clips:
    raise SystemExit("no TTS clips generated")

# pick the first Nova clip for the test
nova = next((c for c in clips if "nova" in c.name), clips[0])
wake = load16k(nova)
sil = lambda s: np.zeros(int(s * 16000), dtype=np.int16)
take = np.concatenate([sil(1.2), wake, sil(max(0.0, 7.0 - 1.2 - len(wake) / 16000.0))])
fname = "wakegen_test_take.wav"
with wave.open(str(STORE / fname), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(take.tobytes())
print("test take:", fname, "dur", round(len(take) / 16000, 2), "s from", nova.name)

idx_path = STORE / "index.json"
idx = json.loads(idx_path.read_text(encoding="utf-8"))
recs = idx["recordings"] if isinstance(idx, dict) else idx
if not any(r["id"] == "wakegen_test" for r in recs):
    recs.append({"id": "wakegen_test", "file": fname, "label": "WAKEGEN test: synthetic Nova",
                 "created": "2026-10-24T00:00:00+00:00", "duration_s": round(len(take) / 16000, 2),
                 "sample_rate": 16000, "channels": 1, "wake_word": "Nova", "action": ""})
if isinstance(idx, dict):
    idx["recordings"] = recs
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
else:
    idx_path.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
print("registered: wakegen_test | total takes:", len(recs))
