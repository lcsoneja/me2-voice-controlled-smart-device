"""Check that the one-shot page fits the real window: bottom controls visible, phrases listed."""

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/oneshot.html"
SIZES = [(1228, 677), (1240, 700), (1100, 620)]

PROBE = """() => {
  const box = (id) => { const e = document.getElementById(id); if (!e) return null;
    const b = e.getBoundingClientRect(); return {top: Math.round(b.top), bottom: Math.round(b.bottom)}; };
  return {
    innerH: window.innerHeight,
    innerW: window.innerWidth,
    scrollH: document.documentElement.scrollHeight,
    arm: box('btn-arm'),
    disarm: box('btn-disarm'),
    phrases: box('ph-sum'),
    options: document.querySelectorAll('#sel-g2 option').length,
    phraseItems: document.querySelectorAll('#ph-list li').length,
    phraseSummary: (document.getElementById('ph-sum') || {}).textContent,
    firstOption: (document.querySelector('#sel-g2 option') || {}).textContent
  };
}"""


def main() -> int:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception:
            browser = p.chromium.launch()
        for w, h in SIZES:
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(URL, wait_until="load")
            page.wait_for_timeout(1800)
            m = page.evaluate(PROBE)
            arm_ok = m["arm"] and m["arm"]["bottom"] <= m["innerH"]
            phrases_ok = m["phrases"] and m["phrases"]["bottom"] <= m["innerH"]
            print(
                str(w)
                + "x"
                + str(h)
                + " innerH="
                + str(m["innerH"])
                + " scrollH="
                + str(m["scrollH"])
                + " arm_bottom="
                + str(m["arm"]["bottom"] if m["arm"] else None)
                + " phrases_bottom="
                + str(m["phrases"]["bottom"] if m["phrases"] else None)
                + " arm_visible="
                + str(arm_ok)
                + " phrases_visible="
                + str(phrases_ok)
                + " fits_without_scroll="
                + str(m["scrollH"] <= m["innerH"] + 2)
                + " options="
                + str(m["options"])
                + " phrase_items="
                + str(m["phraseItems"])
            )
            print(
                "   summary=["
                + str(m["phraseSummary"])
                + "] first_option=["
                + str(m["firstOption"])
                + "]"
            )
            page.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
