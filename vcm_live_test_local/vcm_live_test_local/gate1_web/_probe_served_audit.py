"""Audit: served-HTML markers + screenshot of the opened two-pane frame."""
import asyncio
import io
import json
import sys
import urllib.request

from playwright.async_api import async_playwright


def _force_utf8_stdio() -> None:
    out = sys.stdout if isinstance(sys.stdout, io.TextIOWrapper) else None
    err = sys.stderr if isinstance(sys.stderr, io.TextIOWrapper) else None
    if out is not None:
        out.reconfigure(encoding="utf-8", errors="replace")
    if err is not None:
        err.reconfigure(encoding="utf-8", errors="replace")


_force_utf8_stdio()

BASE = "http://127.0.0.1:8765"
REC = "20261023_155245_2dd71e"

html = urllib.request.urlopen(BASE + "/pipeline_all_in_one.html", timeout=15).read().decode("utf-8", "replace")
markers = ['id="rf-left"', 'id="rf-right"', 'id="rf-gatemode"', 'v3 — G1 first + intent vote',
           'All (v1 + v2 + v3)', 'id="all-actions-toggle"', 'id="rf-best"',
           'id="rf-delselected"', 'id="rf-selall"', 'Recommended for demo',
           'This cannot be undone', 'slot (']
missing = [m for m in markers if m not in html]
print("SERVED bytes:", len(html), "| missing markers:", missing if missing else "NONE")


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


async def main():
    errs = []
    args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            "--autoplay-policy=no-user-gesture-required"]
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True, args=args)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge", args=args)
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:120]))
        await page.goto(BASE + "/pipeline_all_in_one.html")
        await page.click("#all-recframe-toggle")
        await page.wait_for_selector("#rf-recpane > div", timeout=15000)

        await page.select_option("#rf-rec", REC)
        await page.wait_for_timeout(300)
        await page.evaluate("""() => {
          const pick = (boxSel, want) => {
            const box = document.getElementById(boxSel);
            const inputs = Array.from(box.querySelectorAll('input'));
            inputs.forEach(i => { i.checked = false; });
            const hit = inputs.find(i => i.value === want);
            if (hit) { hit.checked = true; hit.dispatchEvent(new Event('change', { bubbles: true })); }
            return !!hit;
          };
          pick('rf-g1box', 'gate1v10_dr'); pick('rf-mbox', 'gate2v16');
        }""")
        await page.select_option("#rf-ncmode", "on")
        await page.select_option("#rf-gatemode", "all")
        await page.click("#rf-start")
        summ = ""
        for _ in range(60):
            summ = await page.evaluate("() => (document.getElementById('rf-summary') || {}).innerText || ''")
            if "Summary — expected wake:" in summ and "combinations ·" in summ:
                break
            await page.wait_for_timeout(500)
        check_lines = []
        def check(name, cond, detail=""):
            check_lines.append(("PASS " if cond else "FAIL ") + name)
            print(("PASS " if cond else "FAIL ") + name + (("  " + str(detail)[:80]) if detail else ""))

        check("summary renders (digest + wake/intent times)",
              "Summary — expected wake:" in summ and "Wake fired at:" in summ)
        picker = await page.evaluate("""() => {
          const opts = Array.from(document.querySelectorAll('#rf-summary select option')).map(o => o.textContent);
          return { v1: opts.some(t => t.indexOf('Arch v1') >= 0),
                   v2: opts.some(t => t.indexOf('Arch v2') >= 0),
                   v3: opts.some(t => t.indexOf('Arch v3') >= 0), n: opts.length };
        }""")
        check("lane picker shows Arch v1/v2/v3", picker["v1"] and picker["v2"] and picker["v3"], json.dumps(picker))
        await page.screenshot(path="_audit_frame.png")
        print("screenshot: gate1_web/_audit_frame.png")
        check("no page errors", not errs, json.dumps(errs)[:120])
        await browser.close()
    for line in check_lines:
        pass
    print("OVERALL: " + ("PASS" if all(l.startswith("PASS") for l in check_lines) and not missing else "FAIL"))


asyncio.run(main())
