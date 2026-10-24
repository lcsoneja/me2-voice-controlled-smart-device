"""Click-open + scenario quick-pick probe (Edge fallback)."""
import asyncio, json
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8765/pipeline_all_in_one.html"

async def main():
    r = {}
    errs = []
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge")
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(1200)
        await page.click("#all-recframe-toggle")
        await page.wait_for_timeout(900)
        r["display"] = await page.evaluate("getComputedStyle(document.getElementById('recframe')).display")
        r["rect"] = await page.evaluate(
            "(() => { const b = document.getElementById('recframe').getBoundingClientRect();"
            " return { top: Math.round(b.top), inViewport: b.top < window.innerHeight && b.bottom > 0 }; })()")
        r["btn_label"] = await page.evaluate("document.getElementById('all-recframe-toggle').textContent")
        try:
            await page.wait_for_function("document.querySelectorAll('#rf-rec option').length > 0", timeout=8000)
        except Exception:
            pass
        r["takes"] = await page.evaluate("document.querySelectorAll('#rf-rec option').length")
        r["scn_buttons"] = await page.evaluate("document.querySelectorAll('#rf-scn button').length")
        s2 = page.locator('#rf-scn button[data-scn="S2"]')
        if await s2.count():
            r["s2_disabled"] = await s2.is_disabled()
            if not r["s2_disabled"]:
                await s2.click()
                await page.wait_for_timeout(300)
                r["s2_pick"] = await page.evaluate(
                    "(() => { const s = document.getElementById('rf-rec');"
                    " return s.selectedOptions[0] ? s.selectedOptions[0].textContent : ''; })()")
        r["pageerrors"] = errs or "none"
        await browser.close()
    print(json.dumps(r, indent=2))
    ok = (not errs and r["display"] == "block" and r["rect"]["inViewport"]
          and r["scn_buttons"] == 6 and str(r.get("s2_pick", "")).startswith("scenario S2"))
    if not ok:
        raise SystemExit(1)

asyncio.run(main())
