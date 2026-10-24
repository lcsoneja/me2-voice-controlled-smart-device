"""Probe: Architecture v1/v2 naming across the recording test frame."""
import asyncio
import io
import json
import sys

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
DASH = BASE + "/pipeline_all_in_one.html"
PASSED = True


def check(name, cond, detail=None):
    global PASSED
    PASSED = PASSED and bool(cond)
    text = "" if detail in ("", None, [], {}) else str(detail)
    print(("PASS " if cond else "FAIL ") + name + (("  " + text) if text else ""))


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

        sel = await page.evaluate("""() => {
          const s = document.getElementById('rf-gatemode');
          const lab = s ? s.closest('label') : null;
          return { label: lab ? (lab.textContent || '').trim().slice(0, 30) : '',
                   options: s ? Array.from(s.options).map(o => o.textContent) : [] };
        }""")
        check("select labeled Architecture", sel["label"].startswith("Architecture"), sel["label"])
        opts = sel["options"]
        check("options use v1/v2 naming",
              any("v1 — all gates run" in o for o in opts) and
              any("v2 — G1 first" in o for o in opts) and
              any("v1 + v2 (A/B)" in o for o in opts), json.dumps(opts))

        await page.select_option("#rf-rec", "20261023_155245_2dd71e")
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
        await page.click("#rf-start")
        summ = ""
        for _ in range(60):
            summ = await page.evaluate("() => (document.getElementById('rf-summary') || {}).innerText || ''")
            if "Summary — expected wake:" in summ and "combinations ·" in summ:
                break
            await page.wait_for_timeout(500)
        check("summary shows Architecture A/B", "Architecture A/B (v1 + v2)" in summ, summ[:90].replace("\n", " | "))

        picker = await page.evaluate("""() => {
          const opts = Array.from(document.querySelectorAll('#rf-summary select option')).map(o => o.textContent);
          return { hasV1: opts.some(t => t.indexOf('Arch v1') >= 0),
                   hasV2: opts.some(t => t.indexOf('Arch v2') >= 0), n: opts.length };
        }""")
        check("lane picker labels Arch v1/v2", picker["hasV1"] and picker["hasV2"], json.dumps(picker))

        results = await page.evaluate("() => (document.getElementById('rf-results') || {}).innerText || ''")
        check("cards label Arch v1/v2", ("· Arch v1" in results) and ("· Arch v2" in results))

        best = ""
        for _ in range(40):
            best = await page.evaluate("() => (document.getElementById('rf-best') || {}).innerText || ''")
            if "Recommended for demo" in best or "run a test" in best:
                break
            await page.wait_for_timeout(400)
        check("best block renders", "Best combination across runs" in best, best[:70].replace("\n", " | "))
        check("best banner labels Arch", ("· Arch v1" in best) or ("· Arch v2" in best), best[:100].replace("\n", " | "))

        check("no page errors", not errs, json.dumps(errs)[:200])
        await browser.close()
    print("OVERALL: " + ("PASS" if PASSED else "FAIL"))


asyncio.run(main())
