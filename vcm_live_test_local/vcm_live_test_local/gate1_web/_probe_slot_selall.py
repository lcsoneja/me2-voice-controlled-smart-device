"""Probe: slot label, select-all, delete prompt (dismissed), selective delete of scratch takes."""
import asyncio
import base64
import io
import json
import sys
import urllib.request
import wave

from playwright.async_api import async_playwright


def _force_utf8_stdio() -> None:
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
accept_next = [False]


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

    # clean orphans, then two scratch takes for the delete test
    recs = await asyncio.to_thread(get, "/api/recordings")
    for r in recs["recordings"]:
        if str(r.get("label", "")).startswith("ui-delall-"):
            await asyncio.to_thread(delete, "/api/recordings/" + r["id"])
    scratch_ids = []
    for lbl in ("ui-delall-1", "ui-delall-2"):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(b"\x01\x00" * 16000 * 2)
        d = await asyncio.to_thread(post, "/api/recordings", {"label": lbl,
                               "wav_base64": base64.b64encode(buf.getvalue()).decode()})
        scratch_ids.append(d["recording"]["id"])
    print("scratches:", scratch_ids)

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True, args=args)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge", args=args)
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:160]))

        async def on_dialog(d):
            dialogs.append(d.message)
            if accept_next[0]:
                await d.accept()
            else:
                await d.dismiss()
        page.on("dialog", on_dialog)

        await page.goto(DASH)
        await page.click("#all-recframe-toggle")
        await page.wait_for_selector("#rf-recpane > div", timeout=15000)

        # 1) slot label via a synthetic render (specialist fired -> "slot (green)")
        fake = {"id": "fake", "recording": "20261023_155245_2dd71e", "label": "slot-probe",
                "duration_s": 12, "combos": [], "events": [], "status": "done", "elapsed_s": 0.4,
                "gated_modes": [False],
                "summaries": [{"g1_model": "gate1v12_f16", "model": "gate2v16", "nc": False, "gated": False,
                               "trigger_ticks": 3, "top_intent": "COLOR", "top_intent_conf": 0.9,
                               "intents": {"COLOR": 3}, "command_ticks": 3, "ticks": 3,
                               "g3_fired": 2, "g3_top": "COLOR:green",
                               "mean_infer_ms": 4.2, "mean_cpu_ms": 1.1}]}
        await page.evaluate("(j) => window.rfRender(j)", fake)
        await page.wait_for_timeout(400)
        res = await page.evaluate("() => (document.getElementById('rf-results') || {}).innerText || ''")
        summ = await page.evaluate("() => (document.getElementById('rf-summary') || {}).innerText || ''")
        check("slot label on card", "slot (green)" in res, res[:110].replace("\n", " | "))
        check("slot label on summary lane", "slot (green)" in summ, summ[:110].replace("\n", " | "))

        # 2) select all
        rows = await page.evaluate("() => Array.from(document.querySelectorAll('#rf-recpane input[type=checkbox]')).length")
        await page.check("#rf-selall")
        await page.wait_for_timeout(300)
        st = await page.evaluate("""() => ({
          batch: (document.getElementById('rf-batchstart') || {}).textContent || '',
          del: (document.getElementById('rf-delselected') || {}).textContent || '',
          count: (document.getElementById('rf-selcount') || {}).textContent || '',
          checked: Array.from(document.querySelectorAll('#rf-recpane input[type=checkbox]')).filter(c => c.checked).length })""")
        check("select all checks every take", st["checked"] == rows and str(rows) in st["batch"], json.dumps(st)[:180])
        check("delete button armed for all", str(rows) in st["del"], st["del"])

        # 3) uncheck -> cleared
        await page.uncheck("#rf-selall")
        await page.wait_for_timeout(300)
        st = await page.evaluate("() => Array.from(document.querySelectorAll('#rf-recpane input[type=checkbox]')).filter(c => c.checked).length")
        check("uncheck clears selection", st == 0, st)

        # 4) delete prompt DISMISSED (protect the real takes)
        await page.check("#rf-selall")
        await page.wait_for_timeout(300)
        accept_next[0] = False
        await page.click("#rf-delselected")
        await page.wait_for_timeout(400)
        check("delete prompt shown", any("permanently" in d and "cannot be undone" in d for d in dialogs),
              json.dumps(dialogs)[:140])
        rows_now = await page.evaluate("() => Array.from(document.querySelectorAll('#rf-recpane > div')).length")
        check("cancelled delete keeps all takes", rows_now == rows, f"{rows_now}/{rows}")

        # 5) selective delete: uncheck all, check only the two scratches, ACCEPT
        await page.uncheck("#rf-selall")
        await page.wait_for_timeout(200)
        await page.evaluate("""() => {
          Array.from(document.querySelectorAll('#rf-recpane > div')).forEach(function (row) {
            if (row.textContent.indexOf('ui-delall-') >= 0) {
              var c = row.querySelector('input[type=checkbox]');
              if (c) { c.checked = true; c.dispatchEvent(new Event('change', { bubbles: true })); }
            }
          });
        }""")
        await page.wait_for_timeout(200)
        delbtn = await page.evaluate("() => (document.getElementById('rf-delselected') || {}).textContent || ''")
        check("delete armed for 2 scratches", "(2)" in delbtn, delbtn)
        accept_next[0] = True
        await page.click("#rf-delselected")
        gone = False
        say = ""
        for _ in range(40):
            say = await page.evaluate("() => (document.getElementById('rf-say') || {}).textContent || ''")
            if "deleted 2 takes" in say:
                gone = True
                break
            await page.wait_for_timeout(300)
        # pi-lens-ignore: Pyright:reportPossiblyUnbound
        check("scratches deleted (accepted)", gone, say[:60])
        left = await page.evaluate("""() => Array.from(document.querySelectorAll('#rf-recpane > div'))
          .filter(d => d.textContent.indexOf('ui-delall-') >= 0).length""")
        check("only scratches were deleted", left == 0, left)

        check("no page errors", not errs, json.dumps(errs)[:200])
        await browser.close()
    print("OVERALL: " + ("PASS" if PASSED else "FAIL"))


asyncio.run(main())
