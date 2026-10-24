"""Probe: batch test names the architecture axis - real 1-take mini batch (arch v1+v2+v3)."""
import asyncio
import json

from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8765/"


# pi-lens-ignore: Pyright:reportAttributeAccessIssue
async def main():
    r = {}
    errs = []
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge")
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await page.goto(URL, wait_until="domcontentloaded")
        await page.click("#all-recframe-toggle")
        await page.wait_for_selector("#rf-rec", timeout=20000)
        await page.wait_for_selector("#rf-g1box input[type=checkbox]", timeout=20000)
        await page.wait_for_selector("#rf-mbox input[type=checkbox]", timeout=20000)
        await page.wait_for_function("document.querySelectorAll('#rf-rec option').length > 0", timeout=30000)
        await page.wait_for_timeout(800)

        picked = await page.evaluate("""() => {
          const keepFirst = (sel) => {
            const boxes = [...document.querySelectorAll(sel + ' input[type="checkbox"]')];
            boxes.forEach((b, i) => { b.checked = i === 0; });
            return boxes.length;
          };
          const rec = document.querySelector('#rf-rec');
          const opt = [...rec.options].find((o) => o.value);
          if (opt) rec.value = opt.value;
          return { g1_total: keepFirst('#rf-g1box'), model_total: keepFirst('#rf-mbox'),
                   g1_left: document.querySelectorAll('#rf-g1box input:checked').length,
                   model_left: document.querySelectorAll('#rf-mbox input:checked').length,
                   take: rec.value || null };
        }""")
        r["picked"] = picked
        if not picked.get("take"):
            print(json.dumps(r, indent=1))
            print("UI-PROBE: FAIL (no take selected)")
            await browser.close()
            return 1

        await page.select_option("#rf-gatemode", "all")
        await page.select_option("#rf-ncmode", "off")
        await page.select_option("#rf-fsource", "me2w")
        await page.wait_for_timeout(400)
        r["filtered_rows"] = await page.evaluate("document.querySelectorAll('#rf-recpane > div').length")
        await page.select_option("#rf-fsource", "")
        await page.click("#rf-batchstart")
        header_ok = False
        r["timeline"] = []
        for _ in range(20):  # 20 x 1 s = 20 s budget
            await page.wait_for_timeout(1000)
            st = await page.evaluate("""() => ({
              say: (document.getElementById('rf-say')||{}).textContent || '',
              prog: (document.getElementById('rf-prog')||{}).textContent || '',
              head: ((document.querySelector('#rf-results')||{}).textContent || '').slice(0, 80),
              progressShown: (document.getElementById('rf-progress')||{}).style ? (document.getElementById('rf-progress').style.display !== 'none') : false,
              progressText: (document.getElementById('rf-progress-text')||{}).textContent || ''
            })""")
            if st.get("progressShown"):
                r["progress_seen"] = r.get("progress_seen", 0) + 1
                if not r.get("progress_sample"):
                    r["progress_sample"] = st.get("progressText", "")
            if "Batch: 1/1" in (st.get("head") or ""):
                header_ok = True
                break
            r["timeline"].append(st)
        r["header_ok"] = header_ok
        if not header_ok:
            print(json.dumps(r, indent=1))
            print("UI-PROBE: FAIL (batch header never appeared)")
            await browser.close()
            return 1
        r["workers_sel"] = await page.evaluate("!!document.getElementById('rf-workers')")
        r["find_input"] = await page.evaluate("!!document.getElementById('rf-find')")
        r["batch_header"] = await page.evaluate("document.querySelector('#rf-results').firstElementChild.textContent")
        r["results_text"] = (await page.text_content("#rf-results") or "")[:1200]
        r["chart_canvases"] = await page.evaluate("document.querySelectorAll('#rf-results canvas').length")
        await page.evaluate("() => { const f = document.getElementById('rf-find'); f.value = 'v16'; f.dispatchEvent(new Event('input')); }")
        await page.wait_for_timeout(300)
        r["find_matches"] = await page.evaluate("document.querySelectorAll('#rf-findout button').length")
        await page.evaluate("() => { const f = document.getElementById('rf-find'); f.value = ''; f.dispatchEvent(new Event('input')); }")
        ok = ("arch 3: v1 + v2 + v3" in r["batch_header"]
              and "lanes/take (G1 1 × G2 1 × NC 1 × arch 3" in r["batch_header"]
              and "· arch v1 + v2 + v3" in r["results_text"]
              and r["workers_sel"] and r["find_input"]
              and r["chart_canvases"] >= 3 and r["find_matches"] >= 1
              and r.get("filtered_rows", 0) == 202 and r.get("progress_seen", 0) >= 1)
        r["page_errors"] = errs[:3]
        print(json.dumps(r, indent=1))
        print("UI-PROBE:", "PASS" if ok else "FAIL")
        await browser.close()
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
