"""Probe: room simulation tells the weather, the time, and which color was taken."""
import asyncio
import json

from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8765/room_sim.html"


async def click_demo(page, match, exact=False):
    return await page.evaluate(
        """(args) => {
          const btn = [...document.querySelectorAll('#demos button')]
            .find(b => args.exact ? b.textContent === args.match : b.textContent.includes(args.match));
          if (btn) { btn.click(); return true; }
          return false;
        }""", {"match": match, "exact": exact})


async def main():
    r = {}
    errs = []
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge")
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        r["demos"] = await page.evaluate("[...document.querySelectorAll('#demos button')].map(b => b.textContent)")

        # TIME (already existed; system clock, no API)
        await click_demo(page, "Time", exact=True)
        await page.wait_for_timeout(400)
        r["time_info"] = ((await page.text_content("#infotext")) or "").strip()

        # WEATHER via keyless Open-Meteo
        await click_demo(page, "Weather")
        await page.wait_for_timeout(4500)
        r["weather_info"] = ((await page.text_content("#infotext")) or "").strip()
        r["weather_subtitle"] = ((await page.text_content("#room-subtitle-text")) or "").strip()

        # COLOR demo -> bulb takes the color + info panel states it
        await click_demo(page, "Color", exact=True)
        await page.wait_for_timeout(300)
        r["color_info"] = ((await page.text_content("#infotext")) or "").strip()
        r["bulb_color"] = await page.evaluate("getComputedStyle(document.getElementById('bulb')).getPropertyValue('--bulb-color').trim()")

        # what color was taken (query)
        await click_demo(page, "What color")
        await page.wait_for_timeout(300)
        r["whatcolor_info"] = ((await page.text_content("#infotext")) or "").strip()

        r["page_errors"] = errs[:3]
        ok = (":" in r["time_info"]
              and "°C" in r["weather_info"] and "demo" not in r["weather_info"]
              and "Light color" in r["color_info"] and r["bulb_color"]
              and "Light color" in r["whatcolor_info"])
        print(json.dumps(r, indent=1))
        print("ROOM-PROBE:", "PASS" if ok else "FAIL")
        await browser.close()
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
