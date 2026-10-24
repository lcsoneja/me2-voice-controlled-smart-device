"""Behavioral probe: select-all/clear-all/quick-set + play/pause/resume/stop controls."""
import asyncio
import json

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
        page.on("pageerror", lambda e: errs.append(str(e)[:300]))
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(1200)
        await page.click("#all-recframe-toggle")
        await page.wait_for_timeout(900)
        # wait for checkbox lists to populate
        await page.wait_for_function("document.querySelectorAll('#rf-g1box input').length > 0", timeout=8000)

        r["btns_present"] = await page.evaluate("""['rf-play','rf-pause','rf-stopaudio','rf-reset','rf-selectall','rf-clearall','rf-quickset']
            .map(id => [id, !!document.getElementById(id)])""")
        r["g1_total"] = await page.evaluate("document.querySelectorAll('#rf-g1box input').length")
        r["g2_total"] = await page.evaluate("document.querySelectorAll('#rf-mbox input').length")

        await page.click("#rf-selectall")
        await page.wait_for_timeout(200)
        r["after_selectall"] = await page.evaluate(
            "document.querySelectorAll('#rf-g1box input:checked').length + '/' + document.querySelectorAll('#rf-mbox input:checked').length")
        r["say_selectall"] = await page.evaluate("document.getElementById('rf-say').textContent")

        await page.click("#rf-clearall")
        await page.wait_for_timeout(200)
        r["after_clearall"] = await page.evaluate(
            "document.querySelectorAll('#rf-g1box input:checked').length + '/' + document.querySelectorAll('#rf-mbox input:checked').length")

        await page.click("#rf-quickset")
        await page.wait_for_timeout(200)
        r["after_quickset"] = await page.evaluate(
            "document.querySelectorAll('#rf-g1box input:checked').length + '/' + document.querySelectorAll('#rf-mbox input:checked').length")
        r["pause_disabled_initial"] = await page.evaluate("document.getElementById('rf-pause').disabled")

        # --- audio playback test (needs a saved take) ---
        has_take = await page.evaluate("document.querySelectorAll('#rf-rec option').length > 0")
        if has_take:
            await page.select_option("#rf-rec", index=0)
            await page.click("#rf-play")
            await page.wait_for_timeout(1500)
            r["t1_playing"] = await page.evaluate(
                "(function(){var a=window.RF_AUDIO_PROBE||(document.querySelector('audio')&&null);return null;})(),"
                " (typeof RF!=='undefined') ? 'RF-private' : 'no-RF'")
            # use the pause button's own state + audio element state via public DOM signals
            r["pause_btn_after_play"] = await page.evaluate("document.getElementById('rf-pause').textContent")
            r["pause_btn_disabled"] = await page.evaluate("document.getElementById('rf-pause').disabled")
            await page.click("#rf-pause")
            await page.wait_for_timeout(400)
            r["pause_btn_after_pause"] = await page.evaluate("document.getElementById('rf-pause').textContent")
            r["say_after_pause"] = await page.evaluate("document.getElementById('rf-say').textContent")
            await page.click("#rf-play")   # should RESUME, not restart
            await page.wait_for_timeout(400)
            r["say_after_resume"] = await page.evaluate("document.getElementById('rf-say').textContent")
            await page.click("#rf-stopaudio")
            await page.wait_for_timeout(300)
            r["say_after_stop"] = await page.evaluate("document.getElementById('rf-say').textContent")
            r["play_btn_after_stop"] = await page.evaluate("document.getElementById('rf-play').textContent")
        else:
            r["audio_test"] = "skipped — no saved takes"

        r["pageerrors"] = errs or "none"
        await browser.close()
    print(json.dumps(r, indent=2))

asyncio.run(main())
