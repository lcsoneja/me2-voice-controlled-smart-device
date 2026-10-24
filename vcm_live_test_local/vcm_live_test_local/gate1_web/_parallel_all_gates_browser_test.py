"""Browser E2E smoke for the new ALL GATES · PARALLEL TEST tab.

Requires gate1_server.py on the configured TEST_URL and existing synthetic WAVs.
Uses Edge fake-mic permissions and the app's VCM.inject test hook; no physical mic.
"""
from __future__ import annotations

import base64
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
SYN = PROJECT / "synthetic_samples"
URL = "http://127.0.0.1:8766/"


def b64wav(name: str) -> str:
    with wave.open(str(SYN / name), "rb") as handle:
        channels = handle.getnchannels()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape((-1, channels)).mean(axis=1)
    if rate != 16000:
        raise ValueError(f"E2E fixture must be 16 kHz, got {rate}: {name}")
    return base64.b64encode(audio.astype("<f4").tobytes()).decode("ascii")

REPEAT = """async ([b64, times, gap]) => {
  const bin = atob(b64); const bytes = new Uint8Array(bin.length);
  for (let i=0; i<bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const audio = new Float32Array(bytes.buffer);
  for (let i=0; i<times; i++) {
    VCM.inject(audio);
    await new Promise(resolve => setTimeout(resolve, gap));
  }
  return true;
}"""

STREAM = """([b64, repeats, gap]) => {
  const bin = atob(b64); const bytes = new Uint8Array(bin.length);
  for (let i=0; i<bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const audio = new Float32Array(bytes.buffer);
  window.parallelStreamPromise = (async () => {
    for (let rep=0; rep<repeats; rep++) {
      for (let offset=0; offset<audio.length; offset+=4096) {
        VCM.inject(audio.subarray(offset, Math.min(offset+4096, audio.length)));
        await new Promise(resolve => setTimeout(resolve, gap));
      }
    }
    return true;
  })();
  return true;
}"""


def main() -> int:
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)[:200]))
        page.goto(URL, wait_until="load", timeout=60000)
        page.wait_for_function("document.getElementById('status').textContent.includes('microphone live')", timeout=30000)
        page.wait_for_function("document.getElementById('g1log').children.length > 0", timeout=30000)
        page.click("button[data-tab='parallel']")
        page.wait_for_function("document.getElementById('parallel-g1') !== null", timeout=10000)
        page.evaluate("window.parallelSeen = []; VCM.on('parallel', function (m) { window.parallelSeen.push(m); });")

        nova = b64wav("gate1_wake_nova_f01_pitchhigh_normal.wav")
        color = b64wav("gate4_COLOR_Blue_f10_pitchnorm_normal.wav")
        page.evaluate(REPEAT, [nova, 6, 500])
        page.wait_for_function("document.getElementById('parallel-g1').textContent.includes('WAKE ACTIVE')", timeout=15000)
        page.wait_for_timeout(1300)  # let wake speech roll down before the command
        page.evaluate(STREAM, [color, 2, 220])
        snapshots = []
        for _ in range(24):
            page.wait_for_timeout(250)
            snapshots.append(page.evaluate("({g1:document.getElementById('parallel-g1').textContent,g2:document.getElementById('parallel-g2').textContent,gateN:document.getElementById('parallel-gateN').textContent,gate4:document.getElementById('parallel-gate4').textContent,gate5:document.getElementById('parallel-gate5').textContent,slot:document.getElementById('parallel-slot-value').textContent,action:document.getElementById('parallel-action-status').textContent,stage:document.getElementById('parallel-stage').textContent})"))
            if page.evaluate("document.getElementById('parallel-action-status').textContent.includes('LIGHT ON:') && document.getElementById('parallel-slot-value').textContent.includes('Blue')"):
                break
        parallel_scoring_ok = any("COLOR" in s["g2"] and "Blue" in s["gate4"] and "gateN: waiting for Gate 1 wake" not in s["gateN"] and "gate5: waiting for Gate 1 wake" not in s["gate5"] and "branches scored concurrently" in s["stage"] for s in snapshots)
        rendered = page.evaluate("""() => {
          VCMPARALLEL.update({type:"parallel", stage:"deterministic action-render check",
            g1:{active:true,wake:"Nova",conf:0.95,remaining_s:6,rms:0.03,floor:0.005},
            gate2:{intent:"COLOR",conf:0.99,threshold:0.5,active:true},
            specialists:{gateN:{top:"10 seconds",conf:0.91},gate4:{top:"Blue",conf:0.997},gate5:{top:"Exercise",conf:0.93}},
            action:{active:true,intent:"COLOR",route:"gate4",gate:"gate4",value:"Blue",slot_conf:0.997,light:true,triggered:true}});
          return {status:document.getElementById("parallel-action-status").textContent,
            slot:document.getElementById("parallel-slot-value").textContent,
            ledOn:document.getElementById("parallel-led-COLOR").classList.contains("on"),
            selected:document.getElementById("parallel-card-COLOR").classList.contains("selected")};
        }""")
        action_render_ok = rendered["status"].startswith("LIGHT ON:") and "Blue" in rendered["slot"] and rendered["ledOn"] and rendered["selected"]
        print("snapshots=", ascii(snapshots[-8:]))
        gate_values = {name: page.inner_text("#parallel-" + name).strip() for name in ("g1", "g2", "gateN", "gate4", "gate5", "slot-value", "action-status", "stage")}
        print("parallel_tab=loaded; g1=", ascii(gate_values["g1"]))
        print("g2=", ascii(gate_values["g2"]))
        print("gateN=", ascii(gate_values["gateN"]))
        print("gate4=", ascii(gate_values["gate4"]))
        print("gate5=", ascii(gate_values["gate5"]))
        print("slot=", ascii(gate_values["slot-value"]))
        print("action=", ascii(gate_values["action-status"]))
        print("stage=", ascii(gate_values["stage"]))
        print("parallel_gate_scores=", "PASS" if parallel_scoring_ok else "FAIL")
        print("parallel_action_light_render=", "PASS" if action_render_ok else "FAIL", ascii(rendered))
        if errors:
            print("page_errors=", errors[:5])
        page.screenshot(path=str(HERE / "parallel_all_gates_e2e.png"))
        browser.close()
    return 0 if parallel_scoring_ok and action_render_ok and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
