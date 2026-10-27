"""Find what widens the stage panel beyond its client width."""

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/oneshot.html"

PROBE = """() => {
  const panel = document.querySelector('.panel.stage');
  const out = [];
  panel.querySelectorAll('*').forEach(e => {
    if (e.scrollWidth > panel.clientWidth + 1) {
      out.push({
        tag: e.tagName,
        id: e.id || '',
        cls: (e.className && typeof e.className === 'string') ? String(e.className).slice(0, 24) : '',
        sw: e.scrollWidth,
        cw: e.clientWidth,
        text: (e.textContent || '').slice(0, 30)
      });
    }
  });
  return out;
}"""


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1228, "height": 677})
        page.goto(URL, wait_until="load")
        page.wait_for_selector("#ph-list li", timeout=60000)
        panel = page.evaluate(
            "() => { const p = document.querySelector('.panel.stage'); "
            "return p.clientWidth + '/' + p.scrollWidth; }"
        )
        wide = page.evaluate(PROBE)
        print("PANEL=" + str(panel))
        for item in wide[:12]:
            print(
                str(item["tag"])
                + " #"
                + item["id"]
                + " ."
                + item["cls"]
                + " sw="
                + str(item["sw"])
                + "/"
                + str(item["cw"])
                + " "
                + repr(item["text"])
            )
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
