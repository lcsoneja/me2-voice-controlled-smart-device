"""Regression tests for the live all-in-one gate timing contract."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from collections import deque
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

spec = importlib.util.spec_from_file_location("gate1_server_realtime_test", PROJECT / "gate1_server.py")
assert spec is not None and spec.loader is not None
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class TestGateActivationWindows(unittest.TestCase):
    def test_gate1_and_gate2_have_independent_12_and_8_second_latches(self):
        windows = server.PipelineActivationWindows()
        # A single threshold-qualified command tick latches G2 immediately;
        # the latches stay independent of G1.
        self.assertTrue(windows.observe_gate2("COLOR", 0.9, 0.5, 100.0))
        self.assertFalse(windows.gate1_active(100.1))
        self.assertTrue(windows.gate2_active(100.1))
        # In-pair lag: the command can latch 1-2 evaluation ticks before the
        # 2-of-3 wake votes activate G1; within the wake grace it still fires.
        windows.activate_gate1(102.0, "Nova", 0.88)
        self.assertTrue(windows.action_ready(102.1))
        windows.consume_action()
        # Ordered usage: wake first, then the command tick.
        windows.activate_gate1(104.0, "Nova", 0.88)
        self.assertTrue(windows.observe_gate2("LIGHT_ON", 0.9, 0.5, 105.0))
        self.assertTrue(windows.action_ready(105.1))
        windows.consume_action()
        self.assertFalse(windows.action_ready(105.2))
        self.assertTrue(windows.gate1_active(115.99))
        self.assertFalse(windows.gate1_active(116.0))
        self.assertTrue(windows.gate2_active(112.9))
        self.assertFalse(windows.gate2_active(113.1))

    def test_manual_stop_clears_active_latches_and_pending_event(self):
        windows = server.PipelineActivationWindows()
        windows.activate_gate1(100.0, "Nova", 0.9)
        self.assertTrue(windows.observe_gate2("TIMER", 0.95, 0.5, 100.2))
        self.assertTrue(windows.action_ready(100.7))
        windows.manual_stop()
        snapshot = windows.snapshot(100.8)
        self.assertFalse(snapshot["g1"]["active"])
        self.assertFalse(snapshot["g2"]["active"])
        self.assertFalse(snapshot["action_gate"]["active"])
        self.assertFalse(windows.action_ready(100.8))


class TestNegativeRejectAndEventIds(unittest.TestCase):
    def test_negative_reject_never_latches_or_becomes_an_action(self):
        windows = server.PipelineActivationWindows()
        self.assertFalse(windows.observe_gate2("NEGATIVE", 0.99, 0.5, 100.0))
        self.assertFalse(windows.gate2_active(100.5))
        windows.activate_gate1(100.5, "Nova", 0.9)
        self.assertTrue(windows.gate1_active(100.6))
        self.assertFalse(windows.action_ready(100.6))
        snap = windows.snapshot(100.6)
        self.assertIsNone(snap["action_gate"]["intent"])

    def test_confirmed_commands_carry_unique_action_event_ids(self):
        windows = server.PipelineActivationWindows()
        windows.activate_gate1(100.0, "Nova", 0.9)
        self.assertTrue(windows.observe_gate2("LIGHT_ON", 0.8, 0.5, 100.0))
        first = windows.snapshot(100.1)["action_gate"]
        self.assertEqual(first.get("event_id"), windows.g2_event_id)
        self.assertTrue(first["pending"])
        windows.consume_action()
        windows.g2_until = 0.0
        windows.observe_gate2(None, 0.0, 0.5, 101.0)
        windows.activate_gate1(102.0, "Nova", 0.9)
        self.assertTrue(windows.observe_gate2("LIGHT_ON", 0.8, 0.5, 102.0))
        second = windows.snapshot(102.1)["action_gate"]
        self.assertEqual(second.get("event_id"), windows.g2_event_id)
        self.assertNotEqual(first.get("event_id"), second.get("event_id"))


class TestDefaultWakeModel(unittest.TestCase):
    """The pipeline must default to the current shipped wake model.

    Gate1V10 is a sealed-benchmark FAILURE (owner Nova 3/10; README: do NOT
    deploy). Gate1V12 (2026-10-22) took the default after it read the Piattos
    wake word correctly where V8 read it as Nova, and rejected the command words
    V8 false-woke on; the behavioural pins live in _wake_model_registry_test.py.
    gate1v8_f32 stays shipped, selectable, and first in the fallback chain.
    """
    def test_default_gate1_model_is_registerable_and_shipped(self):
        self.assertEqual(server.DEFAULT_G1_MODEL, "gate1v12_f16")
        self.assertIn(server.DEFAULT_G1_MODEL, server.Gates().g1_variants)

    def test_previous_default_stays_shipped_and_first_fallback(self):
        source = (PROJECT / "gate1_server.py").read_text(encoding="utf-8")
        self.assertIn('"gate1v8_f32": ("gate1v8_float32.tflite"', source)
        self.assertIn('for fallback in ("gate1v8_f32", "gate1v8_f16", "gate1v5_f32")', source)

    def test_failed_v10_is_not_the_default(self):
        self.assertNotEqual(server.DEFAULT_G1_MODEL, "gate1v10_f16")


class TestGate2FreshnessAndAmbientFloor(unittest.TestCase):
    """Owner-voice E2E (2026-10-17): stale command latches fired phantom
    actions on a later wake word, and a loud first tracked tick seeded the
    noise floor so every later tick was energy-gated (Piattos cases)."""

    def test_single_command_tick_latches_and_window_repeats_do_not_reLatch(self):
        windows = server.PipelineActivationWindows()
        self.assertTrue(windows.observe_gate2("COLOR", 0.9, 0.5, 100.0))
        self.assertTrue(windows.gate2_active(100.2))
        self.assertFalse(windows.observe_gate2("COLOR", 0.95, 0.5, 100.6))
        self.assertEqual(windows.g2_event_id, 1)

    def test_stale_gate2_latch_cannot_fire_after_a_later_wake(self):
        windows = server.PipelineActivationWindows()
        self.assertTrue(windows.observe_gate2("COLOR", 0.9, 0.5, 100.6))
        windows.activate_gate1(101.0, "Nova", 0.9)
        self.assertTrue(windows.action_ready(101.2))
        # The user wakes again long after the command: both latches overlap,
        # but the aged command utterance must not fire as a phantom action.
        windows.activate_gate1(107.0, "Nova", 0.9)
        self.assertTrue(windows.gate1_active(107.2))
        self.assertTrue(windows.gate2_active(107.2))
        self.assertFalse(windows.action_ready(107.2))
        self.assertFalse(windows.snapshot(107.2)["action_gate"]["triggered"])

    def test_same_command_utterance_cannot_refire_after_window_expiry(self):
        # Owner-voice tick trace (2026-10-17): one ALARM utterance scored >=0.5
        # across many ticks; after the 8s G2 window expired while G1 was still
        # latched, the continuing same-intent scores re-armed a SECOND event and
        # fired the action twice. A new event for the same intent requires an
        # intervening reset (quiet tick / NEGATIVE / below-threshold), not a
        # mere window expiry.
        windows = server.PipelineActivationWindows()
        windows.activate_gate1(100.0, "Nova", 0.9)
        self.assertTrue(windows.observe_gate2("ALARM", 0.99, 0.5, 100.0))
        self.assertTrue(windows.action_ready(100.5))
        windows.consume_action()
        # window expired (g2_until = 108), G1 still active, same intent keeps scoring
        self.assertTrue(windows.gate1_active(109.0))
        self.assertFalse(windows.gate2_active(109.0))
        self.assertFalse(windows.observe_gate2("ALARM", 0.99, 0.5, 109.0))
        self.assertFalse(windows.action_ready(109.5))
        # A genuine repeated command after a quiet reset DOES re-arm.
        self.assertFalse(windows.observe_gate2(None, 0.0, 0.5, 110.0))
        self.assertTrue(windows.observe_gate2("ALARM", 0.99, 0.5, 111.0))
        self.assertTrue(windows.action_ready(111.5))

    def test_command_confirmed_slightly_before_wake_activation_still_fires(self):
        # In-pair ordering: the 5.92s window scores wake and command in the
        # same ticks, so the command can latch one or two evaluation ticks
        # BEFORE the 2-of-3 wake votes activate G1. That same-utterance lag
        # (owner-voice E2E 2026-10-17: 0 actions with a 0.5s grace) must fire.
        windows = server.PipelineActivationWindows()
        self.assertTrue(windows.observe_gate2("ALARM", 1.0, 0.5, 100.0))
        windows.activate_gate1(104.0, "Nova", 0.99)  # wake activates 4s later
        self.assertTrue(windows.gate1_active(104.5))
        self.assertTrue(windows.gate2_active(104.5))
        self.assertTrue(windows.action_ready(104.5))

    def test_command_confirmed_long_before_a_new_wake_must_not_fire(self):
        # Cross-pair staleness: a command latched long before a NEW wake word
        # must never fire as a phantom action on that later wake (the wake at
        # 107.0 lands inside the still-open G2 window: g2_until = 108.0).
        windows = server.PipelineActivationWindows()
        self.assertTrue(windows.observe_gate2("ALARM", 1.0, 0.5, 100.0))
        windows.activate_gate1(107.0, "Nova", 0.99)  # new wake 7s later
        self.assertTrue(windows.gate1_active(107.5))
        self.assertTrue(windows.gate2_active(107.5))
        self.assertFalse(windows.action_ready(107.5))

    def test_loud_first_tracked_tick_must_not_seed_the_noise_floor(self):
        amb = deque(maxlen=30)
        floor = server._track_ambient(amb, 0.132)
        self.assertEqual(floor, 0.005)
        self.assertEqual(len(amb), 0)
        floor = server._track_ambient(amb, 0.132)
        self.assertLess(floor, 0.132)
        server._track_ambient(amb, 0.001)
        self.assertEqual(len(amb), 1)


class TestLiveEvaluationCadence(unittest.TestCase):
    def test_all_in_one_mode_defaults_to_one_second_evaluation(self):
        self.assertEqual(server._inference_interval_s("both", {}), 1.0)
        self.assertEqual(server._inference_interval_s("gate1", {}), 1.0)
        self.assertEqual(server._inference_interval_s("gate2", {"interval_s": 2}), 2.0)


if __name__ == "__main__":
    unittest.main()
