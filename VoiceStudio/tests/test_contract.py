"""Contract tests: VoiceStudio must be a single self-contained offline file."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "VoiceStudio.html"


class VoiceStudioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = APP.read_text(encoding="utf-8") if APP.is_file() else ""

    def test_app_file_exists(self):
        self.assertTrue(APP.is_file(), "VoiceStudio.html missing")
        self.assertGreater(APP.stat().st_size, 20000, "app file suspiciously small")

    def test_single_file_no_external_resources(self):
        html = self.html
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link ", html)
        self.assertNotIn("fetch(", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertIn('id="wave"', html)
        self.assertIn('id="levelFill"', html)

    def test_worklet_inline_via_blob_url(self):
        self.assertIn('registerProcessor("raw-capture"', self.html)
        self.assertIn("URL.createObjectURL(new Blob(", self.html)
        self.assertIn("audioWorklet.addModule", self.html)

    def test_transport_state_machine(self):
        for token in ('"idle"', '"recording"', '"paused"', '"stopped"', '"playing"', '"play-paused"'):
            self.assertIn(token, self.html)
        for action in ("record", "pause", "stop", "play", "delete", "download"):
            self.assertIn('data-action="' + action + '"', self.html)

    def test_wav_zip_csv_builders(self):
        for token in ("encodePcmWav", "buildZip", "crc32", "manifest.csv", "indexedDB.open", "3988292384"):
            self.assertIn(token, self.html)

    def test_inline_phrase_data_93_entries(self):
        match = re.search(r"const PHRASES = (\[[\s\S]*?\]);", self.html)
        if match is None:
            self.fail("inline PHRASES array missing")
        phrases = json.loads(match.group(1))
        self.assertEqual(len(phrases), 93)
        self.assertEqual(len({item["intent"] for item in phrases}), 19)

    def test_keyboard_shortcuts_bound(self):
        for token in ('event.key === "r"', 'event.key === " "', 'event.key === "p"', 'event.key === "Delete"'):
            self.assertIn(token, self.html)

    def test_playback_waveform_elements(self):
        self.assertIn('thumb.className = "thumb"', self.html)
        self.assertIn("decodeAudioData", self.html)
        self.assertIn("computePeaks", self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
