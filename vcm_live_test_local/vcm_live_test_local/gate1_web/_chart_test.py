"""Chart verification: continuous probability line chart next to the log window.
Checks (1) probability series draws (blue Nova + purple Piattos) after audio
injection, (2) dashed threshold lines present and MOVE with the sliders,
(3) version page parity (v5).
Handles both page types: combined app (VCM global) and self-contained
version pages (inline script, no VCM global - uses its own ws).
Classification order matters: amber (Piattos thr) before red (Nova thr)
because a 1px dashed red/amber row can share antialiased pixels."""
import base64
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
BASE = "http://127.0.0.1:8765"

SCAN = """() => {
  const c = document.querySelector('#g1chart');
  if (!c) return null;
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  const bands = {red:{min:9999,max:0}, amber:{min:9999,max:0}};
  const counts = {red:0, amber:0, purple:0, blue:0};
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i], g = d[i+1], b = d[i+2];
    const y = Math.floor(i / 4 / c.width);
    // blue #1f6feb (g>r) vs purple #a371f7 (r>g): both have b>150
    if (b > 150 && g > r) { counts.blue++; }
    else if (b > 150 && r > g && r > 110) { counts.purple++; }
    else if (r > 120 && g > 90 && b < 90 && g > b + 40) { counts.amber++; if (y<bands.amber.min) bands.amber.min=y; if (y>bands.amber.max) bands.amber.max=y; }
    else if (r > 120 && r > g + 50 && r > b + 50) { counts.red++; if (y<bands.red.min) bands.red.min=y; if (y>bands.red.max) bands.red.max=y; }
  }
  return {counts: counts, redBand: [bands.red.min, bands.red.max], amberBand: [bands.amber.min, bands.amber.max]};
}"""

INJECT_MAIN = """async (b64) => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  VCM.inject(new Float32Array(bytes.buffer));
  return true;
}"""

INJECT_PAGE = """async (b64) => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  ws.send(bytes.buffer);
  return true;
}"""


def b64wav(fname):
    with wave.open(str(HERE.parent / "synthetic_samples" / fname), "rb") as w:
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return base64.b64encode(y.astype("<f4").tobytes()).decode()


def check(page, url, standalone):
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)[:160]))
    page.goto(url, wait_until="load", timeout=60000)
    page.wait_for_function("document.getElementById('status') && document.getElementById('status').textContent.indexOf('microphone live') !== -1", timeout=30000)
    if standalone:
        page.wait_for_function("document.getElementById('statsline').textContent.indexOf('windows scored: 0') === -1", timeout=15000)
    else:
        page.wait_for_function("VCM.state.lastP1 && VCM.state.lastP1.labels && VCM.state.lastP1.labels.length > 0", timeout=15000)
    # Spread thresholds so both dashed lines are visible: Nova 0.8, Piattos 0.35
    if standalone:
        for key, val in (("Nova", 0.8), ("Piattos", 0.35)):
            page.evaluate("(a) => { const sl = document.getElementById('thr_' + a[0]); sl.value = String(a[1]); sl.dispatchEvent(new Event('input')); }", [key, val])
    else:
        page.evaluate("VCM.setThr('Nova', 0.8); VCM.setThr('Piattos', 0.35)")
    # Inject both wake words to get two distinct series
    inj = INJECT_PAGE if standalone else INJECT_MAIN
    page.evaluate(inj, b64wav("gate1_wake_nova_f01_pitchhigh_normal.wav"))
    page.wait_for_timeout(2500)
    page.evaluate(inj, b64wav("gate1_wake_piattos_m01_pitchnorm_fast.wav"))
    page.wait_for_timeout(3500)
    before = page.evaluate(SCAN)
    # Move the Nova threshold slider 0.8 -> 0.4: dashed red line must move DOWN
    if standalone:
        page.evaluate("(a) => { const sl = document.getElementById('thr_' + a[0]); sl.value = String(a[1]); sl.dispatchEvent(new Event('input')); }", ["Nova", 0.4])
    else:
        page.evaluate("VCM.setThr('Nova', 0.4)")
    page.wait_for_timeout(400)
    after = page.evaluate(SCAN)
    # restore thresholds
    if standalone:
        for key, val in (("Nova", 0.5), ("Piattos", 0.5)):
            page.evaluate("(a) => { const sl = document.getElementById('thr_' + a[0]); sl.value = String(a[1]); sl.dispatchEvent(new Event('input')); }", [key, val])
    else:
        page.evaluate("VCM.setThr('Nova', 0.5); VCM.setThr('Piattos', 0.5)")
    return before, after, errs


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page()
        b, a, errs = check(page, BASE + "/vcm_monitor.html", standalone=False)
        moved = b["redBand"][0] != 9999 and a["redBand"][0] != 9999 and abs((b["redBand"][0] + b["redBand"][1]) / 2 - (a["redBand"][0] + a["redBand"][1]) / 2) > 10
        print("combined chart:", b["counts"])
        print("  red band", b["redBand"], "-> after thr move", a["redBand"], "| moved:", moved)
        print("  amber line:", b["counts"]["amber"] > 20, b["amberBand"])
        print("  series drawn (blue+purple):", b["counts"]["blue"] > 50 and b["counts"]["purple"] > 30)
        print("  pageerrors:", errs or "none")
        ok_main = b["counts"]["blue"] > 50 and b["counts"]["purple"] > 30 and b["counts"]["red"] > 20 and b["counts"]["amber"] > 20 and moved and not errs

        page2 = browser.new_page()
        b2, a2, errs2 = check(page2, BASE + "/gate1_monitor_v5.html", standalone=True)
        moved2 = b2["redBand"][0] != 9999 and a2["redBand"][0] != 9999 and abs((b2["redBand"][0] + b2["redBand"][1]) / 2 - (a2["redBand"][0] + a2["redBand"][1]) / 2) > 10
        print("v5 page chart:", b2["counts"], "| red moved:", moved2, "| amber:", b2["counts"]["amber"] > 20)
        print("  series drawn:", b2["counts"]["blue"] > 50 and b2["counts"]["purple"] > 30)
        print("  pageerrors:", errs2 or "none")
        ok_v5 = b2["counts"]["blue"] > 50 and b2["counts"]["purple"] > 30 and b2["counts"]["red"] > 20 and moved2 and not errs2

        page.screenshot(path=str(HERE / "chart_main.png"))
        page2.screenshot(path=str(HERE / "chart_v5.png"))
        browser.close()
    verdict = "PASS" if (ok_main and ok_v5) else "FAIL"
    print("CHART TEST:", verdict)
    return 0


if __name__ == "__main__":
    main()
