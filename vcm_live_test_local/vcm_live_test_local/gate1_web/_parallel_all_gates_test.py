"""RED unit tests for parallel specialist inference and intent action lights."""
from __future__ import annotations

# pyright: reportMissingImports=false
import threading
import unittest
from pathlib import Path

import numpy as np

from gate1_server import Gates
from parallel_pipeline import run_in_parallel, select_parallel_action

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ParallelAllGatesTests(unittest.TestCase):
    def test_all_four_branches_run_concurrently(self):
        barrier = threading.Barrier(4)

        def branch(value):
            barrier.wait(timeout=3)
            return value

        got = run_in_parallel({
            "gate2": lambda: branch("intent"),
            "gateN": lambda: branch("numeric"),
            "gate4": lambda: branch("color"),
            "gate5": lambda: branch("reminder"),
        })
        self.assertEqual(set(got), {"gate2", "gateN", "gate4", "gate5"})
        self.assertEqual(got["gate2"], "intent")

    def test_gates_infer_parallel_returns_gate2_and_all_specialists(self):
        gates = object.__new__(Gates)
        gates.gate2_labels = lambda: ["TIMER", "WEATHER"]
        gates.gate2_active_model = lambda: "gate2v2"
        gates.infer_gate2 = lambda waveform: [0.9, 0.1]
        gates.labels = {
            "gateN": ["10 seconds", "1 minute"],
            "gate4": ["Red", "Blue"],
            "gate5": ["Exercise", "Study"],
        }
        raw = {"gateN": [0.8, 0.2], "gate4": [0.1, 0.9], "gate5": [0.7, 0.3]}
        gates.infer = lambda name, waveform: raw[name]
        results = gates.infer_parallel(np.zeros(16000, dtype=np.float32))
        self.assertEqual(set(results["specialists"]), {"gateN", "gate4", "gate5"})
        self.assertEqual(results["gate2"]["top"], "TIMER")
        self.assertEqual(results["specialists"]["gate4"]["top"], "Blue")

    def test_gate1_wake_is_required_for_action_light(self):
        result = select_parallel_action(
            wake_active=False, intent="TIMER", intent_confidence=0.95, threshold=0.5,
            specialists={"gateN": {"label": "10 seconds", "conf": 0.9}},
            routing={"TIMER": "gateN"},
        )
        self.assertFalse(result["active"])
        self.assertIsNone(result["value"])

    def test_gate2_threshold_is_required_for_action_light(self):
        result = select_parallel_action(
            wake_active=True, intent="TIMER", intent_confidence=0.4, threshold=0.5,
            specialists={"gateN": {"label": "10 seconds", "conf": 0.9}},
            routing={"TIMER": "gateN"},
        )
        self.assertFalse(result["active"])

    def test_timer_color_reminder_show_routed_gate_value(self):
        specialists = {
            "gateN": {"label": "10 seconds", "conf": 0.91},
            "gate4": {"label": "Blue", "conf": 0.87},
            "gate5": {"label": "Exercise", "conf": 0.93},
        }
        routing = {"TIMER": "gateN", "COLOR": "gate4", "CREATE_REMINDER": "gate5"}
        for intent, gate, value in (
            ("TIMER", "gateN", "10 seconds"),
            ("COLOR", "gate4", "Blue"),
            ("CREATE_REMINDER", "gate5", "Exercise"),
        ):
            result = select_parallel_action(wake_active=True, intent=intent,
                intent_confidence=0.9, threshold=0.5, specialists=specialists, routing=routing)
            self.assertTrue(result["active"])
            self.assertEqual(result["gate"], gate)
            self.assertEqual(result["value"], value)

    def test_monitor_has_a_separate_parallel_all_gates_tab_and_panel(self):
        html = (PROJECT_ROOT / "gate1_web" / "vcm_monitor.html").read_text(encoding="utf-8")
        self.assertIn('data-tab="parallel"', html)
        self.assertIn('id="sec-parallel"', html)
        self.assertIn('id="parallel-cards"', html)
        self.assertIn('id="parallel-gateN"', html)
        self.assertIn('id="parallel-gate4"', html)
        self.assertIn('id="parallel-gate5"', html)

    def test_server_and_shared_tabs_route_parallel_mode(self):
        server = (PROJECT_ROOT / "gate1_server.py").read_text(encoding="utf-8")
        shared = (PROJECT_ROOT / "gate1_web" / "js" / "shared.js").read_text(encoding="utf-8")
        self.assertIn('"parallel"', server)
        self.assertIn('mode === "parallel"', shared)
        self.assertIn('"parallel"', shared)

    def test_non_slot_command_uses_gate2_intent_as_final(self):
        result = select_parallel_action(
            wake_active=True, intent="WEATHER", intent_confidence=0.85, threshold=0.5,
            specialists={"gateN": {"label": "7", "conf": 0.99}},
            routing={"TIMER": "gateN"},
        )
        self.assertTrue(result["active"])
        self.assertIsNone(result["gate"])
        self.assertIsNone(result["value"])
        self.assertEqual(result["final"], "WEATHER")


if __name__ == "__main__":
    unittest.main(verbosity=2)
