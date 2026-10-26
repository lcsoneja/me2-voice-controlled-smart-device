"""Browser smoke test for VoiceStudio via file:// with a synthetic mic.
Exercises the full transport: record, pause (gap cut), resume, stop, playback,
pause/resume playback, WAV download, CSV + ZIP exports, persistence, delete,
and keyboard shortcuts. Audio is a synthetic tone; no private recordings.
"""
import re
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

APP = Path(__file__).resolve().parents[1] / "VoiceStudio.html"
URL = APP.as_uri()


class VoiceStudioBrowserTests(unittest.TestCase):
    def test_full_transport_workflow(self):
        errors = []
        with tempfile.TemporaryDirectory() as temp_dir, sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True, args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-capture",
                "--autoplay-policy=no-user-gesture-required",
                "--allow-file-access-from-files",
            ])
            context = browser.new_context(permissions=["microphone"], accept_downloads=True)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)[:300]))
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(URL, wait_until="load", timeout=30000)
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Idle'", timeout=10000)

            # Record 1s, pause 1s (gap must be cut), resume 1s, stop => ~2s take
            page.select_option("#phrase", "Alarm 6 AM")
            page.click('[data-action="record"]')
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Recording'", timeout=10000)
            page.wait_for_timeout(1000)
            page.click('[data-action="pause"]')
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Paused'", timeout=5000)
            page.wait_for_timeout(1000)
            page.click('[data-action="pause"]')
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Recording'", timeout=5000)
            page.wait_for_timeout(1000)
            painted = page.evaluate(
                "(() => { const c = document.getElementById('wave'); const x = c.getContext('2d');"
                " const d = x.getImageData(0, 0, c.width, c.height).data; let n = 0;"
                " for (let i = 0; i < d.length; i += 4) {"
                " if (Math.abs(d[i] - 13) + Math.abs(d[i+1] - 17) + Math.abs(d[i+2] - 23) > 30) n++; }"
                " return n; })()"
            )
            self.assertGreater(painted, 200, "live waveform canvas never painted")
            page.click('[data-action="stop"]')
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Stopped'", timeout=10000)
            self.assertEqual(page.locator(".take-row").count(), 1)
            duration_text = page.locator(".take-row .dur").first.inner_text()
            match = re.search(r"([0-9.]+) s", duration_text)
            if match is None:
                self.fail("duration text missing: " + duration_text)
            duration = float(match.group(1))
            self.assertGreaterEqual(duration, 1.6)
            self.assertLessEqual(duration, 2.6)

            # Playback: play, pause playback, resume, stop
            page.locator(".play-take").first.click()
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Playing'", timeout=10000)
            page.click('[data-action="pause"]')
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Play-paused'", timeout=5000)
            page.click('[data-action="pause"]')
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Playing'", timeout=5000)
            page.click('[data-action="stop"]')
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Stopped'", timeout=5000)

            # WAV download
            with page.expect_download(timeout=10000) as wav_download:
                page.click('[data-action="download"]')
            wav_path = Path(temp_dir) / wav_download.value.suggested_filename
            wav_download.value.save_as(str(wav_path))
            self.assertTrue(wav_path.name.startswith("gate2_ALARM__alarm_6_am__"))
            with wave.open(str(wav_path), "rb") as reader:
                self.assertEqual(reader.getnchannels(), 1)
                self.assertEqual(reader.getsampwidth(), 2)
                self.assertEqual(reader.getframerate(), 48000)
                self.assertGreaterEqual(reader.getnframes(), int(1.6 * 48000))
                self.assertLessEqual(reader.getnframes(), int(2.6 * 48000))

            # CSV + ZIP exports
            with page.expect_download(timeout=10000) as csv_download:
                page.click("#exportCsv")
            csv_path = Path(temp_dir) / csv_download.value.suggested_filename
            csv_download.value.save_as(str(csv_path))
            csv_text = csv_path.read_text(encoding="utf-8-sig")
            self.assertIn("file_name,intent,phrase,label,recorded_at,duration_seconds,sample_rate", csv_text)
            self.assertIn("Alarm 6 AM", csv_text)
            with page.expect_download(timeout=20000) as zip_download:
                page.click("#exportZip")
            zip_path = Path(temp_dir) / zip_download.value.suggested_filename
            zip_download.value.save_as(str(zip_path))
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
                wavs = [name for name in names if name.startswith("recordings/ALARM/") and name.endswith(".wav")]
                self.assertEqual(len(wavs), 1)
                self.assertIn("manifest.csv", names)
                self.assertIn("README.txt", names)
                self.assertIn("Alarm 6 AM", archive.read("manifest.csv").decode("utf-8-sig"))
                self.assertEqual(archive.read(wavs[0])[:4], b"RIFF")

            # Persistence across reload
            page.reload(wait_until="load")
            page.wait_for_function("document.querySelectorAll('.take-row').length === 1", timeout=10000)
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Stopped'", timeout=10000)

            # Keyboard shortcuts: R records, Space stops/saves, Delete removes
            page.keyboard.press("r")
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Recording'", timeout=10000)
            page.wait_for_timeout(700)
            page.keyboard.press(" ")
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Stopped'", timeout=10000)
            self.assertEqual(page.locator(".take-row").count(), 2)
            page.keyboard.press("Delete")
            page.wait_for_function("document.querySelectorAll('.take-row').length === 1", timeout=10000)
            page.keyboard.press("Delete")
            page.wait_for_function("document.querySelectorAll('.take-row').length === 0", timeout=10000)
            page.wait_for_function("document.getElementById('stateChip').textContent === 'Idle'", timeout=5000)
            browser.close()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
