"""Unit tests for the isolated Gate3–Gate5 clip-level app."""
import io
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from ..app import create_app
from ..inference_service import ClipTooLongError, Gate3to5InferenceService, InputError, validate_selection

APP_DIR = Path(__file__).resolve().parents[1]
BUNDLE_DIR = APP_DIR.parent / "Shipping" / "Gate3to5_SlotSpecialists_Candidates_20261009"


def synthetic_wav(seconds=1.0):
    rate = 16000
    time = np.arange(int(rate * seconds), dtype=np.float32) / rate
    wave = (0.05 * np.sin(2.0 * np.pi * 440.0 * time)).astype(np.float32)
    stream = io.BytesIO()
    sf.write(stream, wave, rate, format="WAV", subtype="PCM_16")
    return stream.getvalue()


class Gate3To5AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = Gate3to5InferenceService(BUNDLE_DIR)

    def test_invalid_gate_and_ratio_rejected(self):
        with self.assertRaises(InputError):
            validate_selection("gate4_color", "neg1x")
        with self.assertRaises(InputError):
            validate_selection("gate3a_timer", "")
        with self.assertRaises(InputError):
            validate_selection("gate3a_timer", "promoted")

    def test_missing_wav_rejected(self):
        with self.assertRaises(InputError):
            self.service.preprocess_wav("sample.wav", b"")
        with self.assertRaises(InputError):
            self.service.preprocess_wav("", synthetic_wav())

    def test_corrupt_wav_rejected(self):
        with self.assertRaises(InputError):
            self.service.preprocess_wav("corrupt.wav", b"not a wave file")

    def test_clip_longer_than_model_window_rejected(self):
        with self.assertRaises(ClipTooLongError):
            self.service.preprocess_wav("long.wav", synthetic_wav(6.5))

    def test_candidate_model_loads_and_returns_four_label_scores(self):
        gate = "gate3a_timer"
        ratio = "neg1x"
        model = self.service.load_model(gate, ratio)
        self.assertEqual(tuple(model.input_shape[1:]), (148, 60, 1))
        self.assertEqual(int(model.output_shape[-1]), 4)
        result = self.service.infer_wav(gate, ratio, "synthetic_timer.wav", synthetic_wav())
        self.assertEqual([item["label"] for item in result["class_scores"]], self.service.labels[gate])
        self.assertEqual(len(result["class_scores"]), 4)
        self.assertIn(result["top_label"], self.service.labels[gate])
        self.assertEqual(result["score_interpretation"], "uncalibrated model scores")
        self.assertTrue(all(np.isfinite(row["score"]) for row in result["class_scores"]))


class Gate3To5ApiTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = Gate3to5InferenceService(BUNDLE_DIR)

    async def asyncSetUp(self):
        self.client = TestClient(TestServer(create_app(inference_service=self.service)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    @staticmethod
    def form_data(gate="gate3a_timer", ratio="neg1x", audio: bytes | None = None, filename="synthetic.wav", include_audio=True):
        form = FormData()
        if gate is not None:
            form.add_field("gate", gate)
        if ratio is not None:
            form.add_field("ratio", ratio)
        if include_audio:
            payload = synthetic_wav() if audio is None else audio
            form.add_field("audio", payload, filename=filename, content_type="audio/wav")
        return form

    async def test_config_lists_only_scoped_gates_and_both_candidates(self):
        response = await self.client.get("/api/config")
        self.assertEqual(response.status, 200)
        config = await response.json()
        gate_ids = [item["id"] for item in config["gates"]]
        self.assertEqual(gate_ids, [
            "gate3a_timer", "gate3b_alarm", "gate3c_temperature",
            "gate3d_brightness", "gate5_reminder_content",
        ])
        self.assertNotIn("gate4_color", gate_ids)
        self.assertEqual(config["ratios"], ["neg1x", "neg2x"])

    async def test_api_rejects_invalid_gate_or_ratio(self):
        bad_gate = await self.client.post("/api/infer", data=self.form_data(gate="gate4_color"))
        self.assertEqual(bad_gate.status, 400)
        bad_ratio = await self.client.post("/api/infer", data=self.form_data(ratio="promoted"))
        self.assertEqual(bad_ratio.status, 400)

    async def test_api_rejects_missing_and_corrupt_wav(self):
        missing = await self.client.post("/api/infer", data=self.form_data(include_audio=False))
        self.assertEqual(missing.status, 400)
        corrupt = await self.client.post("/api/infer", data=self.form_data(audio=b"not a wav file"))
        self.assertEqual(corrupt.status, 400)

    async def test_api_returns_class_scores_for_synthetic_clip(self):
        response = await self.client.post("/api/infer", data=self.form_data())
        self.assertEqual(response.status, 200)
        result = await response.json()
        self.assertEqual(result["gate"], "gate3a_timer")
        self.assertEqual(result["ratio"], "neg1x")
        self.assertEqual(len(result["class_scores"]), 4)
        self.assertEqual(result["score_interpretation"], "uncalibrated model scores")

    def test_existing_monitor_embeds_candidate_app_and_has_return_navigation(self):
        project = APP_DIR.parent
        live = project / "vcm_live_test_local" / "vcm_live_test_local"
        monitor = (live / "gate1_web" / "vcm_monitor.html").read_text(encoding="utf-8")
        shared = (live / "gate1_web" / "js" / "shared.js").read_text(encoding="utf-8")
        app_page = (APP_DIR / "index.html").read_text(encoding="utf-8")
        launcher = project / "run_all_local.bat"
        self.assertIn('data-tab="gate3to5"', monitor)
        self.assertIn('id="sec-gate3to5"', monitor)
        self.assertIn('src="/gate3to5/"', monitor)
        self.assertIn("serverModeForTab", shared)
        self.assertIn('target="_top"', app_page)
        self.assertTrue(launcher.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
