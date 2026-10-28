"""End-to-end probe of the trim-to-speech option: UI checkbox -> ws payload ->
server state echo -> checkbox restored on reload."""

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
        page.wait_for_timeout(1500)
        box = page.locator("#opt-trim")
        present = box.count() == 1
        if not present:
            print("opt-trim MISSING")
            browser.close()
            return 1
        page.check("#opt-trim")
        page.wait_for_timeout(1200)  # send options + server echo
        page.reload(wait_until="load")
        page.wait_for_timeout(1500)
        restored = page.evaluate("() => document.getElementById('opt-trim').checked")
        payload = page.evaluate("() => (window.__oneshot || {}).options || null")
        # unchecked round-trip too
        page.uncheck("#opt-trim")
        page.wait_for_timeout(1200)
        page.reload(wait_until="load")
        page.wait_for_timeout(1500)
        cleared = page.evaluate("() => document.getElementById('opt-trim').checked")
        print(
            "present="
            + str(present)
            + " restored="
            + str(bool(restored))
            + " payload="
            + str(payload)
            + " cleared="
            + str(not cleared)
        )
        browser.close()
        return 0 if (present and restored and not cleared) else 1


if __name__ == "__main__":
    raise SystemExit(main())
