"""Verify capture-option toggles: change -> server echo, and persistence across a reload."""

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

        # Fresh profile: the socket-open re-sync should have echoed all-off.
        fresh = page.evaluate("() => (window.__oneshot || {}).options || null")

        # Toggle trim -> the server must echo trim=true back.
        page.check("#opt-trim")
        page.wait_for_timeout(700)
        echo1 = page.evaluate("() => (window.__oneshot || {}).options || null")

        # Toggle nc as well, then reload: both must return from localStorage
        # and be re-sent on the socket reconnect.
        page.check("#opt-nc")
        page.wait_for_timeout(400)
        page.reload(wait_until="load")
        page.wait_for_timeout(1800)
        back_nc = page.evaluate("() => document.getElementById('opt-nc').checked")
        back_trim = page.evaluate("() => document.getElementById('opt-trim').checked")
        echo2 = page.evaluate("() => (window.__oneshot || {}).options || null")

        # Uncheck trim -> echo reflects it again.
        page.uncheck("#opt-trim")
        page.wait_for_timeout(700)
        echo3 = page.evaluate("() => (window.__oneshot || {}).options || null")

        ok = (
            isinstance(echo1, dict) and echo1.get("trim") is True
            and back_nc is True and back_trim is True
            and isinstance(echo2, dict) and echo2.get("trim") is True and echo2.get("nc") is True
            and isinstance(echo3, dict) and echo3.get("trim") is False
        )
        print("fresh=" + str(fresh))
        print("echo_after_check=" + str(echo1))
        print("after_reload nc=" + str(back_nc) + " trim=" + str(back_trim) + " echo=" + str(echo2))
        print("echo_after_uncheck=" + str(echo3))
        print("TRIM_FLOW_OK=" + str(ok))
        browser.close()
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
