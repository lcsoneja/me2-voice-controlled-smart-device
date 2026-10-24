"""Inject known audio (nova/piattos/call wavs) through the WebSocket and verify
the server-side inference + banner path. Also reports the fake-mic level to show
whether Chrome's fake audio device produced silence in this environment.
"""
import importlib.util
import sys
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
URL = "http://127.0.0.1:8765/gate1_monitor.html"

spec = importlib.util.spec_from_file_location("ls", HERE.parent / "live_session.py")
assert spec is not None and spec.loader is not None, "failed to load live_session.py spec"
ls = importlib.util.module_from_spec(spec)
sys.argv = ["x"]
spec.loader.exec_module(ls)

FILES = [
    ("gate1_wake_nova_f01_pitchhigh_normal.wav", "WAKE DETECTED: Nova"),
    ("gate1_wake_piattos_m01_pitchnorm_fast.wav", "WAKE DETECTED: Piattos"),
    ("gate2_CALL_f04_pitchlow_normal.wav", "no-wake"),
]

INJECT_JS = """async (b64) => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  let wav = new Float32Array(bytes.buffer);  // decode LE float32 samples properly
  if (wav.length > WIN_SAMPLES) wav = wav.slice(wav.length - WIN_SAMPLES);
  const send = function (f32) {
    pushAudio(f32);
    if (ws && ws.readyState === 1) ws.send(f32);
  };
  // stream in 4096-sample blocks like the mic path
  let pos = 0;
  while (pos + 4096 <= wav.length) { send(wav.subarray(pos, pos + 4096)); pos += 4096; }
  send(wav.subarray(pos));
  return { ctxSR: ctxSR, rollFilled: rollFilled, rmsTail: rmsHist.slice(-3).map(function (v) { return v.toFixed(1); }) };
}"""

FLUSH_JS = """async () => {
  const silence = new Float32Array(4096);  // zeros
  for (let b = 0; b < 25; b++) {
    pushAudio(silence);
    if (ws && ws.readyState === 1) ws.send(silence);
  }
  return rollFilled;
}"""


def main() -> int:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page()
        page.goto(URL, wait_until="load", timeout=60000)
        page.wait_for_function("document.getElementById('modelinfo').textContent.length > 5", timeout=30000)
        page.wait_for_timeout(1500)
        micinfo = page.evaluate("() => ({ ctxSR: ctxSR, rmsTail: rmsHist.slice(-3).map(function (v) { return v.toFixed(1); }) })")
        print("fake-mic check : ctxSR=", micinfo["ctxSR"], " recent rms dB =", micinfo["rmsTail"])

        import base64

        # Fake mic produced ~-51 dB in this environment; flush with real silence
        # between cases so the previous utterance does not dominate the window.
        page.evaluate(FLUSH_JS)
        page.wait_for_timeout(2500)

        for fname, expect in FILES:
            # flush: clear the previous utterance out of the rolling window
            page.evaluate(FLUSH_JS)
            page.wait_for_timeout(2500)  # one tick scores the silence-only window

            path = HERE.parent / "synthetic_samples" / fname
            with wave.open(str(path), "rb") as w:
                y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            b64 = base64.b64encode(y.astype("<f4").tobytes()).decode()
            info = page.evaluate(INJECT_JS, b64)
            print(f"    injected {fname}: ctxSR={info['ctxSR']} rmsTail={info['rmsTail']}")
            page.wait_for_timeout(2500)  # one tick scores the wake-only window
            banner = page.inner_text("#banner").strip()
            last = page.eval_on_selector_all("#logbox div", "els => els.slice(0, 2).map(e => e.textContent)")
            results.append((fname, expect, banner, last))
            print(f"{fname:<44} expect='{expect}' -> banner='{banner}'")
            for r in last:
                print("      ", r)
        browser.close()

    print()
    ok = True
    for _, expect, banner, _ in results:
        if expect == "no-wake":
            ok = ok and ("WAKE DETECTED" not in banner)
        else:
            ok = ok and (expect in banner)
    print("RESULT:", "PASS - all three injected utterances classified correctly" if ok else "MISMATCH - see above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
