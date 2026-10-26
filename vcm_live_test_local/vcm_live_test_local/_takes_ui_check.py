"""Drive the recordings pane: tab, list, selection, real scoring, and the layout contract."""

from playwright.sync_api import sync_playwright

PROBE = """() => ({
  pageScrollH: document.scrollingElement.scrollHeight,
  innerH: window.innerHeight,
  count: (document.getElementById('tk-count') || {}).textContent,
  rows: document.querySelectorAll('#tk-list li.tk').length,
  checked: Array.from(document.querySelectorAll('#tk-list li.tk')).filter((li) => li.querySelector('input:checked')).length,
  summaryRows: document.querySelectorAll('#tk-result tbody tr').length,
  details: document.querySelectorAll('#tk-result details').length,
  firstSummary: (document.querySelector('#tk-result tbody tr') || {}).textContent,
  firstDetail: (document.querySelector('#tk-result details summary') || {}).textContent,
  resultHidden: (document.getElementById('tk-result') || {}).hidden,
  clipped: Array.from(document.querySelectorAll('#pane-takes *')).filter((e) => {
    const r = e.getBoundingClientRect();
    return r.width && r.height && (r.right > innerWidth + 1);
  }).length
})"""


def main() -> int:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1228, "height": 677})
        page.goto("http://127.0.0.1:8765/oneshot.html", wait_until="load")
        page.wait_for_timeout(2200)
        print("tab_click=" + str(page.click("#tab-takes")))
        page.wait_for_selector("#tk-list li.tk", timeout=40000)
        m = page.evaluate(PROBE)
        print("LIST rows=" + str(m["rows"]) + " count=[" + str(m["count"]) + "]")

        # Select the two newest takess that have an intent label and are not holdout clips.
        picked = page.evaluate("""() => {
          const picked = [];
          for (const li of document.querySelectorAll('#tk-list li.tk')) {
            const cb = li.querySelector('input');
            if (cb.disabled) continue;
            if (li.textContent.indexOf("[") < 0) continue;
            cb.click();
            picked.push(li.querySelector('.tk-label').textContent.trim().slice(0, 40));
            if (picked.length === 2) break;
          }
          return picked;
        }""")
        print("SELECTED " + str(picked))
        m2 = page.evaluate(PROBE)
        print("AFTER_SELECT checked=" + str(m2["checked"]))

        page.click("#tk-score")
        page.wait_for_function(
            "() => !document.getElementById('tk-result').hidden && document.querySelectorAll('#tk-result tbody tr').length > 0",
            timeout=300000,
        )
        page.wait_for_timeout(1500)
        m3 = page.evaluate(PROBE)
        print(
            "SCORE summary_rows="
            + str(m3["summaryRows"])
            + " details="
            + str(m3["details"])
        )
        print("  best_row=[" + str(m3["firstSummary"]) + "]")
        print("  first_detail=[" + str(m3["firstDetail"]) + "]")

        page.click("#tk-each")
        page.wait_for_timeout(4000)
        m4 = page.evaluate(PROBE)
        print(
            "EACH_MODE details="
            + str(m4["details"])
            + " count=["
            + str(m4["count"])
            + "]"
        )
        print(
            "LAYOUT page_scroll_ok="
            + str(m4["pageScrollH"] <= m4["innerH"] + 1)
            + " clipped_in_pane="
            + str(m4["clipped"])
        )
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
