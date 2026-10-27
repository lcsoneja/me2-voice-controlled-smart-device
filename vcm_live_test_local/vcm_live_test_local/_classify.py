"""Classify sessions and my-takes: probe remnants vs real recordings."""

import json
import pathlib

APP = pathlib.Path(__file__).resolve().parent
STORE = APP / "recordings"

index = json.loads((STORE / "index.json").read_text(encoding="utf-8"))
sessions_dir = STORE / "sessions"
print("--- sessions ---")
for folder in sorted(sessions_dir.glob("*")):
    meta_path = folder / "session.json"
    if not meta_path.is_file():
        print(folder.name + "  NO_META  wavs=" + str(len(list(folder.glob('*.wav')))))
        continue
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        continue
    label = str(meta.get("label") or "")
    wavs = len(list(folder.glob("*.wav")))
    print(folder.name + "  label=" + repr(label[:44]) + "  wavs=" + str(wavs))
print("--- mine takes (labels) ---")
mine = [e for e in index if not str(e.get("id") or "").startswith("me2h")]
for entry in sorted(mine, key=lambda e: str(e.get("session") or "")):
    print(str(entry.get("session") or "-")[:20] + "  " + str(entry.get("label") or "")[:40]
          + "  session_key=" + str(bool(entry.get("session"))))
