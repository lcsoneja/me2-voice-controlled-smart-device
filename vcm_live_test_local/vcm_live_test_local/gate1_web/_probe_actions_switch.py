"""Probe: Actions Play/Stop switch — toggle, persistence, suppression, frame warning."""
import asyncio
import io
import json
import sys

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


def check(name, cond, detail=None):
    global PASSED
    PASSED = PASSED and bool(cond)
    text = "" if detail in ("", None, [], {}) else str(detail)
    print(("PASS " if cond else "FAIL ") + name + (("  " + text) if text else ""))


TOGGLE_STATE = """() => ({
  btn: (document.getElementById('all-actions-toggle') || {}).textContent || '',
  stored: localStorage.getItem('vcmActions'),
  flag: window.ACTIONS_PLAYING
})"""

TRACK = "() => (document.getElementById('track') || {}).textContent || ''"
VSTATUS = "() => (document.getElementById('all-voice-status') || {}).textContent || ''"

FIRE = """(eid) => window.updateRoomSim({ action_gate: { triggered: true, intent: 'PLAY_MUSIC', event_id: eid } })"""


async def main():
    errs = []
    args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            "--autoplay-policy=no-user-gesture-required"]
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True, args=args)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge", args=args)
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:160]))
        await page.goto(DASH)
        await page.wait_for_function("() => !!window.updateRoomSim", timeout=15000)

        st = await page.evaluate(TOGGLE_STATE)
        check("default is playing", st["btn"] == "⏸ Stop actions" and st["stored"] == "playing" and st["flag"] is True,
              json.dumps(st))

        await page.click("#all-actions-toggle")
        st = await page.evaluate(TOGGLE_STATE)
        check("click stops actions", st["btn"] == "▶ Play actions" and st["stored"] == "stopped" and st["flag"] is False,
              json.dumps(st))

        await page.reload()
        await page.wait_for_function("() => !!window.updateRoomSim", timeout=15000)
        st = await page.evaluate(TOGGLE_STATE)
        check("stop state persists across reload", st["btn"] == "▶ Play actions" and st["stored"] == "stopped",
              json.dumps(st))

        before_track = await page.evaluate(TRACK)
        await page.evaluate(FIRE, 4242)
        await page.wait_for_timeout(300)
        after_track = await page.evaluate(TRACK)
        vstat = await page.evaluate(VSTATUS)
        check("stopped: action NOT executed", after_track == before_track,
              f"track {before_track[:26]!r} -> {after_track[:26]!r}")
        check("stopped: status note shown", "Actions stopped" in vstat, vstat[:60])

        await page.click("#all-actions-toggle")
        st = await page.evaluate(TOGGLE_STATE)
        check("click resumes actions", st["btn"] == "⏸ Stop actions" and st["flag"] is True, json.dumps(st))
        await page.evaluate(FIRE, 4243)
        await page.wait_for_timeout(300)
        after2 = await page.evaluate(TRACK)
        check("playing: action executes", ("loading…" in after2) and (after2 != before_track), f"track: {after2[:40]!r}")

        await page.click("#all-recframe-toggle")
        await page.wait_for_selector("#rf-recpane > div", timeout=15000)
        w1 = await page.evaluate("() => (document.getElementById('rf-actwarn') || {}).style.display || ''")
        check("frame warns while actions live", w1 == "inline", w1)
        # the header toggle sits under the full-screen frame modal — dispatch via JS
        await page.evaluate("() => document.getElementById('all-actions-toggle').click()")
        w2 = await page.evaluate("() => (document.getElementById('rf-actwarn') || {}).style.display || ''")
        check("frame warning hidden when stopped", w2 == "none", w2)
        await page.evaluate("() => document.getElementById('all-actions-toggle').click()")   # leave playing
        w3 = await page.evaluate("() => (document.getElementById('rf-actwarn') || {}).style.display || ''")
        check("frame warns again after resuming", w3 == "inline", w3)

        check("no page errors", not errs, json.dumps(errs)[:200])
        await browser.close()
    print("OVERALL: " + ("PASS" if PASSED else "FAIL"))


asyncio.run(main())
