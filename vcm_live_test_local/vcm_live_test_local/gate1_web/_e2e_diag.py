"""E2E diagnostics: where does the injected audio chain break?"""
import base64
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
URL = "http://127.0.0.1:8765/vcm_monitor.html"

INJECT = """async (b64) => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  let wav = new Float32Array(bytes.buffer);
  const send = function (f32) {
    VCM.inject(f32);
  };
  let pos = 0;
  while (pos + 4096 <= wav.length) { send(wav.subarray(pos, pos + 4096)); pos += 4096; }
  send(wav.subarray(pos));
  return {
    filled: (typeof streamAcc !== 'undefined') ? streamAcc.length : 'no-streamAcc',
    wsState: (typeof ws !== 'undefined' && ws) ? ws.readyState : 'no-ws',
    hasPush: typeof pushAudio,
    hasOn: typeof VCM !== 'undefined' && typeof VCM.on
  };
}"""

PROBE = """() => ({
  lastP1: (typeof VCM !== 'undefined' && VCM.state) ? VCM.state.lastP1 : 'no-state',
  banner: document.getElementById('banner').textContent.slice(0, 60),
  g1logRows: document.getElementById('g1log').children.length,
  thr: (typeof VCM !== 'undefined') ? VCM.thr : null,
  listeners: (typeof VCM !== 'undefined' && VCM._listeners) ? Object.keys(VCM._listeners) : 'n/a'
})"""

def main() -> int:
    with wave.open(str(HERE.parent / "synthetic_samples" / "gate1_wake_nova_f01_pitchhigh_normal.wav"), "rb") as w:
        import numpy as np
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    b64 = base64.b64encode(y.astype("<f4").tobytes()).decode()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page()
        page.goto(URL, wait_until="load", timeout=60000)
        page.wait_for_function("document.getElementById('status').textContent.indexOf('microphone live') !== -1", timeout=30000)
        page.wait_for_timeout(2500)  # fill window with ambient
        info = page.evaluate(INJECT, b64)
        print("inject  :", info)
        page.wait_for_timeout(1800)
        probe = page.evaluate(PROBE)
        print("probe   :", probe)
        browser.close()
    return 0

if __name__ == "__main__":
    main()
