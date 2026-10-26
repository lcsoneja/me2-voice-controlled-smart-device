"""Break down the stage column's vertical budget at the real window size."""

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/oneshot.html"

PROBE = """() => {
  const panel = document.querySelector('.panel.stage');
  const items = [];
  panel.childNodes.forEach(n => {
    if (n.nodeType === 1) {
      const r = n.getBoundingClientRect();
      items.push((n.id || n.className || n.tagName) + ' top=' + Math.round(r.top - panel.getBoundingClientRect().top)
        + ' h=' + Math.round(r.height));
    }
  });
  return {
    panelH: panel.clientHeight,
    panelScroll: panel.scrollHeight,
    children: items
  };
}"""


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        for height in (677, 700):
            page = browser.new_page(viewport={"width": 1228, "height": height})
            page.goto(URL, wait_until="load")
            page.wait_for_selector("#ph-list li", timeout=60000)
            print("H=" + str(height) + " " + str(page.evaluate(PROBE)))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
