"""Restore, score a few take ids into the leaderboard, archive again."""

import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

APP = pathlib.Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"


def call(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path, data=data, method="POST" if data else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("CALL_FAILED " + type(exc).__name__ + " " + str(exc)[:120])
        raise SystemExit(1)


archives = sorted(APP.glob("recordings/_archive_me2h_holdout_*"))
if not archives:
    raise SystemExit("no archive folder")
subprocess.run([sys.executable, "_archive_recordings.py", "--restore", archives[-1].name],
               cwd=APP, check=True, capture_output=True)
rows = call("/api/oneshot/recordings")["recordings"]
labelled = [row["id"] for row in rows if (row.get("action") or "").strip()]
takes = labelled[:3]
result = call("/api/oneshot/leaderboard/score",
              {"ids": takes, "models": "all", "reset": True})
print("SEEDED ranking=" + str(len(result["ranking"])))
subprocess.run([sys.executable, "_archive_recordings.py"], cwd=APP,
               check=True, capture_output=True)
print("ARCHIVED again n=" + str(len(call("/api/oneshot/recordings")["recordings"])))
print("RANKING held=" + str(len(call("/api/oneshot/leaderboard")["ranking"])))
