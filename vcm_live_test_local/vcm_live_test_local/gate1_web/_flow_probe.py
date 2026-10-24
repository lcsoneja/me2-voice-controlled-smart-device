"""Flow probe: does client-side audio processing keep running? Samples state over time."""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/vcm_monitor.html"

SNAP = """() => ({
  rmsLen: (typeof VCM !== 'undefined' && VCM.state && VCM.state.rmsHist) ? VCM.state.rmsHist.length : -1,
  rmsLast: (typeof VCM !== 'undefined' && VCM.state && VCM.state.rmsHist && VCM.state.rmsHist.length) ? VCM.state.rmsHist[VCM.state.rmsHist.length - 1].toFixed(1) : 'n/a',
  send: (function () { try { VCM.send({ type: 'mode', mode: (typeof mode !== 'undefined') ? mode : 'gate1' }); return 'ok'; } catch (e) { return 'err: ' + String(e).slice(0, 80); } })(),
  accLen: (typeof VCM !== 'undefined' && VCM.state && VCM.state.streamAcc) ? VCM.state.streamAcc.length : 'n/a'
})"""

def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page()
        page.goto(URL, wait_until="load", timeout=60000)
        page.wait_for_function("document.getElementById('status').textContent.indexOf('microphone live') !== -1", timeout=30000)
        for i in range(7):
            snap = page.evaluate(SNAP)
            status_tail = page.inner_text("#status").strip().splitlines()[-1] if page.inner_text("#status").strip() else "(empty)"
            print(f"t={i*2+2:>2}s  rmsLen={snap['rmsLen']:>4}  rmsLast={snap['rmsLast']:>6}  send={snap['send'][:20]}  accLen={snap['accLen']}  status: {status_tail[:60]}")
            page.wait_for_timeout(2000)
        browser.close()
    return 0

if __name__ == "__main__":
    main()
