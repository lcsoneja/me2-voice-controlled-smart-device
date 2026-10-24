"""Diagnose the Gate 2 tab failure: server-side inference on the exact window
compositions, then a browser poll of #g2top over time."""
import base64
import importlib.util
import sys
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
spec = importlib.util.spec_from_file_location("ls", HERE.parent / "live_session.py")
assert spec is not None and spec.loader is not None, "failed to load live_session.py spec"
ls = importlib.util.module_from_spec(spec)
sys.argv = ["x"]
spec.loader.exec_module(ls)
gs = importlib.import_module("gate1_server")  # multi-gate inference (gate1v2/gate2/gateN/gate4/gate5)

g = gs.Gates()
labels = g.labels["gate2"]
WIN = gs.WIN_SAMPLES


def wav_samples(fname):
    with wave.open(str(HERE.parent / "synthetic_samples" / fname), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


call = wav_samples("gate2_CALL_f04_pitchlow_normal.wav")

# composition A: call at the very tail (injection instant = window end)
bufA = np.zeros(WIN, dtype=np.float32)
bufA[WIN - len(call):] = call
pA = g.infer("gate2", bufA)
print("A (call at tail)      :", labels[int(np.argmax(pA))], round(float(np.max(pA)), 3))

# composition B: 2.5 s of silence after the call (E2E check instant)
gap = int(2.5 * 16000)
bufB = np.zeros(WIN, dtype=np.float32)
start = WIN - gap - len(call)
if start < 0:
    bufB[:] = call[-WIN:]
else:
    bufB[start : start + len(call)] = call
pB = g.infer("gate2", bufB)
print("B (call 2.5s before end):", labels[int(np.argmax(pB))], round(float(np.max(pB)), 3))

# ---- browser poll ----
b64 = base64.b64encode(call.astype("<f4").tobytes()).decode()
INJECT = """async (b64) => {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  VCM.inject(new Float32Array(bytes.buffer));
  return VCM.state.streamAcc.length;
}"""

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True, args=[
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-capture",
        "--autoplay-policy=no-user-gesture-required",
    ])
    page = browser.new_page()
    page.goto("http://127.0.0.1:8765/vcm_monitor.html", wait_until="load", timeout=60000)
    page.wait_for_function("document.getElementById('g1log').children.length > 0", timeout=30000)
    page.click("button[data-tab='gate2']")
    page.wait_for_timeout(400)
    if page.locator("#g2chips .chip", has_text="call mom").count():
        page.click("#g2chips .chip:has-text('call mom')")
    page.evaluate(INJECT, b64)
    for i in range(7):
        page.wait_for_timeout(1000)
        top = page.inner_text("#g2top").strip()
        verd = page.inner_text("#g2verdict").strip()[:30]
        print(f"  t+{i + 1}s  top='{top}'  verdict='{verd}'")
    browser.close()
