"""Session UI: create via the picker, phrase pointer roundtrip, filter, top-5 scoreboard."""

import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

import numpy as np
from playwright.sync_api import sync_playwright

from recording_lab import RecordingStore

APP = pathlib.Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"
store = RecordingStore(APP / "recordings")


def api(path: str, payload: dict | None = None, post: bool | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    method = "POST" if (post or (payload is not None and not post is False)) else "GET"
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            "call failed " + path + ": " + type(exc).__name__ + " " + str(exc)[:120]
        )


def main() -> int:
    archives = sorted(APP.glob("recordings/_archive_me2h_holdout_*"))
    if not archives:
        raise SystemExit("no archive folder")
    subprocess.run(
        [sys.executable, "_archive_recordings.py", "--restore", archives[-1].name],
        cwd=APP,
        check=True,
        capture_output=True,
    )

    session_id = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1240, "height": 700})
            page.goto(BASE + "/oneshot.html", wait_until="load")
            page.wait_for_selector("#ph-list li", timeout=60000)
            page.wait_for_function(
                "() => document.getElementById('sel-session').options.length > 0",
                timeout=30000,
            )
            print(
                "SESSIONS_OPTIONS="
                + str(
                    page.eval_on_selector_all(
                        "#sel-session option", "els => els.length"
                    )
                )
            )

            page.select_option("#sel-session", "")
            page.wait_for_function(
                "() => document.getElementById('sel-session').selectedIndex === 0",
                timeout=20000,
                polling=300,
            )
            # The page POSTs a new session then sends session_use over the socket; the
            # select then gets primed by the session reply.
            page.wait_for_function(
                "() => { const s = document.getElementById('sel-session'); "
                "return s.options.length > 1 && s.value !== ''; }",
                timeout=30000,
                polling=300,
            )
            session_id = page.eval_on_selector("#sel-session", "el => el.value")
            print("NEW_SESSION id=" + str(session_id))

            page.locator("#ph-list li").nth(2).click()
            page.wait_for_timeout(600)
            sessions = api("/api/oneshot/sessions")["sessions"]
            pointer = next(
                (s.get("phrase_pointer") for s in sessions if s["id"] == session_id),
                None,
            )
            print("POINTER_AFTER_CLICK=" + str(pointer))

            probe_entry = store.save(
                np.zeros(16000, dtype=np.float32),
                label="session probe take",
                meta={"action": "WEATHER"},
                session=session_id,
            )
            print("SESSION_TAKE=" + probe_entry["id"])

            seed = api(
                "/api/oneshot/leaderboard/score",
                {"ids": [probe_entry["id"]], "models": "all", "reset": True},
            )
            print("SEEDED ranking=" + str(len(seed["ranking"])))

            page.reload()
            page.wait_for_function(
                "() => document.getElementById('sb-body').children.length > 0",
                timeout=30000,
            )
            sb_rows = page.eval_on_selector_all("#sb-body tr", "els => els.length")
            print("SCOREBOARD_ROWS=" + str(sb_rows))

            page.click("#tab-takes")
            page.wait_for_function(
                "() => document.getElementById('tk-list').children.length > 0",
                timeout=30000,
            )
            all_rows = page.eval_on_selector_all("#tk-list li", "els => els.length")
            page.select_option("#tk-session", session_id)
            page.wait_for_timeout(400)
            filtered = page.eval_on_selector_all("#tk-list li", "els => els.length")
            print("FILTER all=" + str(all_rows) + " session=" + str(filtered))
            browser.close()
    finally:
        try:
            api("/api/oneshot/leaderboard/reset", {}, post=True)
        except SystemExit:
            pass
    print("DONE bid=" + str(session_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
