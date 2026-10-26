"""Fast, bounded check of the recordings ranking controls."""

import json
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
MODEL = "gate2v108_ownerft_v93b"


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            "POST "
            + path
            + " failed: "
            + str(exc.code)
            + " "
            + exc.read().decode(errors="replace")[:200]
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            "POST " + path + " failed: " + type(exc).__name__ + " " + str(exc)
        )


def main() -> int:
    try:
        with urllib.request.urlopen(BASE + "/api/oneshot/recordings", timeout=120) as r:
            rows = json.loads(r.read().decode())["recordings"]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit("list failed: " + type(exc).__name__ + " " + str(exc))
    labelled = [row for row in rows if (row.get("action") or "").strip()]
    ids = [row["id"] for row in labelled[:3]]
    print("SCOREABLE=" + str(len(labelled)) + " seed_ids=" + ",".join(ids))
    seeded = post(
        "/api/oneshot/leaderboard/score", {"ids": ids, "models": [MODEL], "reset": True}
    )
    print("SEED ranking=" + str(len(seeded["ranking"])))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(BASE + "/oneshot.html", wait_until="load")
        page.click("#tab-takes")
        page.wait_for_selector("#tk-list li", timeout=60000)
        print(
            "ROWS=" + str(page.eval_on_selector_all("#tk-list li", "els => els.length"))
        )
        print(
            "ENABLED_CBS="
            + str(
                page.eval_on_selector_all(
                    "#tk-list input[type=checkbox]:not([disabled])", "els => els.length"
                )
            )
        )
        print(
            "RANK_ROWS="
            + str(page.eval_on_selector_all("#rk-body tr", "els => els.length"))
        )
        print("RANK_VISIBLE=" + str(page.is_visible("#tk-rank")))
        print("RANK_TOP=" + page.inner_text("#rk-body tr:first-child"))

        scoreable_rows = page.locator("#tk-list li.tk", has_text="[")
        print("SCOREABLE_ROWS=" + str(scoreable_rows.count()))
        for index in range(3):
            scoreable_rows.nth(index).locator("input[type=checkbox]").check()
        print("COUNT=" + page.inner_text("#tk-count"))

        page.click("#tk-score-one")
        page.wait_for_function(
            "() => /chosen model|pick a Gate 2|scoring failed/.test(document.getElementById('tk-count').textContent)",
            timeout=120000,
        )
        print("ONE=" + page.inner_text("#tk-count"))
        print("ONE_RESULT=" + str(page.is_visible("#tk-result")))

        page.click("#tk-live")
        page.wait_for_timeout(1500)
        print("LIVE_LABEL=" + page.inner_text("#tk-live"))
        print("LIVE_TITLE=" + page.inner_text("#rk-title"))
        page.click("#tk-live")
        page.wait_for_timeout(300)
        print("STOPPED=" + page.inner_text("#tk-live"))

        page.click("#tk-live-reset")
        page.wait_for_function(
            "() => document.getElementById('tk-rank').hidden === true", timeout=60000
        )
        print("RESET=hidden")
        page.screenshot(path="_rank_ui.png")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
