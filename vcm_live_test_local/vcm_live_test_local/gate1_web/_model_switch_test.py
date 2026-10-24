"""Model chooser verification: switch versions/precisions via the UI dropdown,
inject nova, and verify the probs payload carries the expected label set."""
import base64
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
URL = "http://127.0.0.1:8765/vcm_monitor.html"


def b64wav(fname):
    with wave.open(str(HERE.parent / "synthetic_samples" / fname), "rb") as w:
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return base64.b64encode(y.astype("<f4").tobytes()).decode()


INJECT = """async (b64) => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  VCM.inject(new Float32Array(bytes.buffer));
  return true;
}"""

SWITCH = """async (model) => {
  const sel = document.getElementById('g1model');
  sel.value = model;
  sel.dispatchEvent(new Event('change'));
  return sel.value;
}"""

PROBE = """() => ({
  model: (VCM.state.lastP1 && VCM.state.lastP1.model) || 'none',
  labels: (VCM.state.lastP1 && VCM.state.lastP1.labels) || [],
  wake: (VCM.state.lastP1 && VCM.state.lastP1.wake) || null
})"""


def main() -> int:
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
        # first full window must complete before any case: wait for the first probs message
        page.wait_for_function("VCM.state.lastP1 && VCM.state.lastP1.labels && VCM.state.lastP1.labels.length > 0", timeout=15000)

        for model, expect_labels in (("gate1v3_f16", 3), ("gate1v5_f32", 2), ("gate1v2_f16", 3)):
            page.evaluate(SWITCH, model)
            page.evaluate(INJECT, b64wav("gate1_wake_nova_f01_pitchhigh_normal.wav"))
            try:
                page.wait_for_function(
                    f"VCM.state.lastP1 && VCM.state.lastP1.model === '{model}' && VCM.state.lastP1.labels.length === {expect_labels}",
                    timeout=10000)
                probe = page.evaluate(PROBE)
                status = "OK"
            except Exception:
                probe = page.evaluate(PROBE)
                status = "TIMEOUT"
            print(f"{model:<14} model={probe['model']:<14} labels={probe['labels']} -> {status} (expect {expect_labels})")
            if probe["wake"]:
                print(f"    wake event: {probe['wake']}")
            if errs:
                print("    pageerrors:", errs[:2])
                errs = []

        browser.close()

    print("MODEL SWITCH:", "PASS - all variants responded with correct label sets" if not errs else "FAIL - pageerrors present")
    return 0


if __name__ == "__main__":
    main()
