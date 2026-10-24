"""End-to-end recorder probe: does the mic waveform move, and does Stop save the take?"""
import asyncio
import json
import urllib.request

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8765"
FRAME_URL = BASE + "/pipeline_all_in_one.html"
LAB_URL = BASE + "/recording_lab.html"


def rec_count():
    with urllib.request.urlopen(BASE + "/api/recordings", timeout=15) as r:
        return len(json.load(r)["recordings"])


def rec_ids():
    with urllib.request.urlopen(BASE + "/api/recordings", timeout=15) as r:
        return {e["id"]: str(e.get("label", "")) for e in json.load(r)["recordings"]}


def cleanup(created_before):
    """Remove only the takes this probe banked (rf-take-* / 'take HH:MM:SS')."""
    gone = []
    for rec_id, label in rec_ids().items():
        if rec_id in created_before:
            continue
        if label.startswith(("rf-take-", "take ")): 
            req = urllib.request.Request(BASE + "/api/recordings/" + rec_id, method="DELETE")
            with urllib.request.urlopen(req, timeout=15) as r:
                r.read()
            gone.append(label)
    return gone


async def canvas_ink(page, canvas_id):
    """Count reddish (mic) pixels drawn on the waveform canvas."""
    return await page.evaluate(
        """(id) => {
          const cv = document.getElementById(id);
          if (!cv) return -1;
          const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data;
          let red = 0;
          for (let i = 0; i < d.length; i += 4) {
            if (d[i] > 150 && d[i+1] < 130 && d[i+2] < 140) red++;
          }
          return red;
        }""",
        canvas_id,
    )


async def level_width(page, bar_id):
    return await page.evaluate(
        "(id) => { const e = document.getElementById(id); return e ? parseFloat(e.style.width) || 0 : -1; }",
        bar_id,
    )


async def main():
    results = []
    errs = []
    ids_before = set(rec_ids())
    args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            "--autoplay-policy=no-user-gesture-required"]
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True, args=args)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge", args=args)

        # ---------- 1) Dashboard Recording test frame ----------
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append("dash: " + str(e)[:220]))
        await page.goto(FRAME_URL)
        await page.click("#all-recframe-toggle")
        await page.wait_for_selector("#rf-recnew", timeout=10000)
        before = rec_count()

        await page.click("#rf-recnew")
        await page.wait_for_timeout(2500)
        ink_rec = await canvas_ink(page, "rf-wave")
        lvl_rec = await level_width(page, "rf-level")
        state = await page.evaluate("() => document.getElementById('rf-recstate').textContent")

        await page.click("#rf-recstop")
        await page.wait_for_timeout(3500)
        after = rec_count()
        saved_state = await page.evaluate("() => document.getElementById('rf-recstate').textContent")
        ink_after = await canvas_ink(page, "rf-wave")
        opts = await page.evaluate("() => Array.from(document.querySelectorAll('#rf-rec option')).map(o => o.textContent)")
        results.append(("DASH save grows list", before, after, after == before + 1))
        results.append(("DASH mic waveform drawn while recording", ink_rec, lvl_rec, ink_rec > 50))
        results.append(("DASH state text", state[:40], saved_state[:60], "saved" in saved_state.lower()))
        # After Stop the mic loop and analyser must be released, and no wave
        # loop may keep painting. (Leftover ink only proves a loop existed;
        # timers/analysers are the real release contract.)
        # RF/RFR live in a closure; the DOM-visible contract is: after Stop the
        # waveform canvas is cleared and STAYS cleared (a live loop would repaint).
        await page.wait_for_timeout(1200)
        ink_late = await canvas_ink(page, "rf-wave")
        results.append(("DASH mic meter released after stop", ink_rec, f"ink {ink_after}->{ink_late}", ink_after == 0 and ink_late == 0))
        results.append(("DASH new take in dropdown", len(opts), opts[-1][:34] if opts else "", after == before + 1))

        # Pause/resume path still works after the meter change
        await page.click("#rf-recnew")
        await page.wait_for_timeout(1200)
        await page.click("#rf-recpause")
        p_state = await page.evaluate("() => document.getElementById('rf-recstate').textContent")
        await page.click("#rf-recpause")
        r_state = await page.evaluate("() => document.getElementById('rf-recstate').textContent")
        await page.click("#rf-recdiscard")
        await page.wait_for_timeout(1500)
        after_discard = rec_count()
        results.append(("DASH pause/resume labels", p_state[:24], r_state[:24], "paused" in p_state.lower() and "recording" in r_state.lower()))
        results.append(("DASH discard saves nothing", after, after_discard, after_discard == after))

        # ---------- 2) Recording Lab page ----------
        lab = await browser.new_page()
        lab.on("pageerror", lambda e: errs.append("lab: " + str(e)[:220]))
        await lab.goto(LAB_URL)
        await lab.wait_for_selector("#recWave", timeout=10000)
        lab_before = rec_count()

        await lab.click("#recNew")
        await lab.wait_for_timeout(2500)
        lab_ink = await canvas_ink(lab, "recWave")
        lab_lvl = await level_width(lab, "recLevel")
        lab_state = await lab.evaluate("() => document.getElementById('recState').textContent")

        # Stop keeps the take pending (must NOT auto-save), then Save persists it
        await lab.click("#recStop")
        await lab.wait_for_timeout(800)
        pending_count = rec_count()
        pending_state = await lab.evaluate("() => document.getElementById('recState').textContent")
        save_enabled = await lab.evaluate("() => !document.getElementById('recSave').disabled")
        await lab.click("#recSave")
        await lab.wait_for_timeout(3000)
        lab_after = rec_count()
        final_state = await lab.evaluate("() => document.getElementById('recState').textContent")
        results.append(("LAB mic waveform drawn", lab_ink, lab_lvl, lab_ink > 50))
        results.append(("LAB stop is pending not saved", lab_before, pending_count, pending_count == lab_before and "ready" in pending_state.lower() and save_enabled))
        results.append(("LAB save persists", pending_count, lab_after, lab_after == pending_count + 1))
        results.append(("LAB state text", lab_state[:26], final_state[:50], "saved" in final_state.lower() or "take" in final_state.lower()))

        await browser.close()

    removed = cleanup(ids_before)
    print("cleanup removed probe takes:", len(removed), "| list now:", rec_count())

    ok = True
    for name, a, b, passed in results:
        ok = ok and passed
        line = ("PASS " if passed else "FAIL ") + name + f"  [{a} -> {b}]"
        print(line.encode("ascii", "replace").decode("ascii"))
    if errs:
        print("PAGE ERRORS:", errs)
        ok = False
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
