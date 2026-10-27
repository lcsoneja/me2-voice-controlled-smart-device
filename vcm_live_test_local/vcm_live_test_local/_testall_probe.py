"""One-click test-all: real takes x every model, report saved in a folder."""

import json
import pathlib
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

APP = pathlib.Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"


def main() -> int:
    try:
        with urllib.request.urlopen(
            BASE + "/api/oneshot/recordings", timeout=120
        ) as resp:
            rows = json.loads(resp.read().decode())["recordings"]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("LIST_FAILED " + type(exc).__name__)
        return 1
    mine = [r for r in rows if not r.get("holdout") and (r.get("action") or "").strip()]
    print("MINE=" + str(len(mine)))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1240, "height": 700})
        page.goto(BASE + "/oneshot.html", wait_until="load")
        page.wait_for_selector("#ph-list li", timeout=60000)
        page.click("#tab-takes")
        page.wait_for_function(
            "() => document.getElementById('tk-list').children.length > 0",
            timeout=30000,
        )
        page.click("#tk-test-all")
        page.wait_for_function(
            "() => document.getElementById('tk-count').textContent.includes('.json')",
            timeout=900000,
            polling=750,
        )
        print("STATUS=" + page.inner_text("#tk-count"))
        details = page.eval_on_selector_all("#tk-result details", "els => els.length")
        print("RESULT_DETAILS=" + str(details))
        browser.close()
    reports = sorted((APP / "recordings" / "exports").glob("report_*.json")) + sorted(
        APP / "recordings" / "sessions" if False else []
    )
    if not reports:
        print("REPORT missing")
        return 1
    path = reports[-1]
    print("REPORT=" + str(path.relative_to(APP)))
    data = json.loads(path.read_text(encoding="utf-8"))
    print(
        "TAKES="
        + str(len(data["takes"]))
        + " MODELS="
        + str(len(data["summary"]))
        + " PER_MODEL="
        + str(len(data["takes"][0]["results"]))
        + " SESSIONS="
        + str(data["sessions"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
