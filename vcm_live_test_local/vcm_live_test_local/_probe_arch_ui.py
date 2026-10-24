"""Probe: Pipeline test header - default Gate 2 model, build badge, architecture selector wiring."""
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
            def on_recv(p):
                if isinstance(p, str):
                    try:
                        received.append(json.loads(p))
                    except ValueError:
                        pass
            def on_sent(p):
                if isinstance(p, str):
                    try:
                        sent.append(json.loads(p))
                    except ValueError:
                        pass
            ws.on("framereceived", on_recv)
            ws.on("framesent", on_sent)

        page.on("websocket", on_ws)
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_selector("#all-arch", timeout=15000)
        await page.wait_for_selector("#build-badge", timeout=5000)

        async def wait_arch(n, timeout=10.0):
            for _ in range(int(timeout * 5)):
                if any(m.get("type") == "arch" and m.get("arch") == n for m in received):
                    return True
                await page.wait_for_timeout(200)
            return False

        r["default_g2"] = await page.evaluate("document.getElementById('all-g2model').value")
        r["badge"] = ((await page.text_content("#build-badge")) or "").strip()
        r["arch_opts"] = await page.eval_on_selector_all("#all-arch option", "els => els.map(e => e.value)")
        r["g2count"] = await page.evaluate("document.querySelectorAll('#all-g2model option').length")
        r["has67"] = await page.evaluate("!!document.querySelector('#all-g2model option[value=\"gate2v67_timeshift_only\"]')")
        r["has58"] = await page.evaluate("!!document.querySelector('#all-g2model option[value=\"gate2v58_smooth_pidgate\"]')")

        await page.select_option("#all-arch", "1")
        r["ack_v2"] = await wait_arch(1)
        r["label_v2"] = ((await page.text_content("#all-stage-g2-label")) or "").strip()
        await page.select_option("#all-arch", "0")
        r["ack_v1"] = await wait_arch(0)
        r["label_v1"] = ((await page.text_content("#all-stage-g2-label")) or "").strip()

        r["rf_opts"] = await page.eval_on_selector_all("#rf-gatemode option", "els => els.map(e => e.value)")
        r["page_errors"] = errs[:3]
        ok = (r["default_g2"] == "gate2v56_v54" and "2026-10-24" in r["badge"]
              and r["arch_opts"] == ["0", "1", "2"] and r["has67"] and r["has58"]
              and r["ack_v2"] and r["ack_v1"]
              and "only after wake" in r["label_v2"] and "all gates run" in r["label_v1"]
              and r["g2count"] >= 62 and len(r["rf_opts"]) >= 5)
        print(json.dumps(r, indent=1))
        print("UI-PROBE:", "PASS" if ok else "FAIL")
        await browser.close()
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
