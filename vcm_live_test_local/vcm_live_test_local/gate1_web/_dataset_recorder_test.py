"""Contract tests for the dataset recorder: per-phrase transport + live monitor pane."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = ROOT.parent / "gate1_server.py"
DATA = ROOT / "data" / "gate2_collection_phrases.json"

EXPECTED_COUNTS = {
    "ALARM": 9, "BRIGHTNESS": 9, "CALL": 3, "COLOR": 9, "CREATE_REMINDER": 9,
    "LIGHT_OFF": 3, "LIGHT_ON": 3, "LIST_REMINDERS": 3, "MESSAGE": 3, "NEXT": 3,
    "PAUSE": 3, "PLAY_MUSIC": 3, "STOP": 3, "TEMPERATURE": 9, "TIME": 3,
    "TIMER": 9, "VOLUME_DOWN": 3, "VOLUME_UP": 3, "WEATHER": 3,
}


class DatasetRecorderPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = SERVER.read_text(encoding="utf-8")
        cls.monitor = (ROOT / "vcm_monitor.html").read_text(encoding="utf-8")
        cls.html = (ROOT / "dataset_recorder.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "js" / "dataset_recorder.js").read_text(encoding="utf-8")

    def test_route_page_and_data_exist_with_monitor_link(self):
        self.assertIn("/dataset_recorder.html", self.server)
        self.assertTrue(DATA.is_file())
        self.assertIn("/dataset_recorder.html", self.monitor)

    def test_data_lists_all_93_phrases_across_19_intents(self):
        phrases = json.loads(DATA.read_text(encoding="utf-8"))
        self.assertEqual(len(phrases), 93)
        self.assertEqual(len({item["phrase"] for item in phrases}), 93)
        counts = {}
        for item in phrases:
            counts[item["intent"]] = counts.get(item["intent"], 0) + 1
        for intent, count in EXPECTED_COUNTS.items():
            self.assertEqual(counts.get(intent), count, intent)
        for sample in ("Wake me up at 9 PM", "Kill the lights", "What time is it?", "Timer 30 seconds", "What's the weather?", "Skip song"):
            self.assertIn(sample, [item["phrase"] for item in phrases])

    def test_layout_has_scroll_left_and_sticky_right_pane(self):
        self.assertIn('class="layout"', self.html)
        self.assertIn('id="monitorPane"', self.html)
        self.assertIn("position:sticky", self.html.replace(" ", ""))
        self.assertIn('id="recState"', self.html)
        self.assertIn('id="micState"', self.html)
        self.assertIn('id="elapsed"', self.html)
        self.assertIn('id="levelFill"', self.html)
        self.assertIn('id="wave"', self.html)
        self.assertIn('id="miniTop"', self.html)
        self.assertIn('id="miniConf"', self.html)
        self.assertIn('id="miniChart"', self.html)
        self.assertIn('id="miniLog"', self.html)
        self.assertIn('id="stopMic"', self.html)

    def test_per_phrase_row_has_record_stop_and_take_select(self):
        self.assertIn("record-phrase", self.js)
        self.assertIn("stop-take", self.js)
        self.assertIn("take-select", self.js)
        self.assertIn("mini-canvas", self.js)
        self.assertIn("mini-play", self.js)
        self.assertIn("mini-delete", self.js)
        self.assertIn("take #", self.js)
        self.assertNotIn('id="stop-recording"', self.html)

    def test_js_streams_gate2_and_uses_shared_thresholds(self):
        self.assertIn('mode: "gate2"', self.js)
        self.assertIn("vcm_thr_g2", self.js)
        self.assertIn("vcm_thr", self.js)
        self.assertIn("probs2", self.js)
        self.assertIn("encodePcmWav", self.js)
        self.assertIn("buildZip", self.js)
        self.assertIn("crc32", self.js)
        self.assertIn("dataset_recorder_log.csv", self.js)
        self.assertIn("indexedDB", self.js)
        self.assertIn("manifest.csv", self.js)
        self.assertIn("Escape", self.js)
        self.assertIn("3988292384", self.js)
        worklet = (ROOT / "js" / "raw-capture-worklet.js").read_text(encoding="utf-8")
        self.assertIn('registerProcessor("raw-capture"', worklet)


if __name__ == "__main__":
    unittest.main(verbosity=2)
