"""v5 check: inject nova + piattos over WS in gate1 mode; verify probs arrive."""
import base64
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
URL = "http://127.0.0.1:8765/vcm_monitor.html"
SYN = HERE.parent / "synthetic_samples"

INJECT = """async (b64) => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  VCM.inject(new Float32Array(bytes.buffer));
  return VCM.state.streamAcc ? VCM.state.streamAcc.length : 'n/a';
}"""

PROBE = """() => ({
  lastP1: VCM.state.lastP1,
  logRows: document.getElementById('g1log').children.length,
  derived: (document.getElementById('g1derived') || {}).textContent || 'no-row'
})"""


def b64wav(fname):
    with wave.open(str(SYN / fname), "rb") as w:
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return base64.b64encode(y.astype("<f4").tobytes()).decode()


def main() -> int:
    import numpy as np  # noqa: F401
    errs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        page.goto(URL, wait_until="load", timeout=60000)
        page.wait_for_function("document.getElementById('status').textContent.indexOf('microphone live') !== -1", timeout=30000)
        page.wait_for_timeout(2500)
        for fname in ("gate1_wake_nova_f01_pitchhigh_normal.wav", "gate1_wake_piattos_m01_pitchnorm_fast.wav"):
            page.evaluate(INJECT, b64wav(fname))
            page.wait_for_timeout(3000)
            probe = page.evaluate(PROBE)
            print(fname[:34], "-> lastP1:", probe["lastP1"], "| logRows:", probe["logRows"], "| derived:", probe["derived"])
        page.screenshot(path=str(HERE / "v5_gate1_check.png"))
        browser.close()
    print("pageerrors:", errs[:3])
    return 0


if __name__ == "__main__":
    main()
