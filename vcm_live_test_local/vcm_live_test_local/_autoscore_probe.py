"""Validate the background auto-score queue through the page hook."""

import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
APP = pathlib.Path(__file__).resolve().parent


def call(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method="POST" if data else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            "call failed " + path + ": " + type(exc).__name__ + " " + str(exc)[:150]
        )


def main() -> int:
    archives = sorted(APP.glob("recordings/_archive_me2h_holdout_*"))
    subprocess.run(
        [sys.executable, "_archive_recordings.py", "--restore", archives[-1].name],
        cwd=APP,
        check=True,
        capture_output=True,
    )
    take_id = next(
        r["id"]
        for r in call("/api/oneshot/recordings")["recordings"]
        if (r.get("action") or "").strip()
    )
    print("TAKE=" + take_id)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(BASE + "/oneshot.html", wait_until="load")
            page.click("#tab-takes")
            page.wait_for_selector("#tk-list li", timeout=60000)
            page.evaluate("tid => window.__oneshot.scoreNewTake(tid)", take_id)
            page.wait_for_function(
                "() => document.getElementById('sb-title').textContent.includes('scored take')",
                timeout=240000,
            )
            print("AUTO_TITLE=" + page.inner_text("#sb-title"))
            print(
                "AUTO_ROWS="
                + str(page.eval_on_selector_all("#sb-body tr", "els => els.length"))
            )
            print("AUTO_RANK=" + str(len(call("/api/oneshot/leaderboard")["ranking"])))
            browser.close()
    finally:
        subprocess.run(
            [sys.executable, "_archive_recordings.py"],
            cwd=APP,
            capture_output=True,
            check=False,
        )
        call("/api/oneshot/leaderboard/reset", {})
    print(
        "FINAL RECORDINGS="
        + str(len(call("/api/oneshot/recordings")["recordings"]))
        + " RANKING="
        + str(len(call("/api/oneshot/leaderboard")["ranking"]))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
