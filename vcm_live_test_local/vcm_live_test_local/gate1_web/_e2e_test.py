"""E2E test for vcm_monitor.html: 3 tabs, WS audio injection, verdict checks.

Timing note: injections happen only after the first successful inference
(server window full), so injected audio sits at the window tail.
"""
import base64
import sys
import wave
from pathlib import Path

import numpy as np  # noqa: F401
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
URL = "http://127.0.0.1:8765/vcm_monitor.html"
SYN = HERE.parent / "synthetic_samples"

def b64wav(fname):
    with wave.open(str(SYN / fname), "rb") as w:
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return base64.b64encode(y.astype("<f4").tobytes()).decode()

INJECT = """async (b64) => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const wav = new Float32Array(bytes.buffer);
  const send = function (f32) { VCM.inject(f32); };
  let pos = 0;
  while (pos + 4096 <= wav.length) { send(wav.subarray(pos, pos + 4096)); pos += 4096; }
  send(wav.subarray(pos));
  return VCM.state.streamAcc ? VCM.state.streamAcc.length : 'n/a';
}"""

FLUSH = """async () => {
  const silence = new Float32Array(4096);
  for (let b = 0; b < 25; b++) { VCM.inject(silence); }
  return true;
}"""

def main() -> int:
    results = []
    console_errs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page()
        page.on("pageerror", lambda e: console_errs.append(str(e)[:200]))
        page.goto(URL, wait_until="load", timeout=60000)
        try:
            page.wait_for_function("document.getElementById('status').textContent.indexOf('microphone live') !== -1", timeout=30000)
            print("boot: OK (mic live)")
        except Exception:
            print("boot: FAILED - status:", page.inner_text("#status")[-300:])
            page.screenshot(path=str(HERE / "e2e_boot_fail.png"))
            browser.close()
            return 1
        # wait until the server window is full (first probs processed)
        try:
            page.wait_for_function("document.getElementById('g1log').children.length > 0", timeout=30000)
            print("first inference: OK")
        except Exception:
            print("first inference: never happened (window not filling?)")
            browser.close()
            return 1
        page.wait_for_timeout(500)

        nova = b64wav("gate1_wake_nova_f01_pitchhigh_normal.wav")
        color = b64wav("gate4_COLOR_Blue_f10_pitchnorm_normal.wav")
        call = b64wav("gate2_CALL_f04_pitchlow_normal.wav")

        # A 0.6s wake word sits in the recent-1s tail only briefly (ticks are
        # 1/s), so repeat injections keep it there across tick phases.
        REPEAT = """async (args) => {
          const [b64, times, gapMs] = args;
          for (let k = 0; k < times; k++) {
            const bin = atob(b64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            VCM.inject(new Float32Array(bytes.buffer));
            await new Promise(r => setTimeout(r, gapMs));
          }
          return true;
        }"""

        # ---- Tab 1: Gate 1 ----
        page.evaluate(REPEAT, [nova, 6, 500])
        g1ok = False
        for _ in range(8):
            page.wait_for_timeout(1000)
            banner = page.inner_text("#banner").strip()
            if banner.startswith("WAKE DETECTED: Nova"):
                g1ok = True
                break
        results.append(("gate1 tab: nova -> WAKE banner (2-of-3)", g1ok))
        page.screenshot(path=str(HERE / "e2e_tab1.png"))
        page.evaluate(FLUSH)
        page.wait_for_timeout(1500)

        # ---- Tab 2: Gate 2 ----
        page.click("button[data-tab='gate2']")
        page.wait_for_timeout(500)
        if page.locator("#g2chips .chip", has_text="call mom").count():
            page.click("#g2chips .chip:has-text('call mom')")
        page.evaluate(INJECT, call)
        g2ok = False
        g2verdictText = ""
        for _ in range(8):
            page.wait_for_timeout(1000)
            g2verdictText = page.inner_text("#g2verdict").strip()
            if "PASS" in g2verdictText or "LOW" in g2verdictText:
                g2ok = True
                break
        results.append(("gate2 tab: call -> top CALL + verdict " + g2verdictText[:12], g2ok))
        page.screenshot(path=str(HERE / "e2e_tab2.png"))
        page.evaluate(FLUSH)
        page.wait_for_timeout(1500)

        # ---- Tab 3: Pipeline with independent 8s G1 / 4s G2 activation windows ----
        page.click("button[data-tab='pipe']")
        page.wait_for_timeout(500)
        if page.locator("#pipechips .chip", has_text="make the lights blue").count():
            page.click("#pipechips .chip:has-text('make the lights blue')")
        if page.locator("#pipe-action").count() != 1:
            raise AssertionError("Action Gate status stage is missing")
        page.evaluate(REPEAT, [nova, 6, 500])
        g1_active = False
        for _ in range(5):
            page.wait_for_timeout(1000)
            if "ACTIVE" in page.inner_text("#pipe-g1"):
                g1_active = True
                break
        # Let the wake clip roll out of Gate1's 5.92s window while its 8s latch stays active.
        page.wait_for_timeout(1500)
        # Gate2 sees the command in its centered 74-frame crop while G1 remains latched.
        page.evaluate(INJECT, color)
        page.wait_for_timeout(1500)
        pipeok = False
        pipeStages = {}
        pipeVerdictText = ""
        actionText = ""
        for _ in range(6):
            page.wait_for_timeout(1000)
            pipeStages = {
                "g1": page.inner_text("#pipe-g1").strip(),
                "g2": page.inner_text("#pipe-g2").strip(),
                "spec": page.inner_text("#pipe-spec").strip(),
                "final": page.inner_text("#pipe-final").strip(),
            }
            actionText = page.inner_text("#pipe-action").strip()
            pipeVerdictText = page.inner_text("#pipeverdict").strip()
            if (g1_active and "TRIGGERED" in actionText and "COLOR" in pipeStages["g2"]
                    and "Blue" in pipeStages["spec"] and "Blue" in pipeStages["final"]):
                pipeok = True
                break
        results.append(("pipeline tab: 8s wake latch + Gate2 COLOR -> Gate4 Blue", pipeok))
        page.screenshot(path=str(HERE / "e2e_tab3.png"))
        print("PIPE stages:", {k: ascii(v2) for k, v2 in pipeStages.items()}, "| action:", ascii(actionText), "| verdict:", ascii(pipeVerdictText[:60]))

        browser.close()

    print()
    all_ok = True
    for name, ok in results:
        print(("PASS  " if ok else "FAIL  ") + name)
        all_ok = all_ok and ok
    if console_errs:
        print("console errors:", console_errs[:5])
    print("E2E RESULT:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
