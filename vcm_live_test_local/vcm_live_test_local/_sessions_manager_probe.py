"""Session management: list, delete empty, trash non-empty, sweep."""

import json
import pathlib
import shutil
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
        BASE + path,
        data=data,
        method="POST" if post else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            "call failed " + path + ": " + type(exc).__name__ + " " + str(exc)[:120]
        )


def cleanup_trash(before_dirs: set[str], before_text: str) -> None:
    trash_root = APP / "recordings"
    for folder in trash_root.glob("_trash_*"):
        if folder.name not in before_dirs:
            try:
                shutil.rmtree(folder)
            except OSError:
                pass
    manifest = trash_root / "trash_manifest.json"
    if manifest.is_file():
        try:
            current = manifest.read_text(encoding="utf-8")
        except OSError:
            current = ""
        if current != before_text:
            try:
                manifest.write_text(before_text, encoding="utf-8")
            except OSError:
                pass


def main() -> int:
    trash_root = APP / "recordings"
    before_dirs = {d.name for d in trash_root.glob("_trash_*")}
    manifest_path = trash_root / "trash_manifest.json"
    before_text = (
        manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else "[]"
    )
    empty = api("/api/oneshot/sessions", {"label": "sman probe empty"})["session"]
    one = api("/api/oneshot/sessions", {"label": "sman probe one"})["session"]
    two = api("/api/oneshot/sessions", {"label": "sman probe two"})["session"]
    take_a = store.save(
        np.zeros(16000, dtype=np.float32),
        label="sman probe a",
        meta={"action": "WEATHER"},
        session=one["id"],
    )
    store.save(
        np.zeros(16000, dtype=np.float32),
        label="sman probe b",
        meta={"action": "TIME"},
        session=two["id"],
    )
    store.save(
        np.zeros(16000, dtype=np.float32),
        label="sman probe c",
        meta={"action": "NEXT"},
        session=two["id"],
    )
    listed = api("/api/oneshot/sessions", post=False)["sessions"]
    counts = {s["id"]: s["takes"] for s in listed}
    print(
        "LISTED="
        + str(len(listed))
        + " empty="
        + str(counts.get(empty["id"]))
        + " one="
        + str(counts.get(one["id"]))
        + " two="
        + str(counts.get(two["id"]))
    )

    gone = api("/api/oneshot/sessions/delete", {"id": empty["id"]})
    print("EMPTY deleted=" + str(gone["deleted"]) + " moved=" + str(gone["moved_to"]))

    trashed = api("/api/oneshot/sessions/delete", {"id": two["id"]})
    print(
        "TWO deleted="
        + str(trashed["deleted"])
        + " moved="
        + str(trashed["moved_to"])
        + " takes="
        + str(trashed["takes_removed"])
    )
    trash_folder = APP / "recordings" / trashed["moved_to"]
    print(
        "TRASH_HOLDS_SESSION="
        + str((trash_folder / "session.json").is_file())
        + " wavs="
        + str(len(list(trash_folder.glob("*.wav"))))
    )
    rows = api("/api/oneshot/recordings", post=False)["recordings"]
    ids = {row["id"] for row in rows}
    print("INDEX_CLEAN=" + str(take_a["id"] not in ids))

    keep = api("/api/oneshot/sessions", post=False)["sessions"]
    kept_ids = [s["id"] for s in keep if s["id"] == one["id"]]
    print("ONE_REMAINS=" + str(len(kept_ids) == 1))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1240, "height": 700})
            page.goto(BASE + "/oneshot.html", wait_until="load")
            page.wait_for_selector("#ph-list li", timeout=60000)
            page.click("#tab-takes")
            page.wait_for_selector("#sman-box", timeout=60000)
            page.get_by_text("Sessions - manage").click()
            page.wait_for_selector("#sman .srow", timeout=30000)
            print(
                "MANAGER_ROWS="
                + str(page.eval_on_selector_all("#sman .srow", "els => els.length"))
            )
            page.locator("#sman .srow", has_text="sman probe one").locator(
                "button"
            ).click()
            page.wait_for_function(
                "() => !document.getElementById('sman').textContent.includes('sman probe one')",
                timeout=30000,
                polling=400,
            )
            print("UI_DELETE=ok")
            browser.close()
    finally:
        cleanup_trash(before_dirs, before_text)
        for sid in (one["id"], two["id"], empty["id"]):
            try:
                shutil.rmtree(APP / "recordings" / "sessions" / sid)
            except OSError:
                pass
    print(
        "SESSIONS_LEFT="
        + str(len(api("/api/oneshot/sessions", post=False)["sessions"]))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
