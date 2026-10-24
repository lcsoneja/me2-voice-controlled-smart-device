#!/usr/bin/env python3
"""Wake-gate registry: the 2026-10-22 Gate1V12 default, V8C's missing adapter.

V12 keeps the (1,148,60,1) contract so it rides the v8 stats; V8C is (1,49,40,1)
and stays listed as disabled. The behavioural checks re-score the synthetic wake
and command clips, which is where the V8 default misread Piattos as Nova and
false-woke on "Stop".

Run: py -3.12 -m pytest gate1_web/_wake_model_registry_test.py
"""

from __future__ import annotations

import sys
import unittest
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
APP = HERE.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import gate1_server as server  # noqa: E402

SYN = APP / "synthetic_samples"
V12 = "gate1v12_f16"
V8C = "gate1v8c_f16"
DASHBOARD = HERE / "pipeline_all_in_one.html"


def windowed(name: str) -> np.ndarray:
    with wave.open(str(SYN / name), "rb") as handle:
        audio = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)
    audio = audio.astype(np.float32) / 32768.0
    pad = max(0, server.WIN_SAMPLES - audio.shape[0])
    return np.concatenate([np.zeros(pad, dtype=np.float32), audio])[-server.WIN_SAMPLES :]


class WakeRegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gates = server.Gates()

    def test_v12_is_the_default_and_registered(self):
        self.assertEqual(server.DEFAULT_G1_MODEL, V12)
        self.assertIn(V12, self.gates.g1_variants)

    def test_v12_contract_matches_the_v8_frontend(self):
        spec = self.gates.g1_variants[V12]
        self.assertEqual(spec["in_shape"], (1, server.TARGET_148, server.N_MELS, 1))
        self.assertEqual(spec["labels"], ["Nova", "Piattos", "Negative"])
        self.assertIs(spec["pre"], self.gates.prev8)
        self.assertAlmostEqual(float(spec["pre"].mean), 0.02904, places=4)

    def test_v8c_is_listed_disabled_with_its_adapter_reason(self):
        self.assertIn(V8C, server.GATE1_DISABLED_CANDIDATES)
        self.assertIn("49x40", server.GATE1_DISABLED_CANDIDATES[V8C])
        self.assertNotIn(V8C, self.gates.g1_variants)

    def test_v8c_staged_model_still_needs_that_adapter(self):
        staged = HERE / "gate1v8c_float16.tflite"
        self.assertTrue(staged.is_file(), "staged V8C model missing from gate1_web/")
        spec = server._make_interpreter(staged).get_input_details()[0]
        self.assertEqual(tuple(int(d) for d in spec["shape"]), (1, 49, 40, 1))

    def test_v12_reads_both_wake_words_and_rejects_command_words(self):
        cases = {
            "gate1_wake_nova_f01_pitchhigh_normal.wav": "Nova",
            "gate1_wake_piattos_m01_pitchnorm_fast.wav": "Piattos",
            "gate2_CALL_f04_pitchlow_normal.wav": "Negative",
            "gate2_STOP_f06_pitchhigh_normal.wav": "Negative",
        }
        for clip, expected in cases.items():
            probs, labels, _ = self.gates.infer_g1_variant(V12, windowed(clip))
            self.assertEqual(labels[int(np.argmax(probs))], expected, clip)

    def test_v8_default_regression_is_documented(self):
        # The regression that motivated the switch: V8 reads the Piattos clip as
        # Nova and scores "Stop" as a wake word. Pinned so a future V8 reload is
        # not mistaken for a passing wake gate.
        probs, labels, _ = self.gates.infer_g1_variant("gate1v8_f32", windowed("gate1_wake_piattos_m01_pitchnorm_fast.wav"))
        self.assertEqual(labels[int(np.argmax(probs))], "Nova")
        probs, labels, _ = self.gates.infer_g1_variant("gate1v8_f32", windowed("gate2_STOP_f06_pitchhigh_normal.wav"))
        self.assertEqual(labels[int(np.argmax(probs))], "Nova")

    def test_dashboard_selector_offers_v12_and_flags_v8c(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('<option value="gate1v12_f16" selected>', html)
        self.assertIn('<option value="gate1v8_f32">', html)
        self.assertIn('<option value="gate1v8c_f16" disabled>', html)
        self.assertNotIn('<option value="gate1v8_f32" selected>', html)


if __name__ == "__main__":
    unittest.main()
