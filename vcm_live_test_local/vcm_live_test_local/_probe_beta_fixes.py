"""Probe: beta-tester findings 2+3 fixed — batch headings survive, lanecount follows both selects."""
import asyncio
import json

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8765"
DASH = BASE + "/pipeline_all_in_one.html"
PASSED = True


def check(name, cond, detail=None):
    global PASSED
    PASSED = PASSED and bool(cond)
    text = "" if detail in ("", None, [], {}) else str(detail)
    print(("PASS " if cond else "FAIL ") + name + (("  " + text) if text else ""))


LANECOUNT = "() => (document.getElementById('rf-lanecount') || {}).textContent || ''"


async def main():
    errs = []
    args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True, args=args)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge", args=args)
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:160]))
        await page.goto(DASH)
        await page.click("#all-recframe-toggle")
        await page.wait_for_selector("#rf-recpane > div", timeout=15000)

        picked = await page.evaluate("""() => {
          const pick = (boxSel, want) => {
            const box = document.getElementById(boxSel);
            const inputs = Array.from(box.querySelectorAll('input'));
            inputs.forEach(i => { i.checked = false; });
            const hit = inputs.find(i => i.value === want);
            if (hit) { hit.checked = true; hit.dispatchEvent(new Event('change', { bubbles: true })); }
            return !!hit;
          };
          return { a: pick('rf-g1box', 'gate1v10_dr'), b: pick('rf-mbox', 'gate2v16') };
        }""")
        check("picked 1 g1 + 1 g2", picked["a"] and picked["b"], json.dumps(picked))
        await page.select_option("#rf-ncmode", "off")

        seq = []
        for gmode in ("off", "both", "off"):
            await page.select_option("#rf-gatemode", gmode)
            await page.wait_for_timeout(150)
            seq.append(await page.evaluate(LANECOUNT))
        for nmode in ("both", "off"):
            await page.select_option("#rf-ncmode", nmode)
            await page.wait_for_timeout(150)
            seq.append(await page.evaluate(LANECOUNT))
        exp = ["1 gantt lane", "2 gantt lanes", "1 gantt lane", "2 gantt lanes", "1 gantt lane"]
        check("lanecount follows gate-order select", seq[0] == exp[0] and seq[1] == exp[1] and seq[2] == exp[2], json.dumps(seq[:3]))
        check("lanecount follows NC select", seq[3] == exp[3] and seq[4] == exp[4], json.dumps(seq[3:]))
        await page.select_option("#rf-gatemode", "off")

        checked = await page.evaluate("""() => {
          const cbs = Array.from(document.querySelectorAll('#rf-recpane input[type=checkbox]'));
          cbs.slice(0, 2).forEach(c => { c.checked = true; c.dispatchEvent(new Event('change', { bubbles: true })); });
          return cbs.length;
        }""")
        check("two takes checked", checked >= 2, checked)
        await page.click("#rf-batchstart")
        prog = ""
        for _ in range(90):
            prog = await page.evaluate("() => (document.getElementById('rf-prog') || {}).textContent || ''")
            if "batch done" in prog or "batch stopped" in prog:
                break
            await page.wait_for_timeout(1000)
        check("batch completes", "batch done" in prog, prog)
        heads = await page.evaluate("""() => Array.from(document.querySelectorAll('#rf-results > div')).map(d => (d.firstElementChild || {}).textContent || '')""")
        ones = [h for h in heads if h.startswith("1.")]
        twos = [h for h in heads if h.startswith("2.")]
        check("batch per-take headings survive", len(ones) >= 1 and len(twos) >= 1, json.dumps(heads[:4])[:220])
        secs = await page.evaluate("""() => Array.from(document.querySelectorAll('#rf-results > div')).map(d => ({
          head: (d.firstElementChild || {}).textContent || '',
          hasSummary: d.innerText.indexOf('Summary — expected wake:') >= 0
        }))""")
        sum_secs = [s for s in secs if s["head"].startswith(("1.", "2."))]
        check("sections keep summary content", len(sum_secs) >= 2 and all(s["hasSummary"] for s in sum_secs), json.dumps(sum_secs)[:260])
        check("no page errors", not errs, json.dumps(errs)[:200])
        await browser.close()
    print("OVERALL: " + ("PASS" if PASSED else "FAIL"))


asyncio.run(main())
