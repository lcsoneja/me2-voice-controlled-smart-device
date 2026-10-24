"""Tests for new dashboard features:
- Evaluation interval options (1s, 2s, 3s, 6s)
- Skipped ticks toggle option
- Pipeline reset button
- Gate 1 & Gate 2 trigger Gantt chart
- Embedded VCM Room Simulation pane
"""
from pathlib import Path
import unittest

import gate1_server as server

HERE = Path(__file__).resolve().parent
HTML = (HERE / "pipeline_all_in_one.html").read_text(encoding="utf-8")
SERVER_PY = (HERE.parent / "gate1_server.py").read_text(encoding="utf-8")


class TestNewDashboardFeatures(unittest.TestCase):
    def test_inference_interval_supports_options(self):
        for sec in (1, 2, 3, 6):
            self.assertEqual(server._inference_interval_s("both", {"interval_s": sec}), float(sec))
            self.assertEqual(server._inference_interval_s("gate2", {"interval_s": sec}), float(sec))
        # Default fallback
        self.assertEqual(server._inference_interval_s("both", {}), 1.0)
        self.assertEqual(server._inference_interval_s("gate1", {}), 1.0)

    def test_ui_has_interval_options_select(self):
        self.assertIn('id="all-interval"', HTML)
        self.assertIn('value="1"', HTML)
        self.assertIn('value="2"', HTML)
        self.assertIn('value="3"', HTML)
        self.assertIn('value="6"', HTML)
        self.assertIn('type: "interval"', HTML)

    def test_ui_has_skip_ticks_toggle(self):
        self.assertIn('id="all-skip-ticks"', HTML)
        self.assertIn('type: "skip_ticks"', HTML)
        self.assertIn('skip_ticks_enabled', SERVER_PY)

    def test_ui_has_reset_pipeline_button(self):
        self.assertIn('id="all-reset-pipeline"', HTML)
        self.assertIn('type: "reset"', HTML)
        self.assertIn('elif data.get("type") == "reset":', SERVER_PY)

    def test_ui_has_gantt_chart(self):
        self.assertIn('id="all-gantt-chart"', HTML)
        self.assertIn('function recordGanttEvent', HTML)
        self.assertIn('function drawGanttChart', HTML)
        self.assertIn('G1 Wake', HTML)
        self.assertIn('G2 Intent', HTML)

    def test_ui_has_embedded_room_simulation(self):
        self.assertIn('class="action-room-row"', HTML)
        self.assertIn('id="all-action-panel"', HTML)
        self.assertIn('id="all-room-panel"', HTML)
        self.assertIn('id="room"', HTML)
        self.assertIn('id="bulb"', HTML)
        self.assertIn('id="bed"', HTML)
        self.assertIn('id="nslamp"', HTML)
        self.assertIn('id="musicbox"', HTML)
        self.assertIn('id="tempnum"', HTML)
        self.assertIn('id="room-subtitle"', HTML)
        self.assertIn('function applyRoomAction', HTML)
        self.assertIn('function updateRoomSim', HTML)


if __name__ == "__main__":
    unittest.main()
