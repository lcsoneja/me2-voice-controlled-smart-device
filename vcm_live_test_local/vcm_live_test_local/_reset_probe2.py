"""New-session reset: scoreboard + result panes must actually clear."""

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
        BASE + path, data=data, method="POST" if post else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit("call failed " + path + ": " + type(exc).__name__ + " " + str(exc)[:120])


def main() -> int:
    try:
        with urllib.request.urlopen(BASE + "/api/oneshot/recordings", timeout=120) as resp:
            rows = json.loads(resp.read().decode())["recordings"]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("LIST_FAILED " + type(exc).__name__)
        return 1
    labelled = [row["id"] for row in rows if (row.get("action") or "").strip()]
    api("/api/oneshot/leaderboard/score", {"ids": labelled[:3], "models": "all", "reset": True})
    created = ""
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1240, "height": 700})
            page.goto(BASE + "/oneshot.html", wait_until="load")
            page.wait_for_selector("#ph-list li", timeout=60000)
            page.wait_for_function(
                "() => document.getElementById('sb-body').children.length > 0",
                timeout=30000)
            before = page.eval_on_selector_all("#sb-body tr", "els => els.length")
            print("SB_BEFORE=" + str(before))
            page.select_option("#sel-session", "")
            page.wait_for_function(
                "() => document.getElementById('tk-count').textContent"
                ".includes('scoreboard reset')",
                timeout=40000, polling=400)
            created = page.eval_on_selector("#sel-session", "el => el.value")
            after_rows = page.eval_on_selector_all("#sb-body tr", "els => els.length")
            phrase1 = page.eval_on_selector("#sel-phrase", "el => el.value")
            rank_api = len(api("/api/oneshot/leaderboard", post=False)["ranking"])
            print("SESSION=" + created)
            print("SB_AFTER=" + str(after_rows))
            print("LOG=" + page.inner_text("#log").strip().replace("\n", " ")[:60])
            print("SHOTS=" + page.inner_text("#c-shots"))
            print("PHRASE1=" + repr(phrase1))
            print("RANKING_API=" + str(rank_api))
            browser.close()
    finally:
        if created:
            try:
                shutil.rmtree(APP / "recordings" / "sessions" / created)
            except OSError:
                pass
            api("/api/oneshot/leaderboard/reset", {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
