"""Expand/filter the model ranking in a real browser."""

import json
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"


def api(path: str, payload: dict, post: bool = True) -> dict:
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
    seeded = api("/api/oneshot/leaderboard/score",
                 {"ids": labelled[:3], "models": "all", "reset": True})
    print("SEEDED=" + str(len(seeded["ranking"])))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1240, "height": 700})
        page.goto(BASE + "/oneshot.html", wait_until="load")
        page.wait_for_selector("#ph-list li", timeout=60000)
        page.click("#sb-title")
        page.wait_for_function(
            "() => document.getElementById('tk-rank').classList.contains('expanded')",
            timeout=20000)
        expanded = page.eval_on_selector_all("#rk-body tr", "els => els.length")
        label = page.inner_text("#rk-expand")
        tab = page.eval_on_selector("#tab-takes", "el => el.classList.contains('on')")
        print("SCOREBOARD_CLICK tab_on=" + str(tab) + " rows=" + str(expanded)
              + " button=" + label)

        page.fill("#rk-filter", "v124")
        page.wait_for_timeout(300)
        filtered = page.eval_on_selector_all("#rk-body tr", "els => els.length")
        first = page.eval_on_selector("#rk-body tr:nth-child(1)", "el => el.textContent")
        print("FILTER v124 rows=" + str(filtered) + " first=" + repr(first))

        page.fill("#rk-filter", "")
        page.wait_for_timeout(200)
        page.click("#rk-expand")
        page.wait_for_function(
            "() => !document.getElementById('tk-rank').classList.contains('expanded')",
            timeout=20000)
        collapsed = page.eval_on_selector_all("#rk-body tr", "els => els.length")
        print("COLLAPSED rows=" + str(collapsed))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
