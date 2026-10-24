"""Inject nova.wav over WS, wait for WAKE banner, capture a page screenshot."""
import base64
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
URL = "http://127.0.0.1:8765/gate1_monitor.html"

INJECT_JS = """async (b64) => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  let wav = new Float32Array(bytes.buffer);
  if (wav.length > WIN_SAMPLES) wav = wav.slice(wav.length - WIN_SAMPLES);
  const send = function (f32) {
    pushAudio(f32);
    if (ws && ws.readyState === 1) ws.send(f32);
  };
  let pos = 0;
  while (pos + 4096 <= wav.length) { send(wav.subarray(pos, pos + 4096)); pos += 4096; }
  send(wav.subarray(pos));
}"""


def main() -> int:
    wav_path = HERE.parent / "synthetic_samples" / "gate1_wake_nova_f01_pitchhigh_normal.wav"
    with wave.open(str(wav_path), "rb") as w:
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
        page.wait_for_function(
            "document.getElementById('modelinfo').textContent.length > 5", timeout=30000
        )
        page.wait_for_timeout(1500)
        page.evaluate(INJECT_JS, b64)
        page.wait_for_function(
            "document.getElementById('banner').textContent.indexOf('WAKE DETECTED') === 0",
            timeout=15000,
        )
        # screenshot immediately: the next 1s tick (fake-mic silence) reverts the banner
        out = HERE / "gate1_wake_screenshot.png"
        page.screenshot(path=str(out), full_page=True)
        print("banner:", page.inner_text("#banner").strip())
        print("screenshot:", out)
        browser.close()
    return 0


if __name__ == "__main__":
    main()
