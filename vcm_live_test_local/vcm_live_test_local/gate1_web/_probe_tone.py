"""Decisive delivery probe: page injects a loud tone; watch server tail RMS."""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent

INJECT_TONE = """async () => {
  const tone = new Float32Array(9600);           // 0.6 s at 16 kHz
  for (let i = 0; i < tone.length; i++) tone[i] = 0.9 * Math.sin(2 * Math.PI * 440 * i / 16000);
  VCM.inject(tone);
  const acc = VCM.state.streamAcc;
  const tail = acc.slice(-tone.length);
  let s = 0;
  for (let i = 0; i < tail.length; i++) s += tail[i] * tail[i];
  return Math.sqrt(s / Math.max(1, tail.length));   // client-side tail rms
}"""


def server_count() -> int:
    log = HERE.parent / "ws_received.log"
    try:
        with log.open(encoding="utf-8", errors="replace") as fh:
            lines = [line for line in fh.read().strip().splitlines() if "samples:" in line]
        return int(lines[-1].split("samples:")[1].split("at")[0].strip())
    except Exception:
        return -1


def main() -> int:
    errs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:150]))
        page.goto("http://127.0.0.1:8765/vcm_monitor.html", wait_until="load", timeout=60000)
        page.wait_for_function("VCM.state.lastP1 && VCM.state.lastP1.labels && VCM.state.lastP1.labels.length > 0", timeout=20000)

        client_rms = page.evaluate(INJECT_TONE)
        for tick in range(5):
            page.wait_for_timeout(1000)
            print(tick, "clientTailRms:", round(client_rms, 3),
                  "| serverRms:", page.evaluate("() => VCM.state.lastP1.rms"),
                  "| serverCount:", server_count())
        print("pageerrors:", errs[:3] or "none")
        browser.close()
    return 0


if __name__ == "__main__":
    main()
