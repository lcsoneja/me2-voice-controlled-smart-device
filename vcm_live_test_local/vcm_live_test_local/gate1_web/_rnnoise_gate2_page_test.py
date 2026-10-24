"""Contract tests for the isolated Gate2 RNNoise A/B page."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SERVER = ROOT.parent / "gate1_server.py"


class Gate2RnnoisePageTests(unittest.TestCase):
    def test_page_route_and_self_hosted_assets_exist(self):
        server = SERVER.read_text(encoding="utf-8")
        self.assertIn('/gate2_rnnoise_test.html', server)
        self.assertTrue((ROOT / "gate2_rnnoise_test.html").is_file())
        self.assertTrue((ROOT / "js" / "gate2_rnnoise_test.js").is_file())
        self.assertTrue((ROOT / "js" / "rnnoise-worklet.js").is_file())
        self.assertTrue((ROOT / "vendor" / "rnnoise" / "rnnoise-sync.js").is_file())
        self.assertTrue((ROOT / "vendor" / "rnnoise" / "LICENSE").is_file())

    def test_page_lists_all_read_aloud_gate2_phrases(self):
        html = (ROOT / "gate2_rnnoise_test.html").read_text(encoding="utf-8")
        phrases = [
            "play some music", "what's the weather today", "what time is it",
            "turn on the lights", "turn off the lights", "pause the music", "stop", "next song",
            "turn the volume up", "turn the volume down", "call mom", "send a message to john",
            "list my reminders", "set a timer for 10 seconds", "set a timer for 30 seconds",
            "set a timer for 1 minute", "set an alarm for 6 am", "set an alarm for 8 am",
            "set an alarm for 9 pm", "set the temperature to 18 degrees",
            "set the temperature to 22 degrees", "set the temperature to 26 degrees",
            "set brightness to 20 percent", "set brightness to 60 percent", "set brightness to 100 percent",
            "make the lights red", "make the lights blue", "make the lights green",
            "remind me to drink water", "remind me to study", "remind me to exercise",
        ]
        self.assertIn("phrases-to-read", html)
        self.assertEqual(html.count('class="read-phrase"'), len(phrases))
        for phrase in phrases:
            self.assertIn('class="read-phrase">' + phrase + '</li>', html)

    def test_both_panels_use_independent_gate2_streams(self):
        js_path = ROOT / "js" / "gate2_rnnoise_test.js"
        self.assertTrue(js_path.is_file())
        js = js_path.read_text(encoding="utf-8")
        self.assertIn('mode: "gate2"', js)
        self.assertIn('raw', js.lower())
        self.assertIn('rnnoise', js.lower())
        self.assertIn('probs2', js)
        self.assertIn('WebSocket', js)

    def test_two_second_variant_has_its_own_route_and_interval_setting(self):
        server = SERVER.read_text(encoding="utf-8")
        html = (ROOT / "gate2_rnnoise_test.html").read_text(encoding="utf-8")
        js = (ROOT / "js" / "gate2_rnnoise_test.js").read_text(encoding="utf-8")
        self.assertIn('/gate2_rnnoise_test_2s.html', server)
        self.assertIn('id="interval-variant"', html)
        self.assertIn('endsWith("_2s.html")', js)
        self.assertIn('interval_s:', js)

    def test_worklet_processes_exact_rnnoise_frames(self):
        worklet_path = ROOT / "js" / "rnnoise-worklet.js"
        self.assertTrue(worklet_path.is_file())
        worklet = worklet_path.read_text(encoding="utf-8")
        self.assertIn("480", worklet)
        self.assertIn("createRNNWasmModuleSync", worklet)
        self.assertIn("_rnnoise_process_frame", worklet)
        self.assertIn("registerProcessor", worklet)


if __name__ == "__main__":
    unittest.main(verbosity=2)
