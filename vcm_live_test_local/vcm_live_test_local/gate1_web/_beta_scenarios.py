"""Beta-tester scenario suite for the VCM dashboard (run against the live server).

Usage:  python _beta_scenarios.py
Each scenario prints PASS/FAIL with evidence; exit code 0 only if all pass.
"""
import asyncio
import json
import sys
from contextlib import suppress

from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8765/pipeline_all_in_one.html"
API = "http://127.0.0.1:8765"

async def main():
    out = {"pass": [], "fail": [], "notes": []}
    errs, console_errs, http_fail = [], [], []

    def check(name, ok, detail=""):
        (out["pass"] if ok else out["fail"]).append(f"{name}: {detail}")

    async with async_playwright() as pw:
        args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
        try:
            browser = await pw.chromium.launch(headless=True, args=args)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge", args=args)
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:300]))
        page.on("console", lambda m: console_errs.append(m.text[:200]) if m.type == "error" else None)
        page.on("response", lambda r: http_fail.append(f"{r.status} {r.url}") if r.status >= 400 else None)
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        # S1 page loads with no uncaught JS errors
        check("S1 load without pageerror", not errs, "; ".join(errs))

        # S2 the recording-test frame opens as a REAL modal (fixed overlay, on screen)
        await page.locator("#all-recframe-toggle").click()
        await page.wait_for_timeout(800)
        vis = await page.evaluate("""() => {
            const f = document.getElementById('recframe');
            const cs = getComputedStyle(f);
            const r = f.getBoundingClientRect();
            const inVp = r.top < innerHeight && r.bottom > 0 && r.left < innerWidth && r.right > 0;
            return {display: cs.display, position: cs.position, z: cs.zIndex,
                    rect: [r.top|0, r.left|0, r.width|0, r.height|0], inViewport: inVp,
                    btn: document.getElementById('all-recframe-toggle').textContent};
        }""")
        check("S2 modal display=block", vis["display"] == "block", json.dumps(vis))
        check("S2 modal position=fixed", vis["position"] == "fixed", vis["position"])
        check("S2 modal covers viewport", vis["inViewport"], str(vis["rect"]))
        check("S2 toggle label swapped", "Close" in vis["btn"], vis["btn"])

        # S3 saved takes loaded
        nrec = await page.evaluate("document.getElementById('rf-rec') ? document.getElementById('rf-rec').options.length : -1")
        check("S3 recordings loaded", nrec > 0, f"{nrec} options")

        # S4 back button closes the modal
        await page.locator("#recframe-back").click()
        await page.wait_for_timeout(300)
        disp = await page.evaluate("getComputedStyle(document.getElementById('recframe')).display")
        check("S4 back closes modal", disp == "none", disp)

        # S5 full test-job flow through the UI: select take, run, poll, render gantt
        await page.locator("#all-recframe-toggle").click()
        await page.wait_for_timeout(500)
        await page.evaluate("""() => {
            const sel = document.getElementById('rf-rec');
            if (sel.options.length) sel.selectedIndex = 0;
            sel.dispatchEvent(new Event('change'));
        }""")
        await page.evaluate("""() => {
            document.querySelectorAll('#rf-g1box input').forEach((c, i) => c.checked = i < 2);
            document.querySelectorAll('#rf-mbox input').forEach((c, i) => c.checked = i < 2);
            document.querySelectorAll('#rf-g1box input, #rf-mbox input')
                .forEach(c => c.dispatchEvent(new Event('change')));
        }""")
        await page.locator("#rf-start").click()
        with suppress(Exception):
            await page.wait_for_function(
                "() => /^(done in|error:|job lost)/.test(document.getElementById('rf-prog').textContent)",
                timeout=90000)
        prog = await page.evaluate("document.getElementById('rf-prog').textContent")
        cards = await page.evaluate("document.querySelectorAll('#rf-results canvas').length")
        drawn = await page.evaluate("""() => {
            const cv = document.querySelector('#rf-results canvas');
            if (!cv) return false;
            const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data;
            for (let i = 3; i < d.length; i += 40) if (d[i] !== 0) return true;
            return false;
        }""")
        check("S5 test job finished", prog.startswith(("done in", "error:")), prog)
        check("S5 gantt cards rendered", cards > 0, f"{cards} canvases")
        check("S5 gantt has real pixels", drawn, "")
        if not prog.startswith(("done in", "error:")):
            out["notes"].append("S5 job did not reach terminal state in 90s: " + prog)

        # S6 client-error flight recorder reaches the server diag log
        await page.evaluate("window.VCM_UI_ERRORS && window.VCM_UI_ERRORS.report('beta-probe', 'synthetic probe error')")
        await page.wait_for_timeout(700)
        # S6 fetch the diag ring from inside the page, the way the UI would
        diag = await page.evaluate("""async () => {
            const r = await fetch('/api/diag?last=10');
            return { ok: r.ok, body: await r.json() };
        }""")
        body = (diag.get("body") or {}) if diag.get("ok") else {}
        kinds = [entry.get("kind", "") for entry in (body.get("lines") or [])]
        check("S6 client-error in diag ring", "beta-probe" in kinds, str(kinds[-5:]))

        # S7 Esc closes the modal
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
        disp = await page.evaluate("getComputedStyle(document.getElementById('recframe')).display")
        check("S7 Esc closes modal", disp == "none", disp)

        # S8 the whole run stayed clean
        check("S8 no pageerror during run", not errs, "; ".join(errs))
        if console_errs:
            out["notes"] += [f"console.error: {c}" for c in console_errs[:8]]
        if http_fail:
            out["notes"] += [f"http>=400: {h}" for h in http_fail[:8]]
        await browser.close()

    print(json.dumps(out, indent=1))
    return 0 if not out["fail"] else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
