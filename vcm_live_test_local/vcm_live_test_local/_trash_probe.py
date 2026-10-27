"""Trash round-trip: delete moves to trash, manifest records it, replay works."""

import json
import pathlib
import urllib.error
import urllib.request

import numpy as np
from playwright.sync_api import sync_playwright

from recording_lab import RecordingStore

APP = pathlib.Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"
store = RecordingStore(APP / "recordings")


def api(path: str, payload: dict | None = None, post: bool = True) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path, data=data, method="POST" if post else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit("call failed " + path + ": " + type(exc).__name__ + " " + str(exc)[:120])


def main() -> int:
    first = store.save(np.zeros(16000, dtype=np.float32), label="trash probe a",
                       meta={"action": "WEATHER"})
    second = store.save(np.zeros(16000, dtype=np.float32), label="trash probe b",
                        meta={"action": "TIME"})
    outcome = api("/api/oneshot/recordings/delete",
                  {"ids": [first["id"], second["id"], "me2h_0000"]})
    print("DELETED=" + str(len(outcome["deleted"])) + " refused=" + str(outcome["refused_holdout"])
          + " trash=" + str(outcome["trashed_to"]))
    rows = api("/api/oneshot/recordings", post=False)["recordings"]
    ids = {row["id"] for row in rows}
    print("INDEX keeps_holdout=" + str("me2h_0000" in ids)
          + " probe_gone=" + str(first["id"] not in ids and second["id"] not in ids))
    trash_dir = APP / "recordings" / outcome["trashed_to"]
    wavs = list(trash_dir.glob("*.wav"))
    manifest = json.loads((APP / "recordings" / "trash_manifest.json").read_text(encoding="utf-8"))
    print("TRASH wavs=" + str(len(wavs)) + " manifest_entries=" + str(len(manifest))
          + " has_probe=" + str(any(e["id"] == first["id"] for e in manifest)))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1240, "height": 700})
        page.goto(BASE + "/oneshot.html", wait_until="load")
        page.wait_for_selector("#ph-list li", timeout=60000)
        page.click("#tab-takes")
        page.wait_for_function(
            "() => document.getElementById('tk-list').children.length > 0", timeout=30000)
        page.locator("#tk-list li.tk").first.locator("button:has-text('play')").click()
        src = page.eval_on_selector("#player", "el => el.src")
        print("PLAY_SRC ok=" + str("recordings/audio?id=" in src))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
