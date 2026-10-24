"""Read-only Gate3–Gate5 candidate access and clip-level Keras inference."""
from __future__ import annotations

import importlib.util
import io
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import soundfile as sf

APP_DIR = Path(__file__).resolve().parent
DEFAULT_BUNDLE_DIR = APP_DIR.parent / "Shipping" / "Gate3to5_SlotSpecialists_Candidates_20261009"
ALLOWED_GATES = {
    "gate3a_timer": "Gate 3a · Timer",
    "gate3b_alarm": "Gate 3b · Alarm",
    "gate3c_temperature": "Gate 3c · Temperature",
    "gate3d_brightness": "Gate 3d · Brightness",
    "gate5_reminder_content": "Gate 5 · Reminder content",
}
ALLOWED_RATIOS = ("neg1x", "neg2x")
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


class InputError(ValueError):
    """The request did not contain a valid selection or WAV clip."""


class ClipTooLongError(InputError):
    """The uploaded clip exceeds the model's fixed clip window."""


def validate_selection(gate: object, ratio: object) -> tuple[str, str]:
    if not isinstance(gate, str) or gate not in ALLOWED_GATES:
        raise InputError("Select one supported gate: Gate3a, Gate3b, Gate3c, Gate3d, or Gate5.")
    if not isinstance(ratio, str) or ratio not in ALLOWED_RATIOS:
        raise InputError("Select a candidate ratio: neg1x or neg2x. Neither is promoted by this package.")
    return gate, ratio


def _load_bundle_infer(bundle_dir: Path) -> ModuleType:
    infer_path = bundle_dir / "infer.py"
    if not infer_path.is_file():
        raise FileNotFoundError(f"Candidate bundle infer.py not found: {infer_path}")
    spec = importlib.util.spec_from_file_location("gate3to5_candidate_infer", infer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load candidate inference contract: {infer_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Gate3to5InferenceService:
    """Lazy-load only the explicitly selected candidate; keep its source bundle untouched."""

    def __init__(self, bundle_dir: Path | str = DEFAULT_BUNDLE_DIR):
        self.bundle_dir = Path(bundle_dir).resolve()
        self.infer: ModuleType = _load_bundle_infer(self.bundle_dir)
        self.labels: dict[str, list[str]] = {
            gate: list(self.infer.LABELS[gate]) for gate in ALLOWED_GATES
        }
        self.preprocessing = dict(self.infer.PREPROCESSING)
        self.max_clip_seconds = (
            int(self.preprocessing["target_frames"])
            * int(self.preprocessing["hop_length"])
            / int(self.preprocessing["sample_rate"])
        )
        self._model_key: tuple[str, str] | None = None
        self._model: Any = None
        self._lock = threading.RLock()

    def validate_wav(self, filename: str, payload: bytes) -> float:
        if not isinstance(filename, str) or Path(filename).suffix.lower() != ".wav":
            raise InputError("Choose a WAV file.")
        if not payload:
            raise InputError("The selected WAV file is empty.")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise InputError("WAV is too large; maximum upload size is 12 MiB.")
        try:
            info = sf.info(io.BytesIO(payload))
        except (OSError, RuntimeError, ValueError) as exc:
            raise InputError("Could not read this WAV. Choose a valid, uncorrupted WAV file.") from exc
        if info.frames <= 0 or info.samplerate <= 0 or info.channels <= 0:
            raise InputError("WAV must contain nonempty mono or stereo audio.")
        duration = info.frames / info.samplerate
        if duration > self.max_clip_seconds + 1e-6:
            raise ClipTooLongError(
                f"Clip is {duration:.2f} seconds; the model window is {self.max_clip_seconds:.2f} seconds. "
                "This app classifies one clip and does not stream or silently crop long recordings."
            )
        return duration

    def preprocess_wav(self, filename: str, payload: bytes) -> tuple[np.ndarray, float]:
        duration = self.validate_wav(filename, payload)
        try:
            features = self.infer.make_features(io.BytesIO(payload))
        except (OSError, RuntimeError, ValueError) as exc:
            raise InputError("Could not decode or preprocess this WAV file.") from exc
        expected = (
            1,
            int(self.preprocessing["target_frames"]),
            int(self.preprocessing["n_mels"]),
            1,
        )
        if tuple(features.shape) != expected:
            raise RuntimeError(f"Preprocessor returned {features.shape}; expected {expected}.")
        return features, duration

    def load_model(self, gate: str, ratio: str):
        gate, ratio = validate_selection(gate, ratio)
        key = (gate, ratio)
        with self._lock:
            if self._model_key == key and self._model is not None:
                return self._model
            path = self.bundle_dir / "models" / gate / ratio / "best_model.keras"
            if not path.is_file():
                raise FileNotFoundError(f"Candidate model not found: {path}")
            if self._model is not None:
                self.infer.tf.keras.backend.clear_session()
                self._model = None
                self._model_key = None
            model = self.infer.tf.keras.models.load_model(str(path), compile=False)
            expected_input = (
                int(self.preprocessing["target_frames"]),
                int(self.preprocessing["n_mels"]),
                1,
            )
            if tuple(model.input_shape[1:]) != expected_input:
                raise RuntimeError(f"Model input shape {model.input_shape} does not match {expected_input}.")
            if int(model.output_shape[-1]) != len(self.labels[gate]):
                raise RuntimeError("Model output count differs from labels.json.")
            self._model_key = key
            self._model = model
            return model

    def infer_wav(self, gate: str, ratio: str, filename: str, payload: bytes) -> dict[str, Any]:
        gate, ratio = validate_selection(gate, ratio)
        features, duration = self.preprocess_wav(filename, payload)
        with self._lock:
            model = self.load_model(gate, ratio)
            raw_scores = np.asarray(model.predict(features, verbose=0))
        labels = self.labels[gate]
        if raw_scores.shape != (1, len(labels)):
            raise RuntimeError(f"Model output shape {raw_scores.shape} does not match {len(labels)} labels.")
        scores = raw_scores[0].astype(np.float64)
        if not np.isfinite(scores).all():
            raise RuntimeError("Model returned non-finite scores.")
        top_index = int(np.argmax(scores))
        return {
            "gate": gate,
            "ratio": ratio,
            "top_label": labels[top_index],
            "top_score": float(scores[top_index]),
            "class_scores": [
                {"label": label, "score": float(score)} for label, score in zip(labels, scores, strict=True)
            ],
            "score_interpretation": "uncalibrated model scores",
            "clip_duration_seconds": float(duration),
            "window_seconds": float(self.max_clip_seconds),
        }
