"""Verify the prep selects exist, persist, and reach the server."""

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/oneshot.html"


def main() -> int:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1240, "height": 700})
        page.goto(URL, wait_until="load")
        page.wait_for_timeout(1800)
        opts = page.eval_on_selector_all("#opt-prep option", "els => els.map(e => e.value)")
        print("opt-prep=" + str(opts))
        page.select_option("#opt-prep", "drop500")
        page.wait_for_timeout(900)
        echoed = page.evaluate("() => (window.__oneshot || {}).options || null")
        print("capture_echo=" + str(echoed))
        page.click("#tab-takes")
        page.wait_for_timeout(600)
        takes = page.eval_on_selector_all("#tk-prep option", "els => els.map(e => e.value)")
        print("tk-prep=" + str(takes))
        page.select_option("#tk-prep", "drop250")
        page.wait_for_timeout(300)
        print("takes_value=" + page.eval_on_selector("#tk-prep", "el => el.value"))
        page.reload(wait_until="load")
        page.wait_for_timeout(1800)
        print("after_reload_capture=" + page.eval_on_selector("#opt-prep", "el => el.value"))
        els = page.eval_on_selector_all("[id]", "els => els.map(e => e.id)")
        print("old_controls_gone=" + str("opt-trim" not in els and "tk-trim" not in els))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
