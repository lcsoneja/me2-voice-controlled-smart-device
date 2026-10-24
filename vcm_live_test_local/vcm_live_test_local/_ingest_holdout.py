"""Ingest the AI231-ME2 class-holdout split (202 clips: cmd real/syn + 16 OOS) as recorded-voice takes."""
import io
import json
import datetime
import pathlib
import wave

import pyarrow.parquet as pq

PQ = r"C:/Users/Leandro/.cache/huggingface/hub/datasets--airimonda--ai231-me2-voice-commands/snapshots/bfca0bbebfe17e00d6a685d1da573615d29ecdce/data/holdout-00000-of-00001.parquet"
STORE = pathlib.Path("recordings")

t = pq.read_table(PQ)
rows = t.to_pylist()
idx_path = STORE / "index.json"
idx = json.loads(idx_path.read_text(encoding="utf-8"))
recs = idx["recordings"] if isinstance(idx, dict) else idx
existing = {r["id"] for r in recs}

added = skipped = 0
tiers = {"cmd_real": 0, "cmd_syn": 0, "oos": 0}
for i, row in enumerate(rows):
    rid = f"me2h_{i:04d}"
    if rid in existing:
        skipped += 1
        continue
    aud = row["audio"]
    data = aud["bytes"] if isinstance(aud, dict) else aud
    w = wave.open(io.BytesIO(data))
    sr, ch, dur = w.getframerate(), w.getnchannels(), round(w.getnframes() / w.getframerate(), 2)
    w.close()
    fname = rid + "_me2holdout.wav"
    (STORE / fname).write_bytes(data)
    if int(row["out_of_scope"] or 0):
        label = ("ME2 OOS: " + str(row["transcript"] or row["bucket"] or ""))[:80]
        action = ""
        tiers["oos"] += 1
    else:
        tier = "real" if not int(row["is_synthetic"] or 0) else "syn"
        label = ("ME2 cmd (" + tier + "): " + str(row["bucket"] or row["transcript"] or ""))[:80]
        action = str(row["command"] or "")
        tiers["cmd_" + tier] += 1
    recs.append({"id": rid, "file": fname, "label": label,
                 "created": datetime.datetime.now(datetime.UTC).isoformat(),
                 "duration_s": dur, "sample_rate": sr, "channels": ch,
                 "wake_word": "", "action": action})
    added += 1

if isinstance(idx, dict):
    idx["recordings"] = recs
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
else:
    idx_path.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
print("added:", added, "| skipped(existing):", skipped, "| tiers:", tiers, "| total takes:", len(recs))
# verify one file decodes
w = wave.open(str(STORE / "me2h_0000_me2holdout.wav"))
print("verify me2h_0000:", w.getframerate(), "Hz", w.getnchannels(), "ch", w.getsampwidth() * 8, "bit")
w.close()
