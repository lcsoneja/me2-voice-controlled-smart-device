"""Gate 2 v2 integration checks for the shipped combined model and preprocessing contract."""
import json
import sys
import unittest
from pathlib import Path
from typing import Any, cast

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gate1_server as server  # noqa: E402

ASSETS = ROOT / "gate1_web" / "gate2v2_assets"
EXPECTED_LABELS = [
    "PLAY_MUSIC", "WEATHER", "TIME", "LIGHT_ON", "LIGHT_OFF", "PAUSE", "STOP",
    "NEXT", "VOLUME_UP", "VOLUME_DOWN", "CALL", "MESSAGE", "LIST_REMINDERS",
    "TIMER", "ALARM", "TEMPERATURE", "BRIGHTNESS", "COLOR", "CREATE_REMINDER",
]


class Gate2V2IntegrationTests(unittest.TestCase):
    def test_default_gate2_loads_combined_148_frame_model_with_existing_label_order(self):
        self.assertTrue((ROOT / "gate1_web" / "gate2v2_float16.tflite").is_file())
        self.assertTrue((ROOT / "gate1_web" / "gate2v2_float32.tflite").is_file())
        gates = server.Gates()
        self.assertEqual(gates.gates["gate2"]["in_shape"], (1, 148, 60, 1))
        self.assertEqual(gates.labels["gate2"], EXPECTED_LABELS)

    def test_gate2v2_preprocessor_matches_shipped_librosa_contract(self):
        preproc_type = getattr(server, "Gate2V2Preproc", None)
        self.assertIsNotNone(preproc_type)
        pre = cast(Any, preproc_type)()
        prep = json.loads((ASSETS / "preprocessing.json").read_text(encoding="utf-8"))
        with np.load(ASSETS / "feature_stats.npz") as stats:
            mean = float(stats["mean"])
            std = float(stats["std"])
        waveform = np.sin(np.arange(11_025, dtype=np.float32) * np.float32(0.017))
        actual = pre.extract(waveform)
        mel = librosa.feature.melspectrogram(
            y=waveform,
            sr=16_000,
            n_fft=int(prep["n_fft"]),
            hop_length=int(prep["hop_length"]),
            win_length=int(prep["win_length"]),
            n_mels=int(prep["n_mels"]),
            center=bool(prep["center"]),
            power=2.0,
        )
        features = np.log1p(mel).T
        frames = int(prep["target_frames"])
        if len(features) < frames:
            features = np.pad(features, ((0, frames - len(features)), (0, 0)), mode="constant")
        elif len(features) > frames:
            start = (len(features) - frames) // 2
            features = features[start : start + frames]
        expected = ((features - mean) / (std + 1e-8)).astype(np.float32)[None, :, :, None]
        self.assertEqual(actual.shape, (1, 148, 60, 1))
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-6)


    def test_gate2v2_keeps_required_synthetic_intents_top_ranked(self):
        import soundfile as sf

        gates = server.Gates()
        samples = (
            ("gate2_PLAY_MUSIC_f02_pitchnorm_fast.wav", "PLAY_MUSIC", 1),
            ("gate4_COLOR_Blue_f10_pitchnorm_normal.wav", "COLOR", 3),
        )
        for filename, expected, top_k in samples:
            with self.subTest(filename=filename):
                waveform, sample_rate = sf.read(ROOT / "synthetic_samples" / filename, dtype="float32")
                if waveform.ndim == 2:
                    waveform = waveform.mean(axis=1)
                if sample_rate != 16_000:
                    waveform = librosa.resample(waveform, orig_sr=sample_rate, target_sr=16_000)
                probs = gates.infer("gate2", waveform)
                ranked = np.argsort(probs)[::-1]
                self.assertIn(expected, [gates.labels["gate2"][int(i)] for i in ranked[:top_k]])
                if expected == "PLAY_MUSIC":
                    self.assertGreaterEqual(float(probs[gates.labels["gate2"].index(expected)]), 0.5)

    def test_monitor_names_the_combined_gate2_model(self):
        html = (ROOT / "gate1_web" / "vcm_monitor.html").read_text(encoding="utf-8")
        self.assertIn("Gate 2 v2 (combined", html)

if __name__ == "__main__":
    unittest.main(verbosity=2)
