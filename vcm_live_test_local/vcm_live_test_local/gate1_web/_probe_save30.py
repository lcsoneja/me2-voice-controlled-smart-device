"""E2E probe of the shortcut flow: open the dashboard, watch mic/WS state,
click 'Save last 30 s', verify a recording lands on disk. Diagnostic-rich.

Run: python gate1_web/_probe_save30.py
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
APP = HERE.parent
URL = "http://127.0.0.1:8765/pipeline_all_in_one.html"
REC = APP / "recordings"
BTN = "#pipe2ownervoiceSave30"


def index_count():
    try:
        data = json.loads((REC / "index.json").read_text(encoding="utf-8"))
        return len(data) if isinstance(data, list) else len(data.get("recordings", []))
    except Exception:
        return -1


def main():
    result = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page()
        errs, console, http_fail = [], [], []
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        page.on("response", lambda r: http_fail.append(str(r.status) + " " + r.url) if r.status >= 400 else None)
        page.on("console", lambda m: console.append(m.type + ":" + m.text[:120]) if m.type in ("error", "warning") else None)
        page.goto(URL, wait_until="load", timeout=60000)

        # Poll for up to 25 s: capture status + micLive transitions
        seen = []
        mic_live = False
        for _ in range(50):
            state = page.evaluate("() => ({ mic: !!(window.VCMALL && window.VCMALL.micLive), status: (document.getElementById('status') || {}).textContent || '' })")
            if not seen or seen[-1] != state["status"]:
                seen.append(state["status"])
            if state["mic"]:
                mic_live = True
                break
            page.wait_for_timeout(500)
        result["mic_live"] = mic_live
        result["status_log"] = seen
        result["console_errs"] = console[:5]
        result["http_fail"] = http_fail[:5]
        result["pageerrors"] = errs[:3] or "none"

        if mic_live:
            page.wait_for_timeout(9000)  # let the memory ring accumulate audio
            before = index_count()
            page.click(BTN)
            try:
                page.wait_for_function("!document.getElementById('pipe2ownervoiceSave30').disabled", timeout=14000)
                result["button_reenabled"] = True
            except Exception:
                result["button_reenabled"] = False
            result["capture_text"] = page.evaluate("() => (document.getElementById('pipe2-ownervoice-capture') || {}).textContent || ''")
            time.sleep(1.0)
            after = index_count()
            result["index_before"] = before
            result["index_after"] = after
            result["new_recording"] = (after > before) if (before >= 0 and after >= 0) else None
        browser.close()
    print(json.dumps(result, indent=2))
    return 0 if result.get("new_recording") else 1


if __name__ == "__main__":
    raise SystemExit(main())
