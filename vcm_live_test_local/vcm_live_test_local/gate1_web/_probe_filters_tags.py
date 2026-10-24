"""Browser check for the take filter pane, structured tags, model search and the NC A/B axis."""
import asyncio
import base64
import io
import json
import urllib.request
import wave

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8765"
DASH = BASE + "/pipeline_all_in_one.html"
LAB = BASE + "/recording_lab.html"
TAG_LABEL = "ui-tag-probe"
PASSED = True

COUNT_PANE = "() => document.querySelectorAll('#rf-recpane > div').length"
PANE_TEXT = "() => document.querySelector('#rf-recpane').textContent"
ROW_TEXTS = "() => Array.from(document.querySelectorAll('#rf-recpane > div')).map(d => d.textContent)"
LANE_TEXT = "() => document.getElementById('rf-lanecount').textContent"
REC_INPUTS = "() => !!document.getElementById('rf-recwake') && !!document.getElementById('rf-recaction')"
HIDDEN_MODELS = "() => Array.from(document.querySelectorAll('#rf-mbox label')).filter(l => l.style.display === 'none').length"
VISIBLE_TICKED = """() => Array.from(document.querySelectorAll('#rf-g1box label, #rf-mbox label'))
    .filter(l => l.style.display !== 'none' && l.querySelector('input').checked).length"""
LAB_ROWS = "() => document.querySelectorAll('#reclist label').length"
LAB_FIRST = "() => document.querySelector('#reclist label').textContent"
LAB_NCMODE = "() => document.getElementById('ncmode').value"
CLICK_FIRST_ROW = "() => document.querySelector('#rf-recpane > div').click()"


