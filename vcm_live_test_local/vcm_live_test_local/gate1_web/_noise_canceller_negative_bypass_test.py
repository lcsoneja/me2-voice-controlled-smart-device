"""Regression tests: noise canceller + NEGATIVE-mask bypass (2026-10-17).

Owner request: a noise canceller with a switch, and a single real command
among negative-dominated ticks must still act, with the response attached.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

spec = importlib.util.spec_from_file_location("gate1_server_nc_test", PROJECT / "gate1_server.py")
assert spec is not None and spec.loader is not None
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class TestNegativeMaskBypass(unittest.TestCase):
    LABELS = ["MUSIC_PLAY", "LIGHT_ON", "ALARM_SET", "NEGATIVE"]

    def test_negative_top_promotes_threshold_qualified_command(self):
        # 10 negative-dominated ticks with one real command: the command
        # sits second but meets its per-class threshold -> it must act.
        p2 = np.array([0.12, 0.55, 0.10, 0.80])
        intent, conf = server._g2_candidate_intent(
            p2, self.LABELS, {"ALARM_SET": 0.7}, 0.5)
        self.assertEqual(intent, "LIGHT_ON")
        self.assertAlmostEqual(conf, 0.55)

    def test_negative_top_below_threshold_stays_negative(self):
        p2 = np.array([0.12, 0.40, 0.10, 0.80])
        intent, _ = server._g2_candidate_intent(
            p2, self.LABELS, {}, 0.5)
        self.assertEqual(intent, "NEGATIVE")

    def test_negative_top_uses_per_class_threshold_not_default(self):
        # ALARM_SET at 0.55 beats default 0.5 but its per-class bar is 0.7.
        p2 = np.array([0.10, 0.05, 0.55, 0.80])
        intent, _ = server._g2_candidate_intent(
            p2, self.LABELS, {"ALARM_SET": 0.7}, 0.5)
        self.assertEqual(intent, "NEGATIVE")

    def test_one_qualifying_action_fires_once_after_ten_negative_ticks(self):
        windows = server.PipelineActivationWindows()
        windows.activate_gate1(100.0, "Nova", 0.99)
        negative = np.array([0.08, 0.06, 0.05, 0.81])
        for offset in range(10):
            intent, conf = server._g2_candidate_intent(negative, self.LABELS, {}, 0.5)
            self.assertEqual(intent, "NEGATIVE")
            now = 100.1 + offset
            self.assertFalse(windows.observe_gate2(intent, conf, 0.5, now))
            self.assertFalse(windows.action_ready(now))

        # One threshold-qualified real command is below NEGATIVE, but must
        # pass through the same single-fire gate and retain its event identity.
        mixed = np.array([0.08, 0.58, 0.05, 0.81])
        intent, conf = server._g2_candidate_intent(mixed, self.LABELS, {}, 0.5)
        self.assertEqual(intent, "LIGHT_ON")
        self.assertTrue(windows.observe_gate2(intent, conf, 0.5, 111.0))
        self.assertTrue(windows.action_ready(111.1))
        self.assertEqual(windows.snapshot(111.1)["action_gate"]["event_id"], 1)
        windows.consume_action()
        self.assertFalse(windows.action_ready(111.2))

    def test_command_top_unchanged(self):
        p2 = np.array([0.10, 0.05, 0.90, 0.05])
        intent, conf = server._g2_candidate_intent(
            p2, self.LABELS, {}, 0.5)
        self.assertEqual(intent, "ALARM_SET")
        self.assertAlmostEqual(conf, 0.90)

    def test_labels_without_negative_class_unchanged(self):
        labels = ["MUSIC_PLAY", "LIGHT_ON", "ALARM_SET"]
        p2 = np.array([0.10, 0.55, 0.20])
        intent, _ = server._g2_candidate_intent(p2, labels, {}, 0.5)
        self.assertEqual(intent, "LIGHT_ON")


class TestNoiseCanceller(unittest.TestCase):
    def _noise_window(self, seconds=2.0, seed=7):
        rng = np.random.default_rng(seed)
        n = int(16000 * seconds)
        # Stationary low-frequency hum + hiss: the classic room noise floor.
        t = np.arange(n) / 16000.0
        return (0.05 * np.sin(2 * np.pi * 60 * t)
                + 0.02 * rng.standard_normal(n)).astype(np.float32)

    def test_disabled_and_missing_profile_passthrough(self):
        win = self._noise_window()
        nc = {"enabled": False, "profile": None}
        out = server._nc_apply(win, nc)
        self.assertIs(out, win)
        nc["enabled"] = True
        out = server._nc_apply(win, nc)
        self.assertIs(out, win)

    def test_profile_update_and_noise_reduction(self):
        nc = {"enabled": True, "profile": None}
        quiet = self._noise_window(seed=7)
        server._nc_noise_update(quiet, nc)
        self.assertIsNotNone(nc["profile"])
        # A fresh noise draw from the SAME stationary process must lose power.
        noisy = self._noise_window(seed=99)
        out = server._nc_apply(noisy, nc)
        self.assertEqual(out.shape, noisy.shape)
        self.assertLess(float(np.sqrt(np.mean(out ** 2))),
                        float(np.sqrt(np.mean(noisy ** 2))))

    def test_noise_canceller_preserves_a_command_tone(self):
        noise = self._noise_window(seed=7)
        n = len(noise)
        t = np.arange(n, dtype=np.float64) / 16000.0
        tone = (0.12 * np.sin(2 * np.pi * 900 * t)).astype(np.float32)
        noisy_command = tone + self._noise_window(seconds=n / 16000.0, seed=99)
        nc = {"enabled": True, "profile": None}
        server._nc_noise_update(noise, nc)
        cleaned = server._nc_apply(noisy_command, nc)

        def amplitude_at_900(signal):
            ref = np.exp(-2j * np.pi * 900 * t)
            return 2 * abs(np.vdot(ref, signal.astype(np.float64))) / len(signal)

        # The canceller may attenuate background noise, but must retain the
        # command-band component rather than only preserving broadband RMS.
        self.assertGreater(amplitude_at_900(cleaned), 0.8 * amplitude_at_900(noisy_command))

    def test_profile_ema_blends_updates(self):
        nc = {"enabled": True, "profile": None}
        server._nc_noise_update(self._noise_window(seed=1), nc)
        first = nc["profile"].copy()
        server._nc_noise_update(self._noise_window(seed=2), nc)
        self.assertFalse(np.array_equal(first, nc["profile"]))
        # EMA keeps the profile in the same magnitude range.
        self.assertTrue(np.all(nc["profile"] > 0))

    def test_profile_learns_while_speaking(self):
        # The switch must take effect immediately: a window that is loud
        # everywhere (speech-like) still yields a usable noise profile.
        rng = np.random.default_rng(3)
        n = 16000 * 2
        t = np.arange(n) / 16000.0
        speech = (0.20 * np.sin(2 * np.pi * 900 * t) * (0.4 + 0.6 * np.abs(np.sin(2 * np.pi * 3 * t)))
                  + 0.03 * rng.standard_normal(n)).astype(np.float32)
        nc = {"enabled": True, "profile": None}
        server._nc_noise_update(speech, nc)
        self.assertIsNotNone(nc["profile"])
        out = server._nc_apply(speech, nc)
        self.assertEqual(out.shape, speech.shape)
        self.assertFalse(np.array_equal(out, speech))
        # Noise-floor removal must not erase the tone that carries the command.
        self.assertGreater(float(np.sqrt(np.mean(out ** 2))),
                           0.25 * float(np.sqrt(np.mean(speech ** 2))))

    def test_short_window_passthrough(self):
        nc = {"enabled": True, "profile": None}
        server._nc_noise_update(self._noise_window(), nc)
        short = np.zeros(100, dtype=np.float32)
        out = server._nc_apply(short, nc)
        self.assertEqual(out.shape, short.shape)


if __name__ == "__main__":
    unittest.main()
