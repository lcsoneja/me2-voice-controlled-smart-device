"""Browser smoke test for the dual Gate2 RNNoise page; expects server on localhost:8765."""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/gate2_rnnoise_test.html"


def main():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        context = browser.new_context(permissions=["microphone"])
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)[:240]))
        page.goto(URL, wait_until="load", timeout=30000)
        page.click("#start")
        page.wait_for_function("document.getElementById('status').textContent.includes('RNNoise is ready')", timeout=30000)
        page.wait_for_function("document.getElementById('raw-top').textContent !== 'Waiting for audio' && document.getElementById('clean-top').textContent !== 'Waiting for audio'", timeout=30000)
        page.select_option("#expected", "CALL")
        assert page.locator("#raw-match").inner_text()
        assert page.locator("#clean-match").inner_text()
        assert page.locator("#raw-connection").inner_text() != "idle"
        assert page.locator("#clean-connection").inner_text() != "idle"
        page.click("#stop")
        page.wait_for_function("document.getElementById('status').textContent.startsWith('Stopped')", timeout=5000)
        page.goto(URL.replace("gate2_rnnoise_test.html", "gate2_rnnoise_test_2s.html"), wait_until="load", timeout=30000)
        assert page.locator("#cadence-label").inner_text() == "2 seconds"
        page.click("#start")
        page.wait_for_function("document.getElementById('status').textContent.includes('RNNoise is ready')", timeout=30000)
        page.wait_for_function("document.getElementById('raw-top').textContent !== 'Waiting for audio' && document.getElementById('clean-top').textContent !== 'Waiting for audio'", timeout=30000)
        assert page.locator("#interval-variant").inner_text() == "Use 1-second updates"
        page.click("#stop")
        page.wait_for_function("document.getElementById('status').textContent.startsWith('Stopped')", timeout=5000)
        browser.close()
    if errors:
        raise AssertionError("browser page errors: " + repr(errors[:5]))
    print("PASS: WASM ready; both Gate2 streams updated; expected-command comparison rendered; stop closed session")


if __name__ == "__main__":
    main()
