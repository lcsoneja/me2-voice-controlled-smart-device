"""Probe: filters box, delete-selected flow (dialog accepted), rf-best block, latency/cpu in rf-summary."""
import asyncio
import base64
import io
import json
import sys
import urllib.request
import wave

from playwright.async_api import async_playwright


def _force_utf8_stdio() -> None:
    """cp1252 consoles cannot encode emoji/check glyphs; force UTF-8 when possible."""
    out = sys.stdout if isinstance(sys.stdout, io.TextIOWrapper) else None
    err = sys.stderr if isinstance(sys.stderr, io.TextIOWrapper) else None
    if out is not None:
        out.reconfigure(encoding="utf-8", errors="replace")
    if err is not None:
        err.reconfigure(encoding="utf-8", errors="replace")


_force_utf8_stdio()

BASE = "http://127.0.0.1:8765"
DASH = BASE + "/pipeline_all_in_one.html"
PASSED = True


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def delete(path):
    req = urllib.request.Request(BASE + path, method="DELETE")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def check(name, cond, detail=None):
    global PASSED
    PASSED = PASSED and bool(cond)
    text = "" if detail in ("", None, [], {}) else str(detail)
    print(("PASS " if cond else "FAIL ") + name + (("  " + text) if text else ""))


async def main():
    errs = []
    dialogs = []
    args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]

    # pi-lens-ignore: Pyright:reportUndefinedVariable
    for r in get("/api/recordings")["recordings"]:
        if r.get("label") == "ui-delete-probe":
            # pi-lens-ignore: Pyright:reportUndefinedVariable
            delete("/api/recordings/" + r["id"])

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x01\x00" * 16000 * 2)
    scratch = post("/api/recordings", {"label": "ui-delete-probe",
                                       "wav_base64": base64.b64encode(buf.getvalue()).decode()})["recording"]
    print("scratch:", scratch["id"])

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True, args=args)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge", args=args)
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:160]))

        async def on_dialog(d):
            dialogs.append(d.message)
            await d.accept()
        page.on("dialog", on_dialog)

        await page.goto(DASH)
        await page.click("#all-recframe-toggle")
        await page.wait_for_selector("#rf-recpane > div", timeout=15000)

        box = await page.evaluate("""() => {
          const cand = Array.from(document.querySelectorAll('#rf-left div')).filter(d => d.textContent.indexOf('FILTERS') >= 0);
          const innermost = cand.filter(d => !cand.some(o => o !== d && o.contains(d)));
          const b = innermost[0];
          return { box: !!b,
            labelIn: !!(b && b.querySelector('#rf-label')),
            wakeIn: !!(b && b.querySelector('#rf-fwake')),
            actionIn: !!(b && b.querySelector('#rf-faction')),
            searchIn: !!(b && b.querySelector('#rf-fsearch')) };
        }""")
        check("filters box present", box["box"], json.dumps(box)[:150])
        check("all four filters inside the box", box["labelIn"] and box["wakeIn"] and box["actionIn"] and box["searchIn"])

        best = ""
        for _ in range(30):
            best = await page.evaluate("() => (document.getElementById('rf-best') || {}).innerText || ''")
            if "Best combination across runs" in best and ("Recommended for demo" in best or "run a test" in best):
                break
            await page.wait_for_timeout(400)
        check("rf-best block renders", "Best combination across runs" in best, best[:70].replace("\n", " | "))
        check("rf-best winner or hint", "Recommended for demo" in best or "run a test" in best, best[:100].replace("\n", " | "))
        check("rf-best has per-scenario winners", "Best per scenario" in best)

        await page.evaluate("""() => {
          const pick = (boxSel, want) => {
            const box = document.getElementById(boxSel);
            const inputs = Array.from(box.querySelectorAll('input'));
            inputs.forEach(i => { i.checked = false; });
            const hit = inputs.find(i => i.value === want);
            if (hit) { hit.checked = true; hit.dispatchEvent(new Event('change', { bubbles: true })); }
            return !!hit;
          };
          pick('rf-g1box', 'gate1v10_dr'); pick('rf-mbox', 'gate2v16');
        }""")
        await page.select_option("#rf-rec", "20261023_155245_2dd71e")
        await page.wait_for_timeout(300)
        await page.select_option("#rf-ncmode", "on")
        await page.select_option("#rf-gatemode", "off")
        await page.click("#rf-start")
        summ = ""
        for _ in range(60):
            summ = await page.evaluate("() => (document.getElementById('rf-summary') || {}).innerText || ''")
            if "Summary — expected wake:" in summ and "combinations ·" in summ:
                break
            await page.wait_for_timeout(500)
        check("rf-summary renders", "Summary — expected wake:" in summ, summ[:70].replace("\n", " | "))
        check("latency shown in summary", "ms mean" in summ and "ms p95" in summ)
        check("cpu shown in summary", "cpu/tick" in summ)

        armed = await page.evaluate("""(label) => {
          const cbs = Array.from(document.querySelectorAll('#rf-recpane input[type=checkbox]'));
          const row = cbs.find(c => c.closest('div').textContent.indexOf(label) >= 0);
          if (row) { row.checked = true; row.dispatchEvent(new Event('change', { bubbles: true })); }
          return { found: !!row, btn: (document.getElementById('rf-delselected') || {}).textContent || '', rows: cbs.length };
        }""", "ui-delete-probe")
        check("scratch take checkable", armed["found"], json.dumps(armed)[:120])
        check("delete button armed", "(1)" in armed["btn"], armed["btn"])
        await page.click("#rf-delselected")
        gone = False
        for _ in range(30):
            still = await page.evaluate("""(label) => Array.from(document.querySelectorAll('#rf-recpane > div')).some(d => d.textContent.indexOf(label) >= 0)""", "ui-delete-probe")
            if not still:
                gone = True
                break
            await page.wait_for_timeout(300)
        check("scratch take deleted via UI", gone)
        check("confirm dialog was shown", any("Delete 1 take" in d for d in dialogs), json.dumps(dialogs)[:120])

        check("no page errors", not errs, json.dumps(errs)[:200])
        await browser.close()
    print("OVERALL: " + ("PASS" if PASSED else "FAIL"))


asyncio.run(main())
