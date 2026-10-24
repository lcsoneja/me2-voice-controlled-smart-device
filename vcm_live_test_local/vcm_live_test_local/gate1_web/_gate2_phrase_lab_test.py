"""Contract checks for the separate Gate2 phrase recording/replay lab."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = ROOT.parent / "gate1_server.py"
DATA = ROOT / "data" / "gate2_phrases.json"


class Gate2PhraseLabTests(unittest.TestCase):
    def test_separate_page_route_data_and_navigation(self):
        server = SERVER.read_text(encoding="utf-8")
        monitor = (ROOT / "vcm_monitor.html").read_text(encoding="utf-8")
        ab_page = (ROOT / "gate2_rnnoise_test.html").read_text(encoding="utf-8")
        page_path = ROOT / "gate2_phrase_recorder.html"
        self.assertIn('/gate2_phrase_recorder.html', server)
        self.assertTrue(page_path.is_file())
        self.assertTrue(DATA.is_file())
        page = page_path.read_text(encoding="utf-8")
        self.assertIn('href="/"', page)
        self.assertIn("gate2_phrase_recorder.html", monitor)
        self.assertIn("gate2_rnnoise_test.html", page)
        self.assertIn("gate2_rnnoise_test_2s.html", page)
        self.assertIn("gate2_rnnoise_test.html", monitor)
        self.assertIn("gate2_rnnoise_test_2s.html", monitor)
        self.assertIn("gate2_phrase_recorder.html", ab_page)

    def test_all_31_labeled_examples_have_record_controls(self):
        self.assertTrue(DATA.is_file())
        phrases = json.loads(DATA.read_text(encoding="utf-8"))
        self.assertEqual(len(phrases), 31)
        self.assertEqual(len({item["phrase"] for item in phrases}), 31)
        js_path = ROOT / "js" / "gate2_phrase_recorder.js"
        self.assertTrue(js_path.is_file())
        js = js_path.read_text(encoding="utf-8")
        shared = (ROOT / "js" / "shared.js").read_text(encoding="utf-8")
        self.assertIn("record-phrase", js)
        for item in phrases:
            self.assertIn(item["phrase"], shared)
        storage = (ROOT / "js" / "gate2_phrase_lab_storage.js").read_text(encoding="utf-8")
        self.assertIn("encodePcmWav", storage)
        self.assertIn("wavFilename", storage)
        self.assertIn(".wav", js)

    def test_local_replay_dual_gate2_and_csv_log_contract(self):
        js_path = ROOT / "js" / "gate2_phrase_recorder.js"
        self.assertTrue(js_path.is_file())
        js = js_path.read_text(encoding="utf-8")
        audio = (ROOT / "js" / "gate2_phrase_lab_audio.js").read_text(encoding="utf-8")
        storage = (ROOT / "js" / "gate2_phrase_lab_storage.js").read_text(encoding="utf-8")
        for token in ("testRecording", "interval_s", "probs2", "raw", "clean"):
            self.assertIn(token, audio)
        self.assertIn("indexedDB", storage)
        self.assertIn("exportLogCsv", js)
        worklet = (ROOT / "js" / "rnnoise-worklet.js").read_text(encoding="utf-8")
        self.assertIn('"reset"', worklet)


if __name__ == "__main__":
    unittest.main(verbosity=2)
