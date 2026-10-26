"""Why is the phrase list narrow/clipped after the tab restructure?"""

from playwright.sync_api import sync_playwright

PROBE = """() => {
  const box = (sel) => {
    const e = document.querySelector(sel);
    if (!e) return null;
    const cs = getComputedStyle(e);
    return {w: Math.round(e.clientWidth), sw: Math.round(e.scrollWidth),
            display: cs.display, cols: cs.columnCount, colW: cs.columnWidth,
            flex: cs.flex, minW: cs.minWidth, overflow: cs.overflow};
  };
  const li = document.querySelector('#ph-list li');
  return {rightcol: box('.rightcol'), pane: box('#pane-phrases'), plist: box('#ph-list'),
          li: box('#ph-list li'), liText: li ? li.textContent.trim().slice(0, 34) : null,
          liSpan: (() => { const s = li && li.querySelector('span:not(.pint)'); return s ? {w: Math.round(s.clientWidth), sw: Math.round(s.scrollWidth)} : null; })(),
          parentW: (() => { const p = document.querySelector('#pane-phrases'); return p ? Math.round(p.getBoundingClientRect().width) : null; })()};
}"""


def main() -> int:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1228, "height": 677})
        page.goto("http://127.0.0.1:8765/oneshot.html", wait_until="load")
        page.wait_for_timeout(2200)
        print(page.evaluate(PROBE))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
