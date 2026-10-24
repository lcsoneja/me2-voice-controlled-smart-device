"""Verify the METRICS tab: data renders, t-SNE scatter draws, tables populate."""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
URL = "http://127.0.0.1:8765/vcm_monitor.html"

def main() -> int:
    errs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:250]))
        page.goto(URL, wait_until="load", timeout=60000)
        page.wait_for_function("document.getElementById('status').textContent.indexOf('microphone live') !== -1", timeout=30000)
        page.click("button[data-tab='metrics']")
        page.wait_for_timeout(1200)

        checks = page.evaluate("""() => ({
            summaryCards: document.getElementById('metricsSummary').children.length,
            perClassRows: document.getElementById('metricsPerClass').children.length,
            confusionTables: document.getElementById('metricsConfusion').querySelectorAll('table').length,
            legendChips: document.getElementById('tsneLegend').children.length,
            tsnePoints: (document.getElementById('tsneCanvas')._pts || []).length,
            dataLoaded: !!window.METRICS_DATA,
            tabActive: document.getElementById('sec-metrics').classList.contains('active')
        })""")
        print("checks:", checks)
        page.screenshot(path=str(HERE / "e2e_tab4_metrics.png"), full_page=True)
        browser.close()

    ok = (checks["dataLoaded"] and checks["tabActive"] and checks["summaryCards"] >= 2 and
          checks["perClassRows"] > 10 and checks["confusionTables"] >= 2 and
          checks["legendChips"] >= 19 and checks["tsnePoints"] > 1000 and not errs)
    print("pageerrors:", errs[:4])
    print("METRICS TAB:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    main()
