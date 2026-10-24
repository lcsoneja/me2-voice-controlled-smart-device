#!/usr/bin/env python3
"""One-word assistant reply pack: shipped clips, captions, and wake-ack wiring.

The live dashboard plays /assistant-responses/<clip>; since 2026-10-22 that
route serves the ONEWORD pack (one word per intent, plus a wake-ack pair per
persona). These tests pin the pack selection, the clip format, the CSV captions,
and the dashboard/room-sim wake-ack handling.

Run: py -3.12 -m pytest gate1_web/_oneword_assistant_pack_test.py
"""

from __future__ import annotations

import csv
import json
import sys
import unittest
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
R2B = APP.parent.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import gate1_server as server  # noqa: E402

PACK_NAME = "Gate2_AssistantResponses_ONEWORD_20261022"
LABELS_JSON = R2B / "Shipping" / "Gate2V6_ship_20261013" / "labels.json"
DASHBOARD = HERE / "pipeline_all_in_one.html"
THML = HERE / "pipeline_all_in_one.thml"
ROOM_SIM = HERE / "room_sim.html"


def gate2_labels() -> list[str]:
    return list(json.loads(LABELS_JSON.read_text(encoding="utf-8"))["labels"])


class AssistantPackSelectionTest(unittest.TestCase):
    def test_server_serves_the_oneword_pack(self):
        self.assertEqual(server.ASSISTANT_PACK.name, PACK_NAME)
        self.assertTrue(server.ASSISTANT_AUDIO.is_dir())
        self.assertTrue(server.ASSISTANT_AUDIO.as_posix().endswith("/audio"))

    def test_static_route_uses_the_resolved_pack(self):
        source = (APP / "gate1_server.py").read_text(encoding="utf-8")
        self.assertIn('add_static("/assistant-responses/", path=str(ASSISTANT_AUDIO))', source)
        self.assertNotIn('Gate2_AssistantResponses_20261017" / "audio")', source)


class ShippedClipTest(unittest.TestCase):
    def test_every_gate2_label_ships_two_replies_per_persona(self):
        clips = server.ASSISTANT_CLIPS
        labels = gate2_labels()
        self.assertEqual(len(labels), 19)
        for persona in server.ASSISTANT_PERSONAS:
            for label in labels:
                for variant in (1, 2):
                    self.assertIn((persona, label.lower(), variant), clips,
                                  f"missing {persona}/{label}/{variant}")
        self.assertEqual(len(clips), len(labels) * 2 * 2 + 4)  # + wake pairs

    def test_wake_pairs_exist_for_both_personas(self):
        for persona in server.ASSISTANT_PERSONAS:
            for variant in (1, 2):
                self.assertIn((persona, "wake", variant), server.ASSISTANT_CLIPS)

    def test_clip_formats_are_16k_mono_pcm16(self):
        for entry in sorted(server.ASSISTANT_AUDIO.glob("resp_*.wav")):
            with wave.open(str(entry), "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1, entry.name)
                self.assertEqual(handle.getframerate(), 16000, entry.name)
                self.assertEqual(handle.getsampwidth(), 2, entry.name)

    def test_every_caption_is_exactly_one_word(self):
        rows = list(csv.DictReader((server.ASSISTANT_PACK / "responses_manifest.csv")
                                   .open(newline="", encoding="utf-8")))
        self.assertEqual(len(rows), 80)
        for row in rows:
            self.assertEqual(len(row["text"].split()), 1, row["file_name"])
        wake = {row["persona"]: row["text"] for row in rows
                if row["intent"].strip().lower() == "wake" and row["variant_index"] == "1"}
        self.assertEqual(wake, {"Nova": "Yes?", "Piattos": "Hi"})


class AssistantClipLookupTest(unittest.TestCase):
    def test_wake_lookup_returns_clip_and_caption(self):
        ack = server.assistant_clip("Nova", "wake")
        self.assertIsNotNone(ack)
        assert ack is not None
        self.assertEqual(ack["url"], "/assistant-responses/resp_nova_wake_1.wav")
        self.assertEqual(ack["text"], "Yes?")
        self.assertEqual(ack["persona"], "nova")

        piattos = server.assistant_clip("Piattos", "wake")
        assert piattos is not None
        self.assertEqual(piattos["url"], "/assistant-responses/resp_piattos_wake_1.wav")
        self.assertEqual(piattos["text"], "Hi")

    def test_intent_lookup_is_case_insensitive_and_carries_text(self):
        clip = server.assistant_clip("nova", "PLAY_MUSIC")
        assert clip is not None
        self.assertEqual(clip["url"], "/assistant-responses/resp_nova_play_music_1.wav")
        self.assertEqual(clip["text"], "Playing")

    def test_unknown_persona_falls_back_to_a_shipped_voice(self):
        clip = server.assistant_clip(None, "LIGHT_ON")
        assert clip is not None
        self.assertIn(clip["persona"], server.ASSISTANT_PERSONAS)

    def test_unknown_intent_has_no_clip(self):
        self.assertIsNone(server.assistant_clip("nova", "not_an_intent"))


class WakeAckWiringTest(unittest.TestCase):
    def test_server_emits_one_wake_ack_per_latch(self):
        source = (APP / "gate1_server.py").read_text(encoding="utf-8")
        self.assertIn('ack = assistant_clip(wake, "wake")', source)
        self.assertIn('guard["wake_ack_seq"] = int(guard.get("wake_ack_seq", 0)) + 1', source)
        self.assertIn('payload["wake_response"] = wake_ack', source)
        self.assertIn("wake_ack = None", source)

    def test_action_response_payload_carries_the_spoken_text(self):
        source = (APP / "gate1_server.py").read_text(encoding="utf-8")
        self.assertIn('payload["assistant_response"] = {"intent": intent, "room_active": bool(_ROOM_QUEUES), **clip}', source)

    def test_dashboard_plays_the_wake_ack_and_captions_the_reply(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("msg.wake_response && msg.wake_response.url", html)
        self.assertIn('playVoice("wake", wakePersona, null, msg.wake_response.url, "")', html)
        self.assertIn("var lastWakeKey = '';", html)
        self.assertIn("(response && response.text) ? response.text : responseText(intent, v)", html)

    def test_thml_mirror_is_byte_identical(self):
        self.assertEqual(DASHBOARD.read_bytes(), THML.read_bytes())

    def test_room_sim_plays_the_wake_ack(self):
        html = ROOM_SIM.read_text(encoding="utf-8")
        self.assertIn("m.wake_response&&m.wake_response.url", html)
        self.assertIn("playVoice('wake',wp,null,m.wake_response.url,'')", html)


if __name__ == "__main__":
    unittest.main()
