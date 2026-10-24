"""Tests: PIPELINE ALL-IN-ONE standalone page (no monitor tabs) — pseudo-code
layout (memory -> G1 -> G2 -> LIGHT FIRST -> Gate 3 AND 4 AND 5 -> action) with
the 280-recording panel, served at /pipeline_all_in_one.html. The monitor's
tab bar stays clean (pipe2 tab removed there)."""
from __future__ import annotations

import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


class TestPipelineAllInOnePage(unittest.TestCase):
    def setUp(self):
        self.html = (PROJECT / "gate1_web" / "pipeline_all_in_one.html").read_text(encoding="utf-8")
        self.js = (PROJECT / "gate1_web" / "js" / "pipeline_v2.js").read_text(encoding="utf-8")
        self.server = (PROJECT / "gate1_server.py").read_text(encoding="utf-8")
        self.monitor = (PROJECT / "gate1_web" / "vcm_monitor.html").read_text(encoding="utf-8")

    def test_standalone_page_has_all_pseudocode_stages(self):
        for element in (
            'id="pipe2-memory"', 'id="pipe2-frames"', 'id="pipe2-g1"', 'id="pipe2-g2"',
            'id="pipe2-action"', 'id="pipe2-cards"', 'id="pipe2-slot"', 'id="pipe2-path"',
            'id="pipe2-accuracy"', 'id="pipe2-specialists"',
        ):
            self.assertIn(element, self.html)

    def test_standalone_page_has_specialist_branch_lines(self):
        for element in ('id="pipe2-spec-gateN"', 'id="pipe2-spec-gate4"', 'id="pipe2-spec-gate5"'):
            self.assertIn(element, self.html)

    def test_standalone_page_has_owner_voice_panel(self):
        for element in (
            'id="pipe2-ownervoice"', 'id="pipe2ownervoiceRun"',
            'id="pipe2-ownervoice-summary"', 'id="pipe2-ownervoice-perintent"',
            'id="pipe2-ownervoice-mismatches"',
        ):
            self.assertIn(element, self.html)

    def test_standalone_page_is_self_contained_and_offline(self):
        self.assertNotIn("js/shared.js", self.html)          # no dependency on the monitor shell
        self.assertIn("pipeline_v2.js", self.html)           # shared pseudo-code renderer
        self.assertIn('mode: "both"', self.html)             # pipeline mode on ws open
        self.assertIn("getUserMedia", self.html)             # own mic capture
        self.assertIn("VCMPIPE2_PHRASES", self.html)         # card source without shared.js
        self.assertIn("action light row before slot", self.html)  # layout order note

    def test_monitor_tab_bar_has_no_pipe2_tab(self):
        self.assertNotIn('data-tab="pipe2"', self.monitor)
        self.assertNotIn('id="sec-pipe2"', self.monitor)
        self.assertNotIn("js/pipeline_v2.js", self.monitor)
        self.assertNotIn("pipe2-frame", self.monitor)
        # the pre-existing tabs stay untouched
        self.assertIn('data-tab="pipe"', self.monitor)
        self.assertIn('data-tab="parallel"', self.monitor)

    def test_server_serves_all_in_one_page(self):
        self.assertIn('"/pipeline_all_in_one.html"', self.server)
        self.assertIn("pipeline_all_in_one_page", self.server)

    def test_action_tests_all_three_specialists_light_first(self):
        self.assertIn('payload["specialists"]', self.server)
        self.assertIn('("gateN", "gate4", "gate5")', self.server)
        self.assertIn("run_in_parallel(tasks)", self.server)
        light_pos = self.server.index('payload["action_gate"]["light_on"]')
        spec_pos = self.server.index('payload["specialists"]')
        self.assertLess(light_pos, spec_pos, "LIGHT FIRST: light flag precedes specialist testing")

    def test_pipeline_v2_js_renders_all_stages_and_phrase_fallback(self):
        for token in (
            "pipe2-memory", "pipe2-frames", "pipe2-g1", "pipe2-g2", "pipe2-cards",
            "pipe2-action", "pipe2-slot", "pipe2-path", "pipe2-accuracy",
            "pipe2-specialists", "MEMORY:", "WAKE:", "INTENT:", "LIGHT ON:",
            "PATH:", "ACCURACY:", "ROUTED VALUE", "window.VCMPIPE2",
            "VCMPIPE2_PHRASES", "parallel gate evaluation",
        ):
            self.assertIn(token, self.js)


    def test_all_in_one_has_gate_variant_choosers(self):
        self.assertIn('id="all-g1model"', self.html)
        self.assertIn('id="all-g2model"', self.html)
        self.assertIn("gate1v8_f32", self.html)
        self.assertIn("gate2v6_keras", self.html)
        self.assertIn('id="all-calibrate"', self.html)
        self.assertIn('id="all-thr-nova"', self.html)
        self.assertIn('id="all-thr-piattos"', self.html)
        self.assertIn('id="all-thr-g2min"', self.html)

    def test_all_in_one_has_voice_volume_and_threshold_charts(self):
        self.assertIn('id="all-wave"', self.html)
        self.assertIn('id="all-volume"', self.html)
        self.assertIn('id="all-thrchart"', self.html)
        self.assertIn("VCMALL", self.html)  # debug state for charts

    def test_all_in_one_has_gate_diagram(self):
        self.assertIn('id="all-diagram"', self.html)
        for box in ("mic", "g1", "g2", "light", "g3", "g4", "g5", "out"):
            self.assertIn('id="all-box-' + box + '"', self.html)

    def test_controller_sends_variant_and_threshold_messages(self):
        self.assertIn('type: "model"', self.html)
        self.assertIn('type: "g2model"', self.html)
        self.assertIn('type: "calibrate"', self.html)
        self.assertIn('type: "thr"', self.html)
        self.assertIn("calibrated", self.html)  # threshold updates feed the line chart

    def test_manual_stop_button_sends_control_message(self):
        self.assertIn('id="all-stop-action"', self.html)
        self.assertIn('type: "manual_stop"', self.html)
        self.assertIn('data.get("type") == "manual_stop"', self.server)

    def test_dashboard_shows_recording_memory_and_scheduler_lag(self):
        self.assertIn('id="all-scheduler-status"', self.html)
        self.assertIn("skipped_ticks", self.html)
        self.assertIn("20-second recording buffer", self.html)

    def test_desktop_layout_groups_controls_and_fits_one_view(self):
        for token in ('id="all-top-controls"', 'id="all-main-grid"',
                      'id="all-left-column"', 'id="all-right-column"',
                      "height:100vh", "min-height:0", "overflow:hidden"):
            self.assertIn(token, self.html)

    def test_layout_keeps_related_controls_in_one_rail(self):
        controls = self.html.index('id="all-top-controls"')
        for element in ('id="all-g1model"', 'id="all-g2model"', 'id="all-calibrate"',
                        'id="all-thr-nova"', 'id="all-thr-piattos"', 'id="all-thr-g2min"'):
            self.assertLess(controls, self.html.index(element))
            self.assertLess(self.html.index(element), self.html.index('id="all-main-grid"'))

    def test_all_in_one_has_threshold_meters_and_per_gate_history(self):
        for element in ('id="all-meter-nova"', 'id="all-meter-piattos"',
                        'id="all-meter-g2"', 'id="all-gate-history"'):
            self.assertIn(element, self.html)
        for gate in ("G1", "G2", "G3", "G4", "G5"):
            self.assertIn('<th>' + gate + '</th>', self.html)

    def test_controller_updates_threshold_meters_and_gate_history(self):
        self.assertIn("updateThresholdMeters", self.html)
        self.assertIn("updateGateHistory", self.html)
        self.assertIn("meter-mark", self.html)

    def test_threshold_chart_spreads_short_history_over_visible_width(self):
        self.assertIn("Math.max(1, n - 1)", self.html)
        self.assertNotIn("c.width / HIST_MAX", self.html)

    def test_action_lights_use_available_panel_height_for_larger_targets(self):
        self.assertIn('id="all-action-panel"', self.html)
        self.assertIn("grid-auto-rows:minmax(42px,1fr)", self.html)
        self.assertIn(".action-panel .parallel-grid{flex:1", self.html)
        self.assertIn("min-height:42px;height:auto", self.html)

    def test_threshold_chart_has_labeled_numeric_scale(self):
        self.assertIn("var ticks = [0, 0.25, 0.5, 0.75, 1]", self.html)
        self.assertIn("plotBottom", self.html)

    def test_gate_history_timestamp_is_compact_and_fully_visible(self):
        self.assertIn('hourCycle: "h23"', self.html)
        self.assertIn("width:62px", self.html)


if __name__ == "__main__":
    unittest.main()