def api(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    verb = method or ("POST" if data is not None else "GET")
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(BASE + path, data=data, method=verb, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def check(name, cond, detail=None):
    """Record one PASS/FAIL line."""
    global PASSED
    PASSED = PASSED and bool(cond)
    text = "" if detail in ("", None, [], {}) else str(detail)
    print(("PASS " if cond else "FAIL ") + name + (("  " + text) if text else ""))


def seeded_wav(seconds):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x01\x00" * 16000 * seconds)
    return base64.b64encode(buf.getvalue()).decode()


def lanes(text):
    head = str(text).split()
    return int(head[0]) if head and head[0].isdigit() else -1


async def main():
    seeded = api("/api/recordings", {"label": TAG_LABEL, "wav_base64": seeded_wav(8),
                                     "wake_word": "Piattos", "action": "SET_TIMER"})["recording"]
    print("seeded", seeded["id"], seeded.get("wake_word"), seeded.get("action"))

    errs = []
    args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            "--autoplay-policy=no-user-gesture-required"]
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True, args=args)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge", args=args)

        # ---------- dashboard recording-test frame ----------
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append("dash: " + str(e)[:200]))
        await page.goto(DASH)
        await page.click("#all-recframe-toggle")
        await page.wait_for_selector("#rf-recpane > div", timeout=15000)

        total = await page.evaluate(COUNT_PANE)
        check("pane lists takes", total >= 2, total)

        await page.select_option("#rf-fwake", "Piattos")
        await page.wait_for_timeout(250)
        rows = await page.evaluate(ROW_TEXTS)
        check("wake filter narrows pane", len(rows) >= 1 and all("Piattos" in r for r in rows), len(rows))

        await page.select_option("#rf-faction", "SET_TIMER")
        await page.wait_for_timeout(250)
        check("action filter narrows pane", await page.evaluate(COUNT_PANE) == 1)

        await page.select_option("#rf-fwake", "")
        await page.select_option("#rf-faction", "")
        await page.fill("#rf-fsearch", "no-such-take-xyz")
        await page.wait_for_timeout(250)
        empty = await page.evaluate(PANE_TEXT)
        check("search shows empty state", "no take" in empty.lower(), empty[:46])

        # Row select: the pane re-renders on every filter change, so dispatch the
        # click in the same frame as the render instead of racing a mouse click.
        await page.fill("#rf-fsearch", TAG_LABEL)
        await page.wait_for_timeout(400)
        await page.evaluate(CLICK_FIRST_ROW)
        await page.wait_for_timeout(400)
        tagwake = await page.input_value("#rf-tagwake")
        tagaction = await page.input_value("#rf-tagaction")
        check("row click loads tags", tagwake == "Piattos" and tagaction == "SET_TIMER",
              tagwake + " / " + tagaction)

        await page.select_option("#rf-tagwake", "Nova")
        await page.fill("#rf-tagaction", "PLAY_MUSIC")
        await page.click("#rf-savetags")
        await page.wait_for_timeout(1200)
        after = next(iter(r for r in api("/api/recordings")["recordings"] if r["id"] == seeded["id"]))
        check("UI tag save persists", after.get("wake_word") == "Nova"
              and after.get("action") == "PLAY_MUSIC",
              str(after.get("wake_word")) + " / " + str(after.get("action")))
        await page.fill("#rf-fsearch", "")
        await page.wait_for_timeout(300)

        # Model search + Tick visible ("v1" matches both Gate 1 and Gate 2 labels)
        await page.fill("#rf-modelsearch", "v1")
        await page.click("#rf-selectvisible")
        await page.wait_for_timeout(300)
        hidden = await page.evaluate(HIDDEN_MODELS)
        ticked = await page.evaluate(VISIBLE_TICKED)
        check("model search hides non-matches", hidden > 0, hidden)
        check("tick visible ticks shown rows only", ticked > 0, ticked)
        await page.fill("#rf-modelsearch", "")
        await page.wait_for_timeout(200)

        seen = {}
        for want in ("off", "on", "both"):
            await page.select_option("#rf-ncmode", want)
            await page.wait_for_timeout(200)
            seen[want] = await page.evaluate(LANE_TEXT)
        check("lane count doubles for Both mode",
              lanes(seen["both"]) == 2 * lanes(seen["off"]) > 0, json.dumps(seen))
        check("recorder has wake/action tag inputs", await page.evaluate(REC_INPUTS))
        await page.close()

        # ---------- lab page ----------
        lab = await browser.new_page()
        lab.on("pageerror", lambda e: errs.append("lab: " + str(e)[:200]))
        await lab.goto(LAB)
        await lab.wait_for_selector("#reclist label", timeout=15000)
        ltotal = await lab.evaluate(LAB_ROWS)
        await lab.select_option("#fWake", "Nova")
        await lab.wait_for_timeout(300)
        lnova = await lab.evaluate(LAB_ROWS)
        await lab.select_option("#fWake", "")
        await lab.fill("#fSearch", TAG_LABEL)
        await lab.wait_for_timeout(300)
        lsearch = await lab.evaluate(LAB_ROWS)
        check("lab filter narrows list", ltotal > lnova >= 1 and lsearch == 1,
              f"all={ltotal} nova={lnova} search={lsearch}")
        badge = await lab.evaluate(LAB_FIRST)
        check("lab rows show tag badges", "Nova" in badge or "PLAY_MUSIC" in badge, badge[:56])
        check("lab NC axis defaults to Both", (await lab.evaluate(LAB_NCMODE)) == "both")
        await lab.close()
        await browser.close()

    check("no page errors", not errs, json.dumps(errs)[:280])

    # Cleanup the seeded take (network call off the event loop)
    kill = urllib.request.Request(BASE + "/api/recordings/" + seeded["id"], method="DELETE")
    await asyncio.to_thread(lambda: urllib.request.urlopen(kill, timeout=30).read())
    print(f"cleanup | takes now: {len(api('/api/recordings')['recordings'])}")
    print("OVERALL: " + ("PASS" if PASSED else "FAIL"))


if __name__ == "__main__":
    asyncio.run(main())
