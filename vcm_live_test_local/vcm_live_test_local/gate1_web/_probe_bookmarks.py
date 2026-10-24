"""Probe: top-5 combination bookmarks render and apply settings end-to-end."""
import asyncio
import json

from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8765/"


async def main():
    r = {}
    errs = []
    sent = []
    received = []
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge")
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))

        def on_ws(ws):
            def on_sent(p):
                if isinstance(p, str):
                    try:
                        sent.append(json.loads(p))
                    except ValueError:
                        pass

            def on_recv(p):
                if isinstance(p, str):
                    try:
                        received.append(json.loads(p))
                    except ValueError:
                        pass
            ws.on("framesent", on_sent)
            ws.on("framereceived", on_recv)

        page.on("websocket", on_ws)
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_function(
            "document.getElementById('status') && /connected/.test(document.getElementById('status').textContent)",
            timeout=20000)
        await page.wait_for_function(
            "document.querySelectorAll('#all-topcombos button').length >= 5", timeout=20000)
        r["button_count"] = await page.evaluate("document.querySelectorAll('#all-topcombos button').length")
        r["labels"] = (await page.evaluate(
            "[...document.querySelectorAll('#all-topcombos button')].map(b => b.textContent)"))[:3]
        combos = await page.evaluate("window.VCM_TOP_COMBOS || []")
        r["data_count"] = len(combos)
        b = combos[0] if combos else {}
        r["bm1"] = {"g1": b.get("g1"), "g2": b.get("g2"), "arch": b.get("arch"), "nc": b.get("nc")}

        await page.locator("#all-topcombos button").nth(0).click()
        await page.wait_for_timeout(900)
        r["g1_after"] = await page.evaluate("document.getElementById('all-g1model').value")
        r["g2_after"] = await page.evaluate("document.getElementById('all-g2model').value")
        r["arch_after"] = await page.evaluate("document.getElementById('all-arch').value")
        r["nc_after"] = await page.evaluate("(document.getElementById('all-noise-canceller')||{}).textContent")
        r["stage_label"] = await page.evaluate("(document.getElementById('all-stage-g2-label')||{}).textContent")
        r["bm_status"] = await page.evaluate("(document.getElementById('all-topcombos-status')||{}).textContent")
        r["ticker_status"] = await page.evaluate("(document.getElementById('status')||{}).textContent")
        r["sent_types"] = sorted({str(m.get("type")) for m in sent if isinstance(m, dict) and m.get("type")})
        r["g2_sent"] = any(m.get("type") == "g2model" and m.get("model") == b.get("g2") for m in sent)
        r["ack_g2"] = any(m.get("type") == "g2model" and m.get("model") == b.get("g2") for m in received)

        # second click: a bookmark with a DIFFERENT architecture proves arch switching
        alt = next((x for x in combos if x.get("arch") != b.get("arch")), None)
        r["alt_exists"] = alt is not None
        if alt:
            idx = combos.index(alt)
            await page.locator("#all-topcombos button").nth(idx).click()
            await page.wait_for_timeout(900)
            r["arch_after2"] = await page.evaluate("document.getElementById('all-arch').value")
            r["ack_arch2"] = any(m.get("type") == "arch" and m.get("arch") == alt.get("arch") for m in received)
            r["stage_label2"] = await page.evaluate("(document.getElementById('all-stage-g2-label')||{}).textContent")

        # restore the GLOBAL gate2 model to the default (it is shared server-wide)
        await page.select_option("#all-g2model", "gate2v56_v54")
        await page.wait_for_timeout(500)

        r["page_errors"] = errs[:3]
        ok = (r["button_count"] >= 5 and r["data_count"] >= 5
              and r["g1_after"] == b.get("g1") and r["g2_after"] == b.get("g2")
              and r["arch_after"] == str(b.get("arch"))
              and r["g2_sent"] and r["ack_g2"]
              and ("applied" in r["bm_status"] or "active" in r["bm_status"]))
        if alt:
            ok = ok and r["arch_after2"] == str(alt.get("arch")) and r["ack_arch2"]
        print(json.dumps(r, indent=1))
        print("BOOKMARK-PROBE:", "PASS" if ok else "FAIL")
        await browser.close()
        return 0 if ok else 1


asyncio.run(main())
