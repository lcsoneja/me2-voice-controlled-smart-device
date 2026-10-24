"""Playwright smoke test using a generated synthetic WAV only."""
import io
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8765/gate3to5/"
BUNDLE = Path(__file__).resolve().parents[2] / "Shipping" / "Gate3to5_SlotSpecialists_Candidates_20261009"


def synthetic_wav():
    rate = 16000
    time = np.arange(rate, dtype=np.float32) / rate
    signal = (0.05 * np.sin(2.0 * np.pi * 440.0 * time)).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, signal, rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def main():
    errors = []
    labels = json.loads((BUNDLE / "labels.json").read_text(encoding="utf-8"))["gate3a_timer"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)[:250]))
        page.goto(BASE_URL, wait_until="load", timeout=30000)
        page.wait_for_function("document.querySelectorAll('#gate option').length === 6", timeout=10000)
        gate_values = page.locator("#gate option").evaluate_all("options => options.map(option => option.value)")
        ratio_values = page.locator("#ratio option").evaluate_all("options => options.map(option => option.value)")
        assert gate_values[0] == "" and "gate4_color" not in gate_values
        assert ratio_values == ["", "neg1x", "neg2x"]
        page.select_option("#gate", "gate3a_timer")
        page.select_option("#ratio", "neg1x")
        page.set_input_files("#audio", {"name": "synthetic_tone.wav", "mimeType": "audio/wav", "buffer": synthetic_wav()})
        page.click("#run")
        page.wait_for_function("!document.getElementById('result').hidden", timeout=30000)
        assert "gate3a_timer" in page.locator("#selected").inner_text()
        assert "neg1x" in page.locator("#selected").inner_text()
        assert page.locator(".score-row").count() == 4
        displayed = page.locator(".score-label").all_text_contents()
        assert displayed == labels
        assert "uncalibrated" in page.locator("#result-note").inner_text().lower()
        assert not errors, errors
        browser.close()
    print("PASS: no default gate/ratio; Gate4 excluded; synthetic WAV scored by selected candidate; 4 JSON-ordered scores displayed")


if __name__ == "__main__":
    main()
