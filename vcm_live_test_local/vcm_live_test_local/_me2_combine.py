"""Rebuild ME2 wake+cmd takes: 1.8 s leading silence + TTS wake + 1-3 s gap + command (>= 9.5 s)."""
import json
import pathlib
import random
import wave

import numpy as np

STORE = pathlib.Path("recordings")
random.seed(42)
SR = 16000
LEAD = 1.8


def load16k(path):
    with wave.open(str(path), "rb") as w:
        sr, ch = w.getframerate(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1).astype(np.int16)
    if sr != SR:
        idx = np.linspace(0, len(data) - 1, round(len(data) * SR / sr))
        data = np.interp(idx, np.arange(len(data), dtype=np.float64), data.astype(np.float64)).astype(np.int16)
    return data


wakes = {p.name: load16k(p) for p in sorted(STORE.glob("wakegen_*_raw.wav"))}
sil = lambda s: np.zeros(max(0, int(s * SR)), dtype=np.int16)

idx_path = STORE / "index.json"
idx = json.loads(idx_path.read_text(encoding="utf-8"))
recs = idx["recordings"] if isinstance(idx, dict) else idx
# drop the previous me2w_* takes (wrong layout: wake at t=0)
removed = 0
keep = []
for r in recs:
    if r["id"].startswith("me2w_"):
        p = STORE / r["file"]
        if p.is_file():
            p.unlink()
        removed += 1
        continue
    keep.append(r)
recs = keep
me2 = [r for r in recs if r["id"].startswith("me2h_")]
added = 0
tiers = {"wake_real": 0, "wake_syn": 0, "wake_oos": 0}
for r in me2:
    rid = "me2w_" + r["id"].split("_")[1]
    if rid in {x["id"] for x in recs}:
        continue
    cmd = load16k(STORE / r["file"])
    wname = random.choice(sorted(wakes))
    gap = round(random.uniform(1.0, 3.0), 2)
    body = np.concatenate([sil(LEAD), wakes[wname], sil(gap), cmd])
    take = np.concatenate([body, sil(max(0.0, 9.5 - len(body) / SR))])
    fname = rid + "_me2wake.wav"
    with wave.open(str(STORE / fname), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(take.tobytes())
    wake_word = "Nova" if "nova" in wname else "Piattos"
    if r["label"].startswith("ME2 OOS"):
        label = ("ME2 wake+OOS: " + r["label"].split(":", 1)[-1].strip())[:80]
        action = ""
        tiers["wake_oos"] += 1
    else:
        tier = "real" if "(real)" in r["label"] else "syn"
        label = ("ME2 wake+cmd (" + tier + "): " + r["label"].split(":", 1)[-1].strip())[:80]
        action = r.get("action") or ""
        tiers["wake_" + tier] += 1
    recs.append({"id": rid, "file": fname, "label": label,
                 "created": "2026-10-24T02:00:00+00:00", "duration_s": round(len(take) / SR, 2),
                 "sample_rate": SR, "channels": 1, "wake_word": wake_word, "action": action})
    added += 1

if isinstance(idx, dict):
    idx["recordings"] = recs
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
else:
    idx_path.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
print("removed:", removed, "| rebuilt:", added, "| tiers:", tiers, "| total takes:", len(recs))
