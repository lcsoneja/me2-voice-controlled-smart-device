"""Does clicking the recording-test button bring the frame into view?"""
import asyncio, json
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8765/pipeline_all_in_one.html"

async def main():
    r = {}
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge")
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        r["page_height"] = await page.evaluate("document.body.scrollHeight")
        r["scrollY_before"] = await page.evaluate("window.scrollY")
        await page.click("#all-recframe-toggle")
        await page.wait_for_timeout(1200)
        r["scrollY_after"] = await page.evaluate("window.scrollY")
        r["display"] = await page.evaluate("getComputedStyle(document.getElementById('recframe')).display")
        r["rect"] = await page.evaluate(
            "(() => { const b = document.getElementById('recframe').getBoundingClientRect();"
            " return { top: Math.round(b.top), height: Math.round(b.height),"
            " inViewport: b.top < window.innerHeight && b.bottom > 0 }; })()")
        r["btn_label"] = await page.evaluate("document.getElementById('all-recframe-toggle').textContent")
        r["pageerrors"] = errs or "none"
        await browser.close()
    print(json.dumps(r, indent=2))

asyncio.run(main())
