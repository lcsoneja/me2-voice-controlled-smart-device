"""Verify per-version Gate 1 pages: v5 bars (2-class), 60/40 log layout, WS live."""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
URL_BASE = "http://127.0.0.1:8765/"


def main() -> int:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        for ver in ("v2", "v3", "v4", "v5"):
            page = browser.new_page()
            page.goto(URL_BASE + "gate1_monitor_" + ver + ".html", wait_until="load", timeout=60000)
            try:
                page.wait_for_function("document.getElementById('status').textContent.indexOf('microphone live') !== -1", timeout=30000)
                boot = True
            except Exception:
                boot = False
            checks = page.evaluate("""() => {
                const barsEl = document.getElementById('bars');
                const logEl = document.querySelector('.col-log');
                const probsEl = document.querySelector('.col-probs');
                return {
                    bars: barsEl ? barsEl.children.length : -1,
                    logW: logEl ? logEl.getBoundingClientRect().width : 0,
                    probsW: probsEl ? probsEl.getBoundingClientRect().width : 0,
                    twoClassNote: barsEl ? barsEl.textContent : ''
                };
            }""")
            ratio_ok = checks["logW"] > checks["probsW"] * 1.3  # 60/40 => logW ~ 1.5x probsW
            two_class = ver == "v5"
            note_ok = (not two_class) or ("2-class model" in checks["twoClassNote"])
            results.append((ver, boot, checks["bars"], round(checks["logW"] / (checks["probsW"] or 1), 2), ratio_ok, note_ok))
            page.screenshot(path=str(HERE / ("page_" + ver + ".png")))
            page.close()
        browser.close()

    all_ok = True
    for ver, boot, bars, ratio, ratio_ok, note_ok in results:
        ok = boot and ratio_ok and note_ok
        all_ok = all_ok and ok
        print(("PASS  " if ok else "FAIL  ") + f"{ver}: boot={boot} bars={bars} log/probs ratio={ratio} note_ok={note_ok}")
    print("VERSION PAGES:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    main()
