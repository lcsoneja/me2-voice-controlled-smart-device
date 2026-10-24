"""Probe: main-action dropdown + phrases info panel (dash + lab)."""
import asyncio
import json

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8765"
PASSED = True


def check(name, cond, detail=None):
    global PASSED
    PASSED = PASSED and bool(cond)
    text = "" if detail in ("", None, [], {}) else str(detail)
    print(("PASS " if cond else "FAIL ") + name + (("  " + text) if text else ""))


DL_RF = "() => Array.from(document.querySelectorAll('#rf-actions option')).map(o => o.value)"
DL_LAB = "() => Array.from(document.querySelectorAll('#lab-actions option')).map(o => o.value)"


async def main():
    errs = []
    args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True, args=args)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge", args=args)
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append("dash: " + str(e)[:160]))
        await page.goto(BASE + "/pipeline_all_in_one.html")
        await page.click("#all-recframe-toggle")
        await page.wait_for_selector("#rf-recpane > div", timeout=15000)

        opts = await page.evaluate(DL_RF)
        check("dash datalist lists 20 actions", len(opts) == 20, len(opts))
        check("dash tag action uses dropdown",
              (await page.evaluate("() => document.getElementById('rf-tagaction').getAttribute('list')")) == "rf-actions")
        check("dash recorder action uses dropdown",
              (await page.evaluate("() => document.getElementById('rf-recaction').getAttribute('list')")) == "rf-actions")

        await page.click("#rf-phrasebtn")
        await page.wait_for_timeout(250)
        vis = await page.evaluate("() => document.getElementById('rf-phrasepanel').style.display")
        txt = await page.evaluate("() => document.getElementById('rf-phrasepanel').innerText")
        check("dash info opens phrases panel", vis == "block", vis)
        check("dash panel shows timer_set phrase", "set a timer for five minutes" in txt)
        check("dash default wake prefix is [wake]", "[wake], set a timer for five minutes" in txt)

        await page.fill("#rf-tagaction", "timer_set")
        await page.wait_for_timeout(300)
        first = await page.evaluate("() => (document.querySelector('#rf-phrasepanel b.rfpk') || {}).textContent")
        check("dash selected action shown first", first == "timer_set", first)

        await page.select_option("#rf-tagwake", "Nova")
        await page.wait_for_timeout(300)
        txt = await page.evaluate("() => document.getElementById('rf-phrasepanel').innerText")
        check("dash phrases use chosen wake word", "Nova, set a timer for five minutes" in txt)

        await page.click("#rf-recinfo")
        await page.wait_for_timeout(200)
        check("dash recorder info keeps panel open",
              (await page.evaluate("() => document.getElementById('rf-phrasepanel').style.display")) == "block")
        await page.close()

        lab = await browser.new_page()
        lab.on("pageerror", lambda e: errs.append("lab: " + str(e)[:160]))
        await lab.goto(BASE + "/recording_lab.html")
        await lab.wait_for_selector("#reclist label", timeout=15000)
        lopts = await lab.evaluate(DL_LAB)
        check("lab datalist lists 20 actions", len(lopts) == 20, len(lopts))
        await lab.click("#lab-phrasebtn")
        await lab.wait_for_timeout(250)
        lvis = await lab.evaluate("() => document.getElementById('lab-phrasepanel').style.display")
        check("lab info opens phrases panel", lvis == "block", lvis)
        await lab.fill("#tagAction", "lights_on")
        await lab.wait_for_timeout(300)
        lfirst = await lab.evaluate("() => (document.querySelector('#lab-phrasepanel b.rfpk') || {}).textContent")
        check("lab selected action shown first", lfirst == "lights_on", lfirst)
        await lab.click("#recInfo")
        await lab.wait_for_timeout(200)
        check("lab recorder info opens panel",
              (await lab.evaluate("() => document.getElementById('lab-phrasepanel').style.display")) == "block")
        await lab.close()
        await browser.close()

    check("no page errors", not errs, json.dumps(errs)[:220])
    print("OVERALL: " + ("PASS" if PASSED else "FAIL"))


if __name__ == "__main__":
    asyncio.run(main())
