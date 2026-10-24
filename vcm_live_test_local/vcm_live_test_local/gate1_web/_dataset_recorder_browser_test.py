"""Browser smoke: per-phrase transport, live pane, take player, exports, persistence."""
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/dataset_recorder.html"


class DatasetRecorderBrowserTests(unittest.TestCase):
    def test_full_workflow(self):
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
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(URL, wait_until="load", timeout=30000)
            page.wait_for_function("document.querySelectorAll('.record-phrase').length === 93", timeout=10000)
            self.assertEqual(page.locator("#monitorPane").count(), 1)
            self.assertEqual(page.locator(".stop-take:not([disabled])").count(), 0)

            play_row = page.locator('.prow', has=page.locator('.record-phrase[data-phrase="Play music"]'))
            self.assertEqual(play_row.count(), 1)
            play_row.locator(".record-phrase").click()
            page.wait_for_function("document.getElementById('recState').textContent.includes('Recording')", timeout=15000)
            active_stop = play_row.locator(".stop-take")
            self.assertEqual(page.locator(".stop-take:enabled").count(), 1)
            self.assertTrue(active_stop.is_enabled())
            e1 = page.locator("#elapsed").inner_text()
            page.wait_for_timeout(1200)
            e2 = page.locator("#elapsed").inner_text()
            self.assertNotEqual(e1, e2, "elapsed counter not ticking")
            painted = page.evaluate(
                "(() => { const c = document.getElementById('wave'); const x = c.getContext('2d');"
                " const d = x.getImageData(0, 0, c.width, c.height).data; let n = 0;"
                " for (let i = 0; i < d.length; i += 4) {"
                " if (Math.abs(d[i] - 13) + Math.abs(d[i+1] - 17) + Math.abs(d[i+2] - 23) > 30) n++; }"
                " return n; })()"
            )
            self.assertGreater(painted, 150, "live waveform never painted")

            # Live Gate 2 pane: window fills (~6s) then inferences stream
            page.wait_for_function("document.getElementById('miniTop').textContent !== '\u2014'", timeout=16000)
            self.assertGreaterEqual(page.locator("#miniLog").inner_text().count("\n"), 0)
            chart_painted = page.evaluate(
                "(() => { const c = document.getElementById('miniChart'); const x = c.getContext('2d');"
                " const d = x.getImageData(0, 0, c.width, c.height).data; let n = 0;"
                " for (let i = 0; i < d.length; i += 4) {"
                " if (Math.abs(d[i] - 13) + Math.abs(d[i+1] - 17) + Math.abs(d[i+2] - 23) > 30) n++; }"
                " return n; })()"
            )
            self.assertGreater(chart_painted, 80, "mini chart never painted")

            active_stop.click()
            page.wait_for_function("document.getElementById('recState').textContent.includes('Idle')", timeout=10000)
            self.assertEqual(page.locator(".logrow").count(), 1)
            select = play_row.locator(".take-select")
            self.assertTrue(select.is_enabled())
            selected_label = select.locator(":scope option:checked").text_content() or ""
            self.assertIn("take #1", selected_label)

            # Take player: select => mini player appears; play toggles; delete works
            select.select_option(index=0)
            self.assertEqual(page.locator(".mini-player").count(), 1)
            mini_play = page.locator(".mini-play")
            mini_play.click()
            page.wait_for_timeout(400)
            self.assertEqual(mini_play.text_content(), "\u23f8")
            mini_dur_text = page.locator(".mini-dur").first.text_content()
            if mini_dur_text is None:
                self.fail("mini-dur text missing")
            duration_match = re.search(r"([0-9.]+)s", mini_dur_text)
            if duration_match is None:
                self.fail("mini-dur text unparsable: " + mini_dur_text)
            play_wait_s = float(duration_match.group(1)) + 5.0
            page.wait_for_function("document.querySelector('.mini-play').textContent === '\u25b6'", timeout=play_wait_s * 1000)
            page.locator(".mini-delete").click()
            page.wait_for_function("document.querySelectorAll('.logrow').length === 0", timeout=10000)
            self.assertFalse(select.is_enabled())
            self.assertEqual(page.locator("#countTotal").text_content(), "0")

            # Escape stops an in-progress recording without saving
            play_row.locator(".record-phrase").click()
            page.wait_for_function("document.getElementById('recState').textContent.includes('Recording')", timeout=15000)
            page.keyboard.press("Escape")
            page.wait_for_function("document.getElementById('recState').textContent.includes('Idle')", timeout=10000)
            self.assertEqual(page.locator(".logrow").count(), 0)

            # Record once more for export + persistence checks
            play_row.locator(".record-phrase").click()
            page.wait_for_function("document.getElementById('recState').textContent.includes('Recording')", timeout=15000)
            page.wait_for_timeout(1400)
            play_row.locator(".stop-take").click()
            page.wait_for_function("document.querySelectorAll('.logrow').length === 1", timeout=10000)

            with page.expect_download(timeout=10000) as csv_download:
                page.click("#export-csv")
            csv_path = Path(temp_dir) / csv_download.value.suggested_filename
            csv_download.value.save_as(str(csv_path))
            csv_text = csv_path.read_text(encoding="utf-8-sig")
            self.assertIn("file_name,intent,phrase,recorded_at,duration_seconds,sample_rate", csv_text)
            self.assertIn("Play music", csv_text)

            with page.expect_download(timeout=20000) as zip_download:
                page.click("#export-zip")
            zip_path = Path(temp_dir) / zip_download.value.suggested_filename
            zip_download.value.save_as(str(zip_path))
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
                wavs = [name for name in names if name.startswith("recordings/PLAY_MUSIC/") and name.endswith(".wav")]
                self.assertEqual(len(wavs), 1)
                self.assertIn("manifest.csv", names)
                self.assertIn("README.txt", names)
                self.assertEqual(archive.read(wavs[0])[:4], b"RIFF")

            page.reload(wait_until="load")
            page.wait_for_function("document.querySelectorAll('.record-phrase').length === 93", timeout=10000)
            page.wait_for_function("document.querySelectorAll('.logrow').length === 1", timeout=10000)

            # After reload the mic is off on the fresh page: assert the pane state
            # instead of clicking the (legitimately disabled) stop-mic button.
            page.wait_for_function("document.getElementById('micState').textContent.includes('off')", timeout=10000)
            self.assertFalse(page.locator("#stopMic").is_enabled())
            browser.close()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
