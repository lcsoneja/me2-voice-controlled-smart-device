"""Real browser validation for the phrase recorder, WAV replay, and log export."""
import tempfile
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/gate2_phrase_recorder.html"


def main():
    errors = []
    with tempfile.TemporaryDirectory() as temp_dir, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True, args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-capture",
            "--autoplay-policy=no-user-gesture-required",
        ])
        context = browser.new_context(permissions=["microphone"], accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)[:300]))
        page.goto(URL, wait_until="load", timeout=30000)
        page.wait_for_function("document.querySelectorAll('.record-phrase').length === 31", timeout=10000)
        page.locator(".record-phrase").first.click()
        page.wait_for_function("document.getElementById('status').textContent.includes('Recording')", timeout=15000)
        page.wait_for_timeout(1600)
        with page.expect_download(timeout=10000) as wav_download:
            page.click("#stop-recording")
        wav = wav_download.value
        assert wav.suggested_filename.startswith("gate2_PLAY_MUSIC_play_some_music_")
        assert wav.suggested_filename.endswith(".wav")
        wav_path = Path(temp_dir) / wav.suggested_filename
        wav.save_as(str(wav_path))
        with wave.open(str(wav_path), "rb") as reader:
            assert reader.getnchannels() == 1
            assert reader.getsampwidth() == 2
            assert reader.getframerate() == 48000
            assert reader.getnframes() > 12000
        page.wait_for_selector(".recording-row .test-recording", timeout=5000)
        page.locator(".recording-row .test-recording").first.click()
        try:
            page.wait_for_function("document.getElementById('status').textContent.startsWith('Test complete')", timeout=30000)
        except Exception:
            print("Replay status:", page.locator("#status").inner_text())
            print("Replay raw/clean:", page.locator("#raw-top").inner_text(), page.locator("#clean-top").inner_text())
            print("Page errors:", errors[:5])
            raise
        assert page.locator("#raw-top").inner_text() != "No test yet"
        assert page.locator("#clean-top").inner_text() != "No test yet"
        assert page.locator(".log-row").count() == 1
        try:
            with page.expect_download(timeout=10000) as csv_download:
                page.click("#export-log")
        except Exception:
            print("CSV export status:", page.locator("#status").inner_text())
            print("Page errors:", errors[:5])
            raise
        csv_file = csv_download.value
        csv_path = Path(temp_dir) / csv_file.suggested_filename
        csv_file.save_as(str(csv_path))
        assert "play some music" in csv_path.read_text(encoding="utf-8-sig")
        assert page.locator('a[href="/"]').count() == 1
        page.click("#stop-mic")
        page.wait_for_function("document.getElementById('status').textContent.startsWith('Microphone stopped')", timeout=5000)
        browser.close()
    if errors:
        raise AssertionError("browser page errors: " + repr(errors[:5]))
    print("PASS: labeled PCM16 WAV downloaded; saved audio replayed through raw/RNNoise Gate2; one test logged; CSV exported; mic stopped")


if __name__ == "__main__":
    main()
