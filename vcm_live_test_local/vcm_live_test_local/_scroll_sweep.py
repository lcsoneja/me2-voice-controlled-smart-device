"""Count only elements with a REAL scrollbar (visible overflow), populated via seed."""

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/oneshot.html"
SIZES = [(1228, 677), (1240, 700)]

PROBE = """() => {
  const bad = [];
  document.querySelectorAll('*').forEach(e => {
    const st = getComputedStyle(e);
    const vOver = (st.overflowY === 'auto' || st.overflowY === 'scroll');
    const hOver = (st.overflowX === 'auto' || st.overflowX === 'scroll');
    const vBad = vOver && e.scrollHeight > e.clientHeight + 1;
    const hBad = hOver && e.scrollWidth > e.clientWidth + 1;
    if (vBad || hBad) {
      bad.push({
        id: e.id || '',
        cls: (e.className && typeof e.className === 'string') ? e.className.slice(0, 20) : '',
        v: e.scrollHeight + '/' + e.clientHeight,
        h: e.scrollWidth + '/' + e.clientWidth
      });
    }
  });
  return bad;
}"""


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        for width, height in SIZES:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(URL, wait_until="load")
            page.wait_for_selector("#ph-list li", timeout=60000)
            print("SIZE=" + str(width) + "x" + str(height))
            print("  phrases scrollbars: " + str(page.evaluate(PROBE)))
            page.click("#tab-takes")
            page.wait_for_function(
                "() => !document.getElementById('tk-count').textContent.includes('loading')")
            print("  takes    scrollbars: " + str(page.evaluate(PROBE)))
            page.screenshot(path="_fit_" + str(width) + ".png", full_page=False)
            page.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
