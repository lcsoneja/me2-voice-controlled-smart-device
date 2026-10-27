"""Session layer: create folder, save a session take, verdict, phrase pointer."""

import json
import pathlib
import shutil
import urllib.error
import urllib.request

import numpy as np

from recording_lab import RecordingStore

APP = pathlib.Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"
store = RecordingStore(APP / "recordings")


def api(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method="POST" if data else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            "call failed " + path + ": " + type(exc).__name__ + " " + str(exc)[:120]
        )


def main() -> int:
    created = api("/api/oneshot/sessions", {"label": "probe session"})["session"]
    sid = created["id"]
    print(
        "CREATED id="
        + sid
        + " folder_exists="
        + str((store.root / "sessions" / sid).is_dir())
    )

    entry = store.save(
        np.zeros(16000, dtype=np.float32),
        label="probe phrase",
        meta={"action": "PLAY_MUSIC"},
        session=sid,
    )
    print("TAKE file_rel=" + entry["file"] + " session=" + str(entry.get("session")))
    wav_ok = (store.root / entry["file"]).is_file()
    print("WAV_IN_SESSION_FOLDER=" + str(wav_ok))

    store.update(
        entry["id"],
        meta={"verdict": {"intent": "PLAY_MUSIC", "conf": 0.9, "match": True}},
    )
    loaded = store.get(entry["id"]) or {}
    print("VERDICT=" + json.dumps(loaded.get("verdict")))

    store.set_session_phrases(sid, 42)
    listed = {s["id"]: s for s in api("/api/oneshot/sessions")["sessions"]}
    print(
        "POINTER="
        + str(listed.get(sid, {}).get("phrase_pointer"))
        + " takes="
        + str(listed.get(sid, {}).get("takes"))
    )

    rows = api("/api/oneshot/recordings")["recordings"]
    probe_row = next((r for r in rows if r["id"] == entry["id"]), None)
    print("API_ROW session=" + str((probe_row or {}).get("session")))

    store.delete(entry["id"])
    try:
        shutil.rmtree(store.root / "sessions" / sid, ignore_errors=True)
    except OSError as exc:
        print("CLEANUP_WARN " + type(exc).__name__)
    print("CLEANUP takes=" + str(len(api("/api/oneshot/recordings")["recordings"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
