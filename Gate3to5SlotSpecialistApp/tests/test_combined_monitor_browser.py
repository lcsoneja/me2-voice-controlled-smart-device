"""Browser smoke test for Gate3–Gate5 integration inside the existing monitor."""
import io

import numpy as np
import soundfile as sf
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/"


def synthetic_wav():
    rate = 16000
    time = np.arange(rate, dtype=np.float32) / rate
    samples = (0.05 * np.sin(2.0 * np.pi * 440.0 * time)).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, samples, rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


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
        page.locator('button[data-tab="gate3to5"]').click()
        page.wait_for_function("document.getElementById('sec-gate3to5').classList.contains('active')", timeout=5000)
        frame = page.frame_locator("#gate3to5-frame")
        frame.locator("h1").wait_for(timeout=30000)
        assert frame.locator("h1").inner_text() == "Slot Specialist Bench"
        gate_values = frame.locator("#gate option").evaluate_all("options => options.map(option => option.value)")
        assert gate_values[0] == "" and "gate4_color" not in gate_values
        assert frame.locator("#ratio option").evaluate_all("options => options.map(option => option.value)") == ["", "neg1x", "neg2x"]
        assert frame.locator(".main-monitor-link").get_attribute("target") == "_top"
        frame.locator("#gate").select_option("gate3a_timer")
        frame.locator("#ratio").select_option("neg1x")
        frame.locator("#audio").set_input_files({"name": "synthetic_tone.wav", "mimeType": "audio/wav", "buffer": synthetic_wav()})
        frame.locator("#run").click()
        frame.locator("#result").wait_for(state="visible", timeout=30000)
        assert frame.locator("#selected").inner_text() == "gate3a_timer · neg1x"
        assert frame.locator(".score-row").count() == 4
        assert "uncalibrated" in frame.locator(".scores-head").inner_text().lower()
        browser.close()
    if errors:
        raise AssertionError("browser page errors: " + repr(errors[:5]))
    print("PASS: one-server monitor embeds clip-level Gate3–Gate5 app; synthetic clip returns four uncalibrated scores")


if __name__ == "__main__":
    main()
