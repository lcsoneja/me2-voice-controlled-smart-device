"""Probe: does the browser page's WS deliver injected audio to the server?"""
import base64
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
LOG = HERE.parent / "ws_received.log"


def b64wav(name):
    with wave.open(str(HERE.parent / "synthetic_samples" / name), "rb") as f:
        y = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return base64.b64encode(y.astype("<f4").tobytes()).decode()


INJECT = """async (b64) => {
  const bin = atob(b64);
  const u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  VCM.inject(new Float32Array(u.buffer));
  return true;
}"""


def last_count():
    try:
        lines = LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        return int(lines[-1].split("samples:")[1].split("at")[0].strip()) if lines else 0
    except Exception:
        return -1


def main() -> int:
    errs = []
    before = last_count()
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required"])
        page = b.new_page()
        page.on("pageerror", lambda e: errs.append("pageerror: " + str(e)[:160]))
        page.goto("http://127.0.0.1:8765/vcm_monitor.html", wait_until="load", timeout=60000)
        page.wait_for_function("VCM.state.lastP1 && VCM.state.lastP1.labels && VCM.state.lastP1.labels.length > 0", timeout=20000)
        for i in range(7):
            if i == 1:
                page.evaluate(INJECT, b64wav("gate1_wake_nova_f01_pitchhigh_normal.wav"))
            state = page.evaluate("""() => ({
                wsOpen: VCM.send({ type: "noop" }),
                rms: VCM.state.lastP1.rms,
                nova: VCM.state.lastP1.nova,
                wake: VCM.state.lastP1.wake
            })""")
            print(i, "wsOpen:", state["wsOpen"], "| rms:", state["rms"], "| nova:", round(state["nova"], 4), "| wake:", state["wake"])
            page.wait_for_timeout(1000)
        b.close()
    after = last_count()
    print("ws_received samples before:", before, "after:", after, "delta:", after - before)
    print("pageerrors:", errs[:4] or "none")
    return 0


if __name__ == "__main__":
    main()
