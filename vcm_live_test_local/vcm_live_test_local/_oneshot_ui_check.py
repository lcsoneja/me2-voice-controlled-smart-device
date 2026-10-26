"""Verify the one-shot page: no page scroll, panes scroll, Gate 1 and phrase pickers work."""

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/oneshot.html"

PROBE = """() => {
  const el = (id) => document.getElementById(id);
  const pane = document.querySelector('#tk-list');
  return {
    innerH: window.innerHeight, innerW: window.innerWidth,
    pageScrollH: document.scrollingElement.scrollHeight,
    pageScrollW: document.scrollingElement.scrollWidth,
    bodyOverflow: getComputedStyle(document.body).overflow,
    g1Options: el('sel-g1') ? el('sel-g1').options.length : 0,
    g1First: (el('sel-g1') && el('sel-g1').options.length) ? el('sel-g1').options[0].textContent : null,
    g2Options: el('sel-g2') ? el('sel-g2').options.length : 0,
    phraseOptions: el('sel-phrase') ? el('sel-phrase').options.length : 0,
    phraseItems: document.querySelectorAll('#ph-list li').length,
    chipG1: el('c-g1') ? el('c-g1').textContent : null,
    chipG2: el('c-g2') ? el('c-g2').textContent : null,
    noteG1: el('sel-g1-note') ? el('sel-g1-note').textContent : null,
    notePhrase: el('sel-phrase-note') ? el('sel-phrase-note').textContent : null,
    pane: pane ? {clientH: pane.clientHeight, scrollH: pane.scrollHeight, overflow: getComputedStyle(pane).overflow} : null,
    armBottom: el('btn-arm') ? Math.round(el('btn-arm').getBoundingClientRect().bottom) : null
  };
}"""


def main() -> int:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1228, "height": 677})
        page.goto(URL, wait_until="load")
        page.wait_for_timeout(2500)
        m = page.evaluate(PROBE)
        print("INITIAL " + str(m))
        print(
            "  no_page_scroll_v = "
            + str(m["pageScrollH"] <= m["innerH"] + 1)
            + " no_page_scroll_h = "
            + str(m["pageScrollW"] <= m["innerW"] + 1)
        )

        page.click("#tab-takes")
        page.wait_for_timeout(400)
        m2 = page.evaluate(PROBE)
        panes = m2["pane"]
        print(
            "PHRASES_OPEN pane="
            + str(panes)
            + " pane_scrolls_internally="
            + str(
                bool(
                    panes
                    and panes["scrollH"] > panes["clientH"]
                    and panes["overflow"] == "auto"
                )
            )
            + " page_still_no_scroll="
            + str(m2["pageScrollH"] <= m2["innerH"] + 1)
        )

        chosen = page.evaluate(
            "() => { const s = document.getElementById('sel-g1'); s.selectedIndex = 1; const v = s.value; s.dispatchEvent(new Event('change')); return v; }"
        )
        page.wait_for_timeout(1500)
        m3 = page.evaluate(PROBE)
        print(
            "G1_SWITCH chose="
            + str(chosen)
            + " chip_now="
            + str(m3["chipG1"])
            + " server_confirmed="
            + str((m3["chipG1"] or "") == chosen)
            + " note=["
            + str(m3["noteG1"])
            + "]"
        )

        page.select_option("#sel-phrase", "play some music")
        page.wait_for_timeout(300)
        m4 = page.evaluate(PROBE)
        print("PHRASE_SELECT note=[" + str(m4["notePhrase"]) + "]")

        page.click(
            "#tab-phrases"
        )  # the recordings tab took over the pane; go back first
        page.click("#ph-list li:nth-child(4)")
        page.wait_for_timeout(300)
        m5 = page.evaluate(PROBE)
        print(
            "PHRASE_CLICK note=["
            + str(m5["notePhrase"])
            + "] list_selected="
            + str(
                page.evaluate(
                    "() => document.querySelectorAll('#ph-list li.sel').length"
                )
            )
        )
        print(
            "COUNTS g1="
            + str(m5["g1Options"])
            + " g2="
            + str(m5["g2Options"])
            + " phrases="
            + str(m5["phraseOptions"])
            + " items="
            + str(m5["phraseItems"])
            + " arm_bottom="
            + str(m5["armBottom"])
            + " innerH="
            + str(m5["innerH"])
        )
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
