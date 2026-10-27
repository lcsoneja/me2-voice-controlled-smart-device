"""Save one take's matrix, read it back, report shape."""

import json
import pathlib
import urllib.error
import urllib.request

import numpy as np

from recording_lab import RecordingStore

APP = pathlib.Path(__file__).resolve().parent
store = RecordingStore(APP / "recordings")


def main() -> int:
    entry = store.save(np.zeros(16000, dtype=np.float32), label="matrix probe",
                       meta={"action": "WEATHER"})
    try:
        request = urllib.request.Request(
            "http://127.0.0.1:8765/api/oneshot/results/save",
            data=json.dumps({"ids": [entry["id"]], "models": "all"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                saved = json.loads(response.read().decode())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print("SAVE_FAILED " + type(exc).__name__ + " " + str(exc)[:120])
            return 1
        path = APP / "recordings" / saved["path"]
        data = json.loads(path.read_text(encoding="utf-8"))
        take = data["takes"][0]
        print("PATH=" + saved["path"])
        print("TAKES=" + str(len(data["takes"])) + " MODELS=" + str(len(take["results"]))
              + " FIRST=" + str(take["results"][0]["model"]) + ":" + str(take["results"][0]["intent"])
              + " conf=" + str(take["results"][0]["conf"]))
        print("SUMMARY_TOP=" + str(data["summary"][0]["model"]) + " acc=" + str(data["summary"][0]["acc"]))
        path.unlink()
    finally:
        store.delete(entry["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
