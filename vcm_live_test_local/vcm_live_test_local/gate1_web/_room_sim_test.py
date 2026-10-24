import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOM = (HERE / "room_sim.html").read_text(encoding="utf-8")
SERVER = (HERE.parent / "gate1_server.py").read_text(encoding="utf-8")
DASHBOARD = (HERE / "pipeline_all_in_one.html").read_text(encoding="utf-8")
LABELS = json.loads((HERE.parents[2] / "Shipping" / "Gate2V21_ship_20261017" / "labels.json").read_text(encoding="utf-8"))["labels"]


class TestRoomSimulatorResponses(unittest.TestCase):
    def test_room_has_live_subtitle_and_dynamic_time_response(self):
        self.assertIn('id="room-subtitle-text"', ROOM)
        self.assertIn("function responseText", ROOM)
        self.assertIn("TIME", ROOM)
        self.assertIn("toLocaleTimeString", ROOM)

    def test_every_actionable_gate2_label_has_a_subtitle(self):
        for label in LABELS:
            if label != "NEGATIVE":
                self.assertIn("case '" + label + "'", ROOM, label)
        self.assertIn("else if(intent==='COLOR')", ROOM)
        self.assertIn("['COLOR','Color']", ROOM)

    def test_live_action_uses_server_response_and_local_media(self):
        self.assertIn("assistant_response", ROOM)
        self.assertIn("/media/lofiradio/", ROOM)
        self.assertIn("/media/call-sounds/", ROOM)

    def test_dashboard_defers_audio_when_room_simulator_is_connected(self):
        self.assertIn("room_active", DASHBOARD)
        self.assertIn("room_active", SERVER)

    def test_repeated_confirmed_commands_replay_by_unique_event_id(self):
        self.assertIn("String(ag.event_id||0)", ROOM)
        self.assertIn('"event_id": activations.g2_event_id', SERVER)
        self.assertIn('"event_id": self.g2_event_id if overlap else 0', SERVER)


    def test_dashboard_defaults_to_the_shipped_wake_model(self):
        # The selector must mirror server.DEFAULT_G1_MODEL (Gate1V12 since
        # 2026-10-22); the failed V10 and the previous V8 build are never the
        # selected option.
        self.assertIn('value="gate1v12_f16" selected', DASHBOARD)
        self.assertNotIn('value="gate1v8_f32" selected', DASHBOARD)
        self.assertNotIn('value="gate1v10_f16" selected', DASHBOARD)

    def test_lamp_is_grouped_and_percent_positioned_away_from_the_thermometer(self):
        self.assertIn('class="bulblamp"', ROOM)
        self.assertIn('left:52%', ROOM)
        self.assertNotIn('left:615px', ROOM)
        self.assertNotIn('left:640px', ROOM)

    def test_bed_and_nightstand_have_structured_representation(self):
        self.assertIn('class="headboard"', ROOM)
        self.assertIn('class="legs"', ROOM)
        self.assertIn('id="nslamp"', ROOM)
        self.assertIn("document.querySelector('#nslamp')", ROOM)

if __name__ == "__main__":
    unittest.main()
