"""Continue mode: toggle roundtrip, disarm clears, button echoes."""

import pathlib

from playwright.sync_api import sync_playwright

APP = pathlib.Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1240, "height": 700})
        page.goto(BASE + "/oneshot.html", wait_until="load")
        page.wait_for_selector("#ph-list li", timeout=60000)
        page.wait_for_selector("#btn-cont", timeout=30000)
        page.click("#btn-cont")
        page.wait_for_function(
            "() => window.__oneshot.continueMode === true",
            timeout=20000, polling=300)
        print("CONTINUE_ON echo=" + str(page.eval_on_selector(
            "#btn-cont", "el => el.classList.contains('on')")))
        page.click("#btn-disarm")
        page.wait_for_function(
            "() => window.__oneshot.continueMode === false",
            timeout=20000, polling=300)
        print("DISARM_CLEARED_CONTINUE=true")
        page.click("#btn-cont")
        page.wait_for_function(
            "() => window.__oneshot.continueMode === true",
            timeout=20000, polling=300)
        page.click("#btn-cont")
        page.wait_for_function(
            "() => window.__oneshot.continueMode === false",
            timeout=20000, polling=300)
        print("TOGGLE_OFF=true")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
