"""New session resets the scoreboard and clears the result panes."""

import json
import pathlib
import shutil
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

APP = pathlib.Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"


def api(path: str, payload: dict | None = None, post: bool = True) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method="POST" if post else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            "call failed " + path + ": " + type(exc).__name__ + " " + str(exc)[:120]
        )


def main() -> int:
    try:
        with urllib.request.urlopen(
            BASE + "/api/oneshot/recordings", timeout=120
        ) as resp:
            rows = json.loads(resp.read().decode())["recordings"]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("LIST_FAILED " + type(exc).__name__)
        return 1
    labelled = [row["id"] for row in rows if (row.get("action") or "").strip()]
    seeded = api(
        "/api/oneshot/leaderboard/score",
        {"ids": labelled[:3], "models": "all", "reset": True},
    )
    print("SEEDED=" + str(len(seeded["ranking"])))
    created_id = ""
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1240, "height": 700})
            page.goto(BASE + "/oneshot.html", wait_until="load")
            page.wait_for_selector("#ph-list li", timeout=60000)
            page.wait_for_function(
                "() => document.getElementById('sel-session').options.length > 1",
                timeout=30000,
            )
            page.select_option("#sel-session", "")
            page.wait_for_function(
                "() => { const s = document.getElementById('sel-session'); "
                "return s.value !== ''; }",
                timeout=40000,
                polling=400,
            )
            created_id = page.eval_on_selector("#sel-session", "el => el.value")
            page.wait_for_function(
                "() => document.getElementById('log').textContent.includes('no shots yet')",
                timeout=30000,
                polling=400,
            )
            print("SESSION_ID=" + created_id)
            print("LOG_CLEARED=" + str("no shots yet" in page.inner_text("#log")))
            print("SHOTS=" + page.inner_text("#c-shots"))
            print("INTENT=" + page.inner_text("#r-intent"))
            print(
                "RESULT_HIDDEN="
                + str(page.eval_on_selector("#tk-result", "el => el.hidden"))
            )
            page.wait_for_function(
                "() => document.getElementById('sb-body').children.length === 0",
                timeout=30000,
                polling=400,
            )
            page.wait_for_timeout(400)
            print(
                "SB_ROWS="
                + str(page.eval_on_selector_all("#sb-body tr", "els => els.length"))
            )
            print(
                "PHRASE1="
                + repr(page.eval_on_selector("#sel-phrase", "el => el.value"))
            )
            browser.close()
    finally:
        if created_id:
            folder = APP / "recordings" / "sessions" / created_id
            try:
                shutil.rmtree(folder)
            except OSError:
                pass
            api("/api/oneshot/leaderboard/reset", {})
    after = api("/api/oneshot/leaderboard", post=False)["ranking"]
    print("RANKING_AFTER=" + str(len(after)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
