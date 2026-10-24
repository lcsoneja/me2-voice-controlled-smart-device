"""E2E probe of the Recording Test frame (recframe) in the dashboard."""
import asyncio
import json

from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8765/pipeline_all_in_one.html"

async def main():
    result = {}
    errs, console, http_fail = [], [], []
    async with async_playwright() as pw:
        launch_args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
        try:
            browser = await pw.chromium.launch(headless=True, args=launch_args)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge", args=launch_args)
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:300]))
        page.on("console", lambda m: console.append(m.type + ":" + m.text[:200]) if m.type == "error" else None)
        page.on("response", lambda r: http_fail.append(str(r.status) + " " + r.url) if r.status >= 400 else None)
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        result["toggle_present"] = await page.locator("#all-recframe-toggle").count()
        if result["toggle_present"]:
            await page.locator("#all-recframe-toggle").click()
            await page.wait_for_timeout(1200)
        result["recframe_display"] = await page.evaluate(
            "getComputedStyle(document.getElementById('recframe')).display")

        result["rec_options"] = await page.evaluate(
            "document.getElementById('rf-rec') ? document.getElementById('rf-rec').options.length : -1")
        result["reccount"] = await page.evaluate(
            "document.getElementById('rf-reccount') ? document.getElementById('rf-reccount').textContent : '?'")
        result["g1count"] = await page.evaluate(
            "document.getElementById('rf-g1count') ? document.getElementById('rf-g1count').textContent : '?'")
        result["mcount"] = await page.evaluate(
            "document.getElementById('rf-mcount') ? document.getElementById('rf-mcount').textContent : '?'")

        if result["rec_options"] and result["rec_options"] > 0:
            await page.evaluate(
                "var s=document.getElementById('rf-rec'); s.selectedIndex=0; s.dispatchEvent(new Event('change'))")
            await page.wait_for_timeout(300)
        await page.evaluate(
            "var gb=document.getElementById('rf-g1box'); if(gb){var i=gb.querySelector('input'); if(i) i.checked=true;}"
            "var mb=document.getElementById('rf-mbox'); if(mb){var j=mb.querySelector('input'); if(j) j.checked=true;}")

        result["start_present"] = await page.locator("#rf-start").count()
        if result["start_present"]:
            await page.locator("#rf-start").click()
            prog = ""
            for _ in range(40):
                await page.wait_for_timeout(500)
                prog = await page.evaluate(
                    "document.getElementById('rf-prog') ? document.getElementById('rf-prog').textContent : ''")
                if ("done" in prog) or ("error" in prog) or ("failed" in prog) or ("lost" in prog):
                    break
            result["prog"] = prog
        result["results_cards"] = await page.evaluate(
            "document.getElementById('rf-results') ? document.getElementById('rf-results').children.length : -1")
        result["say"] = await page.evaluate(
            "document.getElementById('rf-say') ? document.getElementById('rf-say').textContent : ''")
        result["pageerrors"] = errs[:6] if errs else "none"
        result["console_errs"] = console[:6]
        result["http_fail"] = http_fail[:6]
        await browser.close()
    print(json.dumps(result, indent=2))
    if errs or result.get("recframe_display") != "block" or result.get("results_cards", 0) == 0:
        raise SystemExit(1)

asyncio.run(main())

