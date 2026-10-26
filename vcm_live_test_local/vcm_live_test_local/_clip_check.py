"""Find every clipped, overflowing or off-screen text element on the one-shot page."""

from playwright.sync_api import sync_playwright

PROBE = """() => {
  const out = {clipped: [], panes: [], vp: {w: window.innerWidth, h: window.innerHeight}};
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const overY = el.scrollHeight - el.clientHeight;
    const overX = el.scrollWidth - el.clientWidth;
    const scrollable = ['auto', 'scroll'].includes(cs.overflowY) || ['auto', 'scroll'].includes(cs.overflowX);
    const isText = el.children.length === 0 && (el.textContent || '').trim().length > 0;
    const tag = el.tagName + (el.id ? '#' + el.id : '') + (el.className ? '.' + String(el.className).split(' ')[0] : '');
    if (!scrollable && (overX > 1 || (isText && overY > 1))) {
      out.clipped.push({tag: tag, text: (el.textContent || '').trim().slice(0, 40), overX: overX, overY: overY});
    }
    if (isText && (r.bottom > innerHeight + 1 || r.right > innerWidth + 1)) {
      out.clipped.push({tag: 'OFFSCREEN ' + tag, text: (el.textContent || '').trim().slice(0, 40),
                        overX: Math.round(r.right - innerWidth), overY: Math.round(r.bottom - innerHeight)});
    }
    if (scrollable && (overY > 1 || overX > 1)) {
      out.panes.push({id: el.id || String(el.className).split(' ')[0] || el.tagName,
                      clientH: el.clientHeight, scrollH: el.scrollHeight, hidden: overY});
    }
  }
  return out;
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
        m = page.evaluate(PROBE)
        print("viewport=" + str(m["vp"]))
        print("CLIPPED=" + str(len(m["clipped"])))
        for c in m["clipped"][:22]:
            print("   " + str(c))
        print("SCROLL_PANES=" + str(len(m["panes"])))
        for s in m["panes"][:12]:
            print("   " + str(s))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
