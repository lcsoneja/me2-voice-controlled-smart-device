"""Direct API check of the export and save endpoints."""

import json
import pathlib
import urllib.error
import urllib.request

import numpy as np

from recording_lab import RecordingStore

APP = pathlib.Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"
store = RecordingStore(APP / "recordings")


def raw(path: str, payload: dict) -> tuple[int, str]:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")[:400]
    except (urllib.error.URLError, OSError) as exc:
        return -1, type(exc).__name__ + " " + str(exc)[:120]


def main() -> int:
    row = next((r for r in store.list() if (r.get("action") or "").strip()), {})
    if not row:
        entry = store.save(
            np.zeros(16000, dtype=np.float32),
            label="api probe take",
            meta={"action": "WEATHER"},
        )
        row = entry
        store.delete(entry["id"])
    take_id = str(row["id"] or "")
    print("TAKE=" + take_id)
    for path in ("/api/oneshot/results/export", "/api/oneshot/results/save"):
        status, body = raw(path, {"ids": [take_id], "models": "all"})
        print(path + " status=" + str(status) + " body=" + body[:260])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
