"""Tests for 20-second rolling memory, model windows, and pipeline frame helpers."""
from __future__ import annotations

import importlib.util
import unittest
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
SR = 16000
WIN_SAMPLES = 94720  # model window: 5.92 s at 16 kHz


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "failed to load module spec"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFrameMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load("pipeline_frames", PROJECT / "pipeline_frames.py")

    def test_memory_keeps_last_20_one_second_frames(self):
        mem = deque(maxlen=self.mod.FRAME_MEMORY_SECONDS)
        for i in range(25):
            self.mod.append_second_frame(mem, np.full(SR, float(i), dtype=np.float32), SR)
        self.assertEqual(self.mod.FRAME_MEMORY_SECONDS, 20)
        self.assertEqual(len(mem), 20)
        self.assertEqual(int(mem[-1][0]), 24)   # newest frame kept
        self.assertEqual(int(mem[0][0]), 5)     # oldest of the last 20

    def test_short_frame_is_front_padded_to_one_second(self):
        mem = deque(maxlen=self.mod.FRAME_MEMORY_SECONDS)
        self.mod.append_second_frame(mem, np.full(SR // 4, 7.0, dtype=np.float32), SR)
        self.assertEqual(len(mem), 1)
        self.assertEqual(mem[0].shape[0], SR)
        self.assertTrue(np.all(mem[0][: SR - SR // 4] == 0.0))
        self.assertTrue(np.all(mem[0][SR - SR // 4:] == 7.0))

    def test_frame_window_joins_six_frames_and_trims_to_model_window(self):
        mem = deque(maxlen=self.mod.FRAME_MEMORY_SECONDS)
        for i in range(8):
            self.mod.append_second_frame(mem, np.full(SR, float(i), dtype=np.float32), SR)
        win = self.mod.frame_window(mem, WIN_SAMPLES)
        self.assertIsNotNone(win)
        self.assertEqual(win.shape[0], WIN_SAMPLES)
        self.assertEqual(int(win[-1]), 7)       # newest audio kept after trim

    def test_frame_window_none_until_six_frames(self):
        mem = deque(maxlen=self.mod.FRAME_MEMORY_SECONDS)
        for i in range(5):
            self.mod.append_second_frame(mem, np.full(SR, float(i), dtype=np.float32), SR)
        self.assertIsNone(self.mod.frame_window(mem, WIN_SAMPLES))

    def test_gate3_window_uses_latest_eight_seconds(self):
        mem = deque(maxlen=self.mod.FRAME_MEMORY_SECONDS)
        for i in range(7):
            self.mod.append_second_frame(mem, np.full(SR, float(i), dtype=np.float32), SR)
        self.assertIsNone(self.mod.frame_window(mem, 8 * SR))
        self.mod.append_second_frame(mem, np.full(SR, 7.0, dtype=np.float32), SR)
        win = self.mod.frame_window(mem, 8 * SR)
        self.assertIsNotNone(win)
        self.assertEqual(win.shape[0], 8 * SR)
        self.assertEqual(float(win[0]), 0.0)
        self.assertEqual(float(win[-1]), 7.0)

    def test_late_ticks_advance_to_future_deadline_without_catchup(self):
        deadline, skipped = self.mod.advance_deadline(4.0, 4.3, 2.0)
        self.assertAlmostEqual(deadline, 6.0)
        self.assertEqual(skipped, 1)
        deadline, skipped = self.mod.advance_deadline(4.0, 8.1, 2.0)
        self.assertAlmostEqual(deadline, 10.0)
        self.assertEqual(skipped, 3)
        deadline, skipped = self.mod.advance_deadline(4.0, 3.9, 2.0)
        self.assertAlmostEqual(deadline, 4.0)
        self.assertEqual(skipped, 0)

    def test_frame_window_normalizes_short_frames_to_one_second_each(self):
        # Frames are stored as exact 1-second blocks, so six frames always form
        # a 6-second window trimmed to the 5.92 s model input; newest audio wins.
        mem = deque(maxlen=self.mod.FRAME_MEMORY_SECONDS)
        for _ in range(6):
            self.mod.append_second_frame(mem, np.full(SR // 2, 1.0, dtype=np.float32), SR)
        win = self.mod.frame_window(mem, WIN_SAMPLES)
        self.assertIsNotNone(win)
        self.assertEqual(win.shape[0], WIN_SAMPLES)
        self.assertEqual(float(win[-1]), 1.0)
        self.assertEqual(float(win[0]), 0.0)  # front silence from the first frame padding


class TestPathIndicator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load("pipeline_frames", PROJECT / "pipeline_frames.py")

    def test_steps_without_wake_show_idle_path(self):
        steps = self.mod.pipe_path_steps(
            g1={"active": False, "activation_label": None, "label": "scanning…"},
            g2=None, spec=None, action_gate=None, g2_ran=False)
        self.assertEqual([s["gate"] for s in steps], ["G1", "ACTION"])
        self.assertFalse(steps[0]["on"])
        self.assertFalse(steps[-1]["on"])

    def test_steps_full_routed_path_in_order(self):
        steps = self.mod.pipe_path_steps(
            g1={"active": True, "activation_label": "Nova", "activation_conf": 0.93},
            g2={"active": True, "activation_intent": "COLOR", "activation_conf": 0.87, "threshold": 0.5},
            spec={"gate": "gate4", "label": "Blue", "conf": 0.997},
            action_gate={"triggered": True, "intent": "COLOR"},
            g2_ran=True)
        self.assertEqual([s["gate"] for s in steps], ["G1", "G2", "G4", "ACTION"])
        self.assertTrue(steps[-1]["on"])

    def test_gateN_is_displayed_as_G3(self):
        steps = self.mod.pipe_path_steps(
            g1={"active": True, "activation_label": "Nova", "activation_conf": 0.9},
            g2={"active": True, "activation_intent": "TIMER", "activation_conf": 0.9, "threshold": 0.5},
            spec={"gate": "gateN", "label": "10 seconds", "conf": 0.91},
            action_gate={"triggered": True, "intent": "TIMER"},
            g2_ran=True)
        self.assertIn("G3", [s["gate"] for s in steps])

    def test_path_text_mentions_light_first_and_values(self):
        steps = self.mod.pipe_path_steps(
            g1={"active": True, "activation_label": "Nova", "activation_conf": 0.93},
            g2={"active": True, "activation_intent": "COLOR", "activation_conf": 0.87, "threshold": 0.5},
            spec={"gate": "gate4", "label": "Blue", "conf": 0.997},
            action_gate={"triggered": True, "intent": "COLOR"},
            g2_ran=True)
        text = self.mod.pipe_path_text(steps)
        for token in ("Nova", "COLOR", "Blue", "LIGHT ON", "%"):
            self.assertIn(token, text)


class TestOwnerVoiceEval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load("owner_voice_eval", PROJECT / "owner_voice_eval.py")

    def test_manifest_loader_parses_columns(self):
        csv_text = ('file_name,intent,phrase\n'
                    'recordings/ALARM/a.wav,ALARM,Alarm 6 AM\n'
                    'recordings/COLOR/b.wav,COLOR,change color to blue\n')
        entries = self.mod.load_manifest_text(csv_text)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["intent"], "ALARM")
        self.assertEqual(entries[1]["phrase"], "change color to blue")

    def test_predict_fn_receives_native_waveform(self):
        # The model preprocessing pads/crops per utterance (training contract);
        # batch evaluation must NOT emulate the live 5.92 s sliding window.
        seen = []
        def predict_fn(waveform, entry):
            seen.append((waveform.shape[0], entry["file"]))
            return (entry["intent"], 1.0)
        entries = [{"file": "a.wav", "intent": "ALARM", "phrase": "x"}]
        self.mod.evaluate_recordings(entries, predict_fn,
                                     loader=lambda path, entry: np.zeros(16, dtype=np.float32))
        self.assertEqual(seen, [(16, "a.wav")])

    def test_accuracy_per_intent_and_mismatches(self):
        entries = [
            {"file": "a.wav", "intent": "ALARM", "phrase": "Alarm 6 AM"},
            {"file": "b.wav", "intent": "ALARM", "phrase": "Alarm 7 AM"},
            {"file": "c.wav", "intent": "COLOR", "phrase": "change color to blue"},
        ]
        preds = {"a.wav": ("ALARM", 0.9), "b.wav": ("TIMER", 0.4), "c.wav": ("COLOR", 0.8)}
        def predict_fn(waveform, entry):
            return preds[entry["file"]]
        summary = self.mod.evaluate_recordings(entries, predict_fn,
                                               loader=lambda path, entry: np.full(SR, 0.1, dtype=np.float32))
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["correct"], 2)
        self.assertAlmostEqual(summary["accuracy"], 2 / 3)
        self.assertEqual(summary["per_intent"]["ALARM"], {"total": 2, "correct": 1, "accuracy": 0.5})
        self.assertEqual(summary["per_intent"]["COLOR"], {"total": 1, "correct": 1, "accuracy": 1.0})
        self.assertEqual(len(summary["mismatches"]), 1)
        self.assertEqual(summary["mismatches"][0]["file"], "b.wav")
        self.assertEqual(summary["mismatches"][0]["expected"], "ALARM")
        self.assertEqual(summary["mismatches"][0]["predicted"], "TIMER")


class TestPipelinePageContract(unittest.TestCase):
    def test_html_has_memory_path_accuracy_and_lights_first_order(self):
        html = (PROJECT / "gate1_web" / "vcm_monitor.html").read_text(encoding="utf-8")
        for element in ('id="pipe-memory"', 'id="pipe-path"', 'id="pipe-accuracy"'):
            self.assertIn(element, html)
        self.assertLess(html.index('id="pipe-action"'), html.index('id="pipe-spec"'),
                        "action light row must come before the specialist row (lights 1st)")

    def test_pipeline_js_renders_memory_path_and_accuracy(self):
        js = (PROJECT / "gate1_web" / "js" / "pipeline.js").read_text(encoding="utf-8")
        for token in ('pipe-memory', 'pipe-path', 'pipe-accuracy', 'PATH:', 'ACCURACY:'):
            self.assertIn(token, js)

    def test_server_uses_frame_memory_wake_gated_g2_and_payload_path(self):
        src = (PROJECT / "gate1_server.py").read_text(encoding="utf-8")
        self.assertIn("frame_mem", src)
        self.assertIn("frame_window(", src)
        self.assertIn("g2_ran", src)
        self.assertIn('"memory":', src)
        self.assertIn('payload["path"]', src)
        self.assertIn("light_on", src)

    def test_server_has_owner_voice_evaluation_route(self):
        src = (PROJECT / "gate1_server.py").read_text(encoding="utf-8")
        self.assertIn("owner_voice_eval", src)
        self.assertIn("/api/owner-voice/evaluate", src)
        self.assertIn("owner_voice_test", src)

    def test_frame_pending_only_accumulates_in_pipe_mode(self):
        # gate1/gate2/parallel ticks never consume frame_pending; unconditional
        # accumulation would leak memory for as long as the mic streams.
        src = (PROJECT / "gate1_server.py").read_text(encoding="utf-8")
        self.assertIn('if mode == "both":\n                    frame_pending.append(arr)', src)

    def test_page_has_owner_voice_accuracy_panel(self):
        html = (PROJECT / "gate1_web" / "vcm_monitor.html").read_text(encoding="utf-8")
        for element in ('id="pipe-ownervoice"', 'id="pipe-ownervoice-summary"',
                        'id="pipe-ownervoice-perintent"', 'id="pipe-ownervoice-mismatches"'):
            self.assertIn(element, html)


if __name__ == "__main__":
    unittest.main()
