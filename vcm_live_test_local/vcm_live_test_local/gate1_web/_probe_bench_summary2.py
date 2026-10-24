"""Probe: combination summary correctness math, cross-checked against an independent recomputation.

check() prints ASCII-safe output on consoles that cannot encode the check/cross glyphs (cp1252)."""
import asyncio
import json
import re
import urllib.request

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8765"
ALIAS = {"settimer": "timer", "alarmset": "alarm", "tempup": "temperature", "tempdown": "temperature",
         "lightsdim": "brightness", "lightsbright": "brightness", "lightson": "lighton", "lightsoff": "lightoff",
         "reminderset": "createreminder", "remindercheck": "listreminders", "checkreminders": "listreminders",
         "mediaplay": "playmusic", "mediapause": "pause", "medianext": "next", "silence": "stop"}
PASSED = True


def check(name, cond, detail=None):
    global PASSED
    PASSED = PASSED and bool(cond)
    text = "" if detail in ("", None, [], {}) else str(detail)
    line = ("PASS " if cond else "FAIL ") + name + (("  " + text) if text else "")
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"))


def bag(s):
    return "".join(sorted(t for t in re.split(r"[^a-z]+", str(s or "").lower()) if t))


def alias(b):
    return ALIAS.get(b, b)


def fetch_json(path):
    with urllib.request.urlopen(BASE + path, timeout=25) as resp:
        return json.load(resp)


def expected_counts(job, recs):
    rec = next((r for r in recs if r["id"] == job.get("recording")), {})
    exp_wake = str(rec.get("wake_word") or "").strip()
    exp_act = str(rec.get("action") or "").strip()
    g1_by = {}
    for e in job.get("events") or []:
        if e.get("kind") == "g1":
            k = (e.get("g1_model") or "") + "|" + (e.get("model") or "") + "|" + ("1" if e.get("nc") else "0")
            g1_by.setdefault(k, []).append(e)
    n_ok = n_g1 = n_g2 = n_na = 0
    for s in job.get("summaries") or []:
        k = (s.get("g1_model") or "") + "|" + (s.get("model") or "") + "|" + ("1" if s.get("nc") else "0")
        fired = [e for e in g1_by.get(k, []) if bag(e.get("label")) == bag(exp_wake)] if exp_wake else []
        g1ok = (len(fired) > 0) if exp_wake else None
        matched = 0
        if exp_act:
            eb = alias(bag(exp_act))
            for k2, v in (s.get("intents") or {}).items():
                if alias(bag(k2)) == eb:
                    matched += v or 0
        g2ok = (matched > 0) if exp_act else None
        if g1ok is None and g2ok is None:
            n_na += 1
        elif g1ok is not False and g2ok is not False:
            n_ok += 1
        if g1ok is True:
            n_g1 += 1
        if g2ok is True:
            n_g2 += 1
    return exp_wake, exp_act, len(job.get("summaries") or []), n_ok, n_g1, n_g2, n_na


SUMTEXT = "() => (document.getElementById('all-bench-summary') || {}).innerText || ''"
OPTCOUNT = "() => document.querySelectorAll('#all-bench-results option').length"


async def main():
    rows = (await asyncio.to_thread(fetch_json, "/api/results")).get("results") or []
    jid = rows[0]["id"]
    job = (await asyncio.to_thread(fetch_json, f"/api/results/{jid}"))["job"]
    recs = (await asyncio.to_thread(fetch_json, "/api/recordings")).get("recordings") or []
    exp_wake, exp_act, n_lanes, n_ok, n_g1, n_g2, n_na = expected_counts(job, recs)
    print(f"job {jid} | expected wake: {exp_wake} | action: {exp_act}")
    print(f"EXPECT lanes={n_lanes} ok={n_ok} g1={n_g1} g2={n_g2} na={n_na}")

    errs = []
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception:
            browser = await pw.chromium.launch(headless=True, channel="msedge")
        page = await browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:160]))
        await page.goto(BASE + "/pipeline_all_in_one.html")

        # The results select is only populated in benchmark mode - enable it.
        if await page.evaluate(OPTCOUNT) == 0:
            for _ in range(2):
                try:
                    await page.click("#all-bench-toggle", timeout=4000)
                except Exception:
                    await page.evaluate("() => { const b = document.getElementById('all-bench-toggle'); if (b) b.click(); }")
                await page.wait_for_timeout(400)
                if await page.evaluate(OPTCOUNT) > 0:
                    break
        check("benchmark dropdown populated", await page.evaluate(OPTCOUNT) > 0)
        await page.wait_for_selector("#all-bench-results option", state="attached", timeout=15000)

        # Auto-open path: benchLoadResults -> benchOpen -> benchDraw + benchSummary (the real wiring).
        auto = ""
        for _ in range(24):
            auto = await page.evaluate(SUMTEXT)
            if "fully correct" in auto:
                break
            await page.wait_for_timeout(250)
        check("auto-open renders summary (wiring)", "fully correct" in auto and "Combination summary" in auto)

        has_job = "(v) => Array.from(document.querySelectorAll('#all-bench-results option')).some(o => o.value === v)"
        for _ in range(20):
            if await page.evaluate(has_job, jid):
                break
            await page.wait_for_timeout(250)
        check("results dropdown has newest job", await page.evaluate(has_job, jid))

        pick = ("(v) => { const s = document.getElementById('all-bench-results');"
                " if (!s) return false; s.value = v;"
                " s.dispatchEvent(new Event('change', { bubbles: true })); return true; }")
        check("summary selection dispatched", await page.evaluate(pick, jid))

        summary = ""
        for _ in range(24):
            summary = await page.evaluate(SUMTEXT)
            if "fully correct" in summary:
                break
            await page.wait_for_timeout(250)
        check("summary header present", "Combination summary" in summary and "expected wake:" in summary)
        if exp_wake:
            check("summary shows expected wake", exp_wake in summary, exp_wake)
        if exp_act:
            check("summary shows expected action", exp_act in summary, exp_act)
        m = re.search(r"(\d+) lanes · fully correct (\d+) · Gate 1 correct (\d+) · Gate 2 correct (\d+) · not judgeable (\d+)", summary)
        check("aggregate line parsed", bool(m), (m.group(0) if m else summary[:90]))
        if m:
            got = [int(m.group(i)) for i in range(1, 6)]
            want = [n_lanes, n_ok, n_g1, n_g2, n_na]
            check("aggregate matches recomputation", got == want, f"got={got} want={want}")
        nrows = await page.evaluate("() => document.querySelectorAll('#all-bench-summary tbody tr').length")
        check("summary table has rows", nrows >= 1, nrows)
        body = await page.evaluate("() => (document.querySelector('#all-bench-summary tbody') || {}).innerText || ''")
        check("verdicts present", ("✓" in body or "✗" in body), body[:80].replace("\n", " | "))
        check("no page errors", not errs, json.dumps(errs)[:200])
        await browser.close()

    print("OVERALL: " + ("PASS" if PASSED else "FAIL"))


if __name__ == "__main__":
    asyncio.run(main())
