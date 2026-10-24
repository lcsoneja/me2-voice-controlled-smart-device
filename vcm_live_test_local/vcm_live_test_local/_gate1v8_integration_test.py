"""TDD contract for Gate1 V8 integration (run: python _gate1v8_integration_test.py)."""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import gate1_server as server  # noqa: E402

EXPECTED_LABELS = ["Nova", "Piattos", "Negative"]


class Gate1V8IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gates = server.Gates()
        cls.source = (ROOT / "gate1_server.py").read_text(encoding="utf-8")
        cls.shared = (ROOT / "gate1_web" / "js" / "shared.js").read_text(encoding="utf-8")
        cls.pipeline = (ROOT / "gate1_web" / "js" / "pipeline.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "gate1_web" / "vcm_monitor.html").read_text(encoding="utf-8")

    def test_v8_precision_assets_are_installed_unchanged(self):
        self.assertTrue((ROOT / "gate1_web" / "gate1v8_float32.tflite").is_file())
        self.assertTrue((ROOT / "gate1_web" / "gate1v8_float16.tflite").is_file())
        self.assertTrue((ROOT / "gate1_web" / "feature_stats_v8_148.npz").is_file())

    def test_v8_variants_load_with_declared_order_and_probabilities(self):
        for key in ("gate1v8_f32", "gate1v8_f16"):
            with self.subTest(model=key):
                self.assertIn(key, self.gates.g1_variants)
                model = self.gates.g1_variants[key]
                self.assertEqual(model["labels"], EXPECTED_LABELS)
                self.assertEqual(model["in_shape"], (1, 148, 60, 1))
                probs, labels, is_two_class = self.gates.infer_g1_variant(key, np.zeros(server.WIN_SAMPLES, np.float32))
                self.assertEqual(labels, EXPECTED_LABELS)
                self.assertFalse(is_two_class)
                self.assertEqual(len(probs), 3)
                self.assertTrue(np.all(np.isfinite(probs)))
                self.assertAlmostEqual(sum(probs), 1.0, places=3)

    def test_energy_floor_suppresses_wake_even_if_model_scores_nova_high(self):
        self.assertIsNone(server._wake_candidate([0.99, 0.005, 0.005], {"Nova": 0.5, "Piattos": 0.5}, rms=0.001, floor=0.005))
        self.assertEqual(server._wake_candidate([0.99, 0.005, 0.005], {"Nova": 0.5, "Piattos": 0.5}, rms=0.02, floor=0.005), "Nova")
        self.assertEqual(server._wake_candidate([0.005, 0.99, 0.005], {"Nova": 0.5, "Piattos": 0.5}, rms=0.02, floor=0.005), "Piattos")

    def test_gate1_status_does_not_relabel_silent_high_nova_as_wake(self):
        start = self.shared.index("function deriveGate1State(message)")
        end = self.shared.index("function updateGate1Derived(status)", start)
        body = self.shared[start:end]
        self.assertNotIn("nova >= thr.Nova", body)
        self.assertNotIn("piattos >= thr.Piattos", body)
        self.assertLess(body.index("if (winRms < floor)"), body.index("if (message.wake)"))

    def test_independent_gate_windows_overlap_in_either_order_and_fire_once(self):
        gate2_first = server.PipelineActivationWindows()
        gate2_first.observe_gate2("PLAY_MUSIC", 0.8, 0.5, now=10.0)
        self.assertEqual(gate2_first.g2_until, 14.0)
        self.assertFalse(gate2_first.action_ready(now=10.0))
        gate2_first.activate_gate1(now=12.0, label="Nova", confidence=0.9)
        self.assertEqual(gate2_first.g1_until, 20.0)
        self.assertTrue(gate2_first.action_ready(now=12.0))
        gate2_first.consume_action()
        self.assertFalse(gate2_first.action_ready(now=12.1))

        gate1_first = server.PipelineActivationWindows()
        gate1_first.activate_gate1(now=0.0, label="Piattos", confidence=0.8)
        gate1_first.observe_gate2("CALL", 0.8, 0.5, now=7.5)
        self.assertTrue(gate1_first.action_ready(now=7.5))
        self.assertFalse(gate1_first.action_ready(now=8.0))

    def test_gate2_window_requires_confidence_and_does_not_refresh_same_intent(self):
        state = server.PipelineActivationWindows()
        state.observe_gate2("CALL", 0.49, 0.5, now=0.0)
        self.assertEqual(state.g2_until, 0.0)
        state.observe_gate2("CALL", 0.8, 0.5, now=1.0)
        self.assertEqual(state.g2_until, 5.0)
        state.observe_gate2("CALL", 0.8, 0.5, now=2.0)
        self.assertEqual(state.g2_until, 5.0)
        self.assertEqual(state.g2_event_id, 1)

    def test_pipeline_scores_gate2_continuously_and_exposes_action_gate(self):
        start = self.source.index("else:  # both")
        end = self.source.index("except asyncio.CancelledError", start)
        pipeline = self.source[start:end]
        self.assertIn('p2 = gates.infer("gate2", win)', pipeline)
        self.assertLess(pipeline.index('p2 = gates.infer("gate2", win)'), pipeline.rindex("attach_action_result(payload, win, monotonic_now)"))
        self.assertIn('id="pipe-action"', self.html)
        self.assertIn("msg.action_gate", self.pipeline)

    def test_level_rms_uses_recent_second_not_full_window(self):
        win = np.zeros(server.WIN_SAMPLES, np.float32)
        loud = np.full(server.SR, 0.5, np.float32)  # last second is loud speech
        win[-server.SR:] = loud
        self.assertGreater(server._level_rms(win), 0.4)
        quiet = np.zeros(server.WIN_SAMPLES, np.float32)
        quiet[: server.SR] = np.full(server.SR, 0.5, np.float32)  # loud 6s ago only
        self.assertLess(server._level_rms(quiet), 0.05)

    def test_gate2_per_phrase_thresholds_are_activation_thresholds(self):
        start = self.source.index("activations.observe_gate2(current_intent")
        line = self.source[start:self.source.index("\n", start)]
        self.assertIn("g2_threshold", line)
        self.assertNotIn('thr["gate2MinConf"]', line)
        # Gate2 tab owns a phrase picker + slider and a compact chart canvas.
        self.assertIn('id="g2chart"', self.html)
        self.assertIn('id="g2phrase"', self.html)

    def test_pipeline_stage_cards_show_last_known_values_not_bare_dashes(self):
        self.assertIn("last:", self.pipeline)
        self.assertIn("below floor", self.pipeline)
        # The old bare placeholders must be gone from the stage-card paths.
        self.assertNotIn('"G2: — (no wake)"', self.pipeline)
        self.assertNotIn('"SPEC: —"', self.pipeline)

    def test_wake_dominant_window_suppresses_gate2_events(self):
        self.assertEqual(server.WAKE_DOMINANT_CONF, 0.7)
        self.assertTrue(server._gate2_suppressed([0.86, 0.1, 0.04]))
        self.assertTrue(server._gate2_suppressed([0.05, 0.9, 0.05]))
        self.assertFalse(server._gate2_suppressed([0.2, 0.3, 0.5]))
        start = self.source.index("if _gate2_suppressed(p1)")
        end = self.source.index("observe_gate2(current_intent", start)
        block = self.source[start:end]
        self.assertIn('observe_gate2(None', block)  # reset intent memory when suppressed

    def test_ticker_uses_configured_per_connection_interval(self):
        ticker_start = self.source.index("async def ticker()")
        ticker_end = self.source.index("tick = asyncio.create_task(ticker())", ticker_start)
        ticker = self.source[ticker_start:ticker_end]
        self.assertIn("tick_interval_changed.wait()", ticker)
        self.assertIn("timeout=tick_interval", ticker)
        self.assertNotIn("asyncio.sleep(1.0)", ticker)

    def test_gate2_inference_interval_defaults_to_one_and_allows_two(self):
        self.assertEqual(server._inference_interval_s("gate2", {}), 1.0)
        self.assertEqual(server._inference_interval_s("gate2", {"interval_s": 2}), 2.0)
        self.assertEqual(server._inference_interval_s("gate1", {"interval_s": 2}), 1.0)
        self.assertEqual(server._inference_interval_s("gate2", {"interval_s": "2"}), 1.0)

    def test_ambient_floor_ignores_audio_ticks(self):
        amb = server.deque([0.02] * 10, maxlen=20)
        floor = server._track_ambient(amb, 0.2)  # audio tick: must not be tracked
        self.assertEqual(len(amb), 10)
        self.assertEqual(floor, 0.05)
        self.assertEqual(server._track_ambient(amb, 0.015), 0.05)  # quiet tick tracked
        self.assertEqual(len(amb), 11)
        floor3 = None
        for _ in range(30):
            floor3 = server._track_ambient(amb, 0.1)  # sustained audio never escalates
        self.assertEqual(floor3, 0.05)
        amb2 = server.deque(maxlen=20)
        self.assertEqual(server._track_ambient(amb2, 0.03), 0.075)  # first tick = baseline

    def test_v8_is_default_and_pipeline_uses_selected_gate1_model(self):
        self.assertIn('g1_model = "gate1v8_f32"', self.source)
        self.assertGreaterEqual(self.source.count("gates.infer_g1_variant(g1_model, win)"), 2)
        self.assertIn('modelSel.value = "gate1v8_f32"', self.shared)
        self.assertIn('"v8"', self.shared)


if __name__ == "__main__":
    unittest.main(verbosity=2)
