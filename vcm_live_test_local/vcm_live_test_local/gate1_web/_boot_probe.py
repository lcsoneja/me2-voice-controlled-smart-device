"""Boot probe: capture console + pageerrors + status for vcm_monitor.html."""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/vcm_monitor.html"

def main() -> int:
    console = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page()
        page.on("console", lambda m: console.append(m.type + ": " + m.text[:300]))
        page.on("pageerror", lambda e: console.append("PAGEERROR: " + str(e)[:400]))
        page.goto(URL, wait_until="load", timeout=60000)
        page.wait_for_timeout(18000)
        print("STATUS :", repr(page.inner_text("#status")[-400:]))
        print("g1log rows:", page.locator("#g1log").count() and page.eval_on_selector_all("#g1log div", "els => els.length"))
        print("lastP1:", page.evaluate("(typeof VCM !== 'undefined' && VCM.state) ? JSON.stringify(VCM.state.lastP1) : 'n/a'"))
        print("BANNER :", repr(page.inner_text("#banner")[:80]))
        print("modelinfo present:", page.locator("#modelinfo").count())
        print("WS readyState probe:", page.evaluate("typeof ws !== 'undefined' && ws ? ws.readyState : 'no-ws'"))
        print("VCM defined:", page.evaluate("typeof VCM !== 'undefined'"))
        print("VCMG2 defined:", page.evaluate("typeof VCMG2 !== 'undefined'"))
        print("VCMPIPE defined:", page.evaluate("typeof VCMPIPE !== 'undefined'"))
        browser.close()
    print("--- console (first 20) ---")
    for c in console[:20]:
        print("  ", c)
    return 0

if __name__ == "__main__":
    main()
