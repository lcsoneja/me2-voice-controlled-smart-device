"""Delay indicator: scheduler eval_ms/late telemetry and dashboard DELAYED rendering."""
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = (HERE.parent / "gate1_server.py").read_text(encoding="utf-8")
HTML = (HERE / "pipeline_all_in_one.html").read_text(encoding="utf-8")
THML = (HERE / "pipeline_all_in_one.thml").read_text(encoding="utf-8")


class TestDelayIndicator(unittest.TestCase):
    def test_server_reports_eval_ms_and_late_per_tick(self):
        self.assertIn('"eval_ms": round(elapsed_s * 1000.0)', SERVER)
        self.assertIn('"late": tick_late', SERVER)
        self.assertIn("tick_late = elapsed_s > tick_interval", SERVER)

    def test_dashboard_renders_delayed_badge(self):
        self.assertIn("sched.eval_ms", HTML)
        self.assertIn("sched.late", HTML)
        self.assertIn("DELAYED", HTML)
        self.assertIn('classList.toggle("delayed", late || drift > 2)', HTML)
        self.assertIn("#all-scheduler-status.delayed", HTML)

    def test_dashboard_shows_drift_and_skipped_windows(self):
        self.assertIn("sched.drift_s", HTML)
        self.assertIn("behind realtime", HTML)
        self.assertIn("skipped audio windows", HTML)
        self.assertIn('"skipped_log": list(skip_log)', SERVER)
        self.assertIn('"drift_s": round(drift_s, 2)', SERVER)
        self.assertIn("all-skipped-log", HTML)

    def test_thml_copy_stays_in_sync(self):
        self.assertIn("sched.eval_ms", THML)
        self.assertIn("DELAYED", THML)

    def test_panel_title_reflects_one_second_cadence(self):
        self.assertIn("1 s parallel evaluation", HTML)
        self.assertNotIn("2 s parallel evaluation", HTML)


if __name__ == "__main__":
    unittest.main()
