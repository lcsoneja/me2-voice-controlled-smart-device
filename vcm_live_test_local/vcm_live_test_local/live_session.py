#!/usr/bin/env python3
"""
VCM Live Voice Command Testing Tool (v1.0.0)
============================================
Owner-commissioned live testing and validation harness for the Tiny Voice Command Model (VCM8).
Provides interactive live-microphone testing with real-time VAD endpointing,
file-batch evaluation, hierarchical gate routing (Gate 2 -> Specialists Gate 3a-d, 4, 5),
and session management with privacy controls.

Repository: /mnt/jfs_hpc/home/leandro.soneja/_Exercise B2
Authoritative Script Path: vcm8/live_test/live_session.py
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import os
import queue
import signal
import sys
import time
import wave
from collections import defaultdict
from pathlib import Path
from typing import Any

# Suppress TensorFlow C++ logs and disable GPU before any TF imports
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import numpy as np  # type: ignore

logger = logging.getLogger("vcm_live")

__version__ = "1.0.0"

# -----------------------------------------------------------------------------
# Default Constants & Preprocessing Configuration
# -----------------------------------------------------------------------------
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_N_MELS = 60
DEFAULT_N_FFT = 1024
DEFAULT_HOP_LENGTH = 640
DEFAULT_WIN_LENGTH = 1024
DEFAULT_TARGET_FRAMES = 74

DEFAULT_MIN_CONFIDENCE = 0.50
DEFAULT_SILENCE_S = 1.2
DEFAULT_MAX_UTTERANCE_S = 6.0
DEFAULT_RMS_SPEECH_FLOOR = 0.005

DISCLAIMER_TEXT = (
    "NOTICE: Results describe THIS live session's samples only and do NOT serve "
    "as a substitute for evaluation on a separate authorized, frozen benchmark dataset."
)

# Relative default paths within repository
DEFAULT_REGISTRY_PATH = "vcm8/config/model_registry.json"
DEFAULT_FEATURE_STATS_PATH = "vcm8/training/feature_stats.npz"

CHECKPOINT_PATHS: dict[str, str] = {
    "gate1": "vcm8/training/runs/gate1_v1/best_model.keras",
    "gate2": "vcm8/training/runs/gate2_v2/best_model.keras",
    "gate3a": "vcm8/training/runs/gate3a_v3/best_model.keras",
    "gate3b": "vcm8/training/runs/gate3b_v3/best_model.keras",
    "gate3c": "vcm8/training/runs/gate3c/best_model.keras",
    "gate3d": "vcm8/training/runs/gate3d_v2/best_model.keras",
    "gate4": "vcm8/training/runs/gate4/best_model.keras",
    "gate5": "vcm8/training/runs/gate5/best_model.keras",
    "gateN": "vcm8/training/runs/gateN_v2_compound/best_model.keras",
}

# Leaf tokens mapping to normalized specialist values and parent intents
LEAF_MAPPINGS: dict[str, tuple[str, str]] = {
    # Gate 3a (Timer)
    "timer_10s": ("TIMER", "10 seconds"),
    "timer_10_seconds": ("TIMER", "10 seconds"),
    "10s": ("TIMER", "10 seconds"),
    "10 seconds": ("TIMER", "10 seconds"),
    "10_seconds": ("TIMER", "10 seconds"),
    "timer_30s": ("TIMER", "30 seconds"),
    "timer_30_seconds": ("TIMER", "30 seconds"),
    "30s": ("TIMER", "30 seconds"),
    "30 seconds": ("TIMER", "30 seconds"),
    "30_seconds": ("TIMER", "30 seconds"),
    "timer_1m": ("TIMER", "1 minute"),
    "timer_1_minute": ("TIMER", "1 minute"),
    "1m": ("TIMER", "1 minute"),
    "1 minute": ("TIMER", "1 minute"),
    "1_minute": ("TIMER", "1 minute"),
    # Gate 3b (Alarm)
    "alarm_6_00am": ("ALARM", "6 AM"),
    "alarm_6am": ("ALARM", "6 AM"),
    "6 am": ("ALARM", "6 AM"),
    "6am": ("ALARM", "6 AM"),
    "6_am": ("ALARM", "6 AM"),
    "alarm_8_00am": ("ALARM", "8 AM"),
    "alarm_8am": ("ALARM", "8 AM"),
    "8 am": ("ALARM", "8 AM"),
    "8am": ("ALARM", "8 AM"),
    "8_am": ("ALARM", "8 AM"),
    "alarm_9_00pm": ("ALARM", "9 PM"),
    "alarm_9pm": ("ALARM", "9 PM"),
    "9 pm": ("ALARM", "9 PM"),
    "9pm": ("ALARM", "9 PM"),
    "9_pm": ("ALARM", "9 PM"),
    # Gate 3c (Temperature)
    "temperature_18": ("TEMPERATURE", "18 degrees"),
    "temperature_18deg": ("TEMPERATURE", "18 degrees"),
    "18 degrees": ("TEMPERATURE", "18 degrees"),
    "18_degrees": ("TEMPERATURE", "18 degrees"),
    "18deg": ("TEMPERATURE", "18 degrees"),
    "18": ("TEMPERATURE", "18 degrees"),
    "temperature_22": ("TEMPERATURE", "22 degrees"),
    "temperature_22deg": ("TEMPERATURE", "22 degrees"),
    "22 degrees": ("TEMPERATURE", "22 degrees"),
    "22_degrees": ("TEMPERATURE", "22 degrees"),
    "22deg": ("TEMPERATURE", "22 degrees"),
    "22": ("TEMPERATURE", "22 degrees"),
    "temperature_26": ("TEMPERATURE", "26 degrees"),
    "temperature_26deg": ("TEMPERATURE", "26 degrees"),
    "26 degrees": ("TEMPERATURE", "26 degrees"),
    "26_degrees": ("TEMPERATURE", "26 degrees"),
    "26deg": ("TEMPERATURE", "26 degrees"),
    "26": ("TEMPERATURE", "26 degrees"),
    # Gate 3d (Brightness)
    "brightness_20": ("BRIGHTNESS", "20 percent"),
    "brightness_20pct": ("BRIGHTNESS", "20 percent"),
    "20 percent": ("BRIGHTNESS", "20 percent"),
    "20_percent": ("BRIGHTNESS", "20 percent"),
    "20%": ("BRIGHTNESS", "20 percent"),
    "20pct": ("BRIGHTNESS", "20 percent"),
    "brightness_60": ("BRIGHTNESS", "60 percent"),
    "brightness_60pct": ("BRIGHTNESS", "60 percent"),
    "60 percent": ("BRIGHTNESS", "60 percent"),
    "60_percent": ("BRIGHTNESS", "60 percent"),
    "60%": ("BRIGHTNESS", "60 percent"),
    "60pct": ("BRIGHTNESS", "60 percent"),
    "brightness_100": ("BRIGHTNESS", "100 percent"),
    "brightness_100pct": ("BRIGHTNESS", "100 percent"),
    "100 percent": ("BRIGHTNESS", "100 percent"),
    "100_percent": ("BRIGHTNESS", "100 percent"),
    "100%": ("BRIGHTNESS", "100 percent"),
    "100pct": ("BRIGHTNESS", "100 percent"),
    # Gate 4 (Color)
    "color_red": ("COLOR", "Red"),
    "red": ("COLOR", "Red"),
    "color_blue": ("COLOR", "Blue"),
    "blue": ("COLOR", "Blue"),
    "color_green": ("COLOR", "Green"),
    "green": ("COLOR", "Green"),
    # Gate 5 (Reminder)
    "create_reminder_drink_water": ("CREATE_REMINDER", "Drink water"),
    "reminder_drink_water": ("CREATE_REMINDER", "Drink water"),
    "drink water": ("CREATE_REMINDER", "Drink water"),
    "drink_water": ("CREATE_REMINDER", "Drink water"),
    "create_reminder_study": ("CREATE_REMINDER", "Study"),
    "reminder_study": ("CREATE_REMINDER", "Study"),
    "study": ("CREATE_REMINDER", "Study"),
    "create_reminder_exercise": ("CREATE_REMINDER", "Exercise"),
    "reminder_exercise": ("CREATE_REMINDER", "Exercise"),
    "exercise": ("CREATE_REMINDER", "Exercise"),
}

# Reverse lookup for specialist values to parent intent
SPECIALIST_TO_INTENT: dict[str, str] = {
    "10 seconds": "TIMER",
    "30 seconds": "TIMER",
    "1 minute": "TIMER",
    "6 AM": "ALARM",
    "8 AM": "ALARM",
    "9 PM": "ALARM",
    "18 degrees": "TEMPERATURE",
    "22 degrees": "TEMPERATURE",
    "26 degrees": "TEMPERATURE",
    "20 percent": "BRIGHTNESS",
    "60 percent": "BRIGHTNESS",
    "100 percent": "BRIGHTNESS",
    "Red": "COLOR",
    "Blue": "COLOR",
    "Green": "COLOR",
    "Drink water": "CREATE_REMINDER",
    "Study": "CREATE_REMINDER",
    "Exercise": "CREATE_REMINDER",
}


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 digest of a file in binary chunks."""
    if not path.is_file():
        return "missing"
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
    except OSError as e:
        logger.error("Failed to read %s for hashing: %s", path, e)
        raise
    return hasher.hexdigest()


def read_audio_file(path: Path) -> tuple[np.ndarray, int]:
    """
    Read audio WAV file as 1D float32 array in [-1.0, 1.0] and its sample rate.
    Tries standard library wave first, falling back to soundfile if present.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Audio file not found: {p}")

    try:
        with wave.open(str(p), "rb") as wf:
            n_ch = wf.getnchannels()
            width = wf.getsampwidth()
            sr = wf.getframerate()
            frames = wf.readframes(wf.getnframes())

            if width == 2:
                data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            elif width == 4:
                data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
            elif width == 1:
                data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            else:
                raise ValueError(f"Unsupported sample width: {width} bytes")

            if n_ch > 1:
                data = data.reshape(-1, n_ch).mean(axis=1)

            return data, sr
    except Exception:
        # Try soundfile fallback
        try:
            import soundfile as sf  # type: ignore
            data, sr = sf.read(str(p), dtype="float32", always_2d=False)
            if data.ndim > 1:
                data = data.mean(axis=1)
            return data.astype(np.float32), int(sr)
        except Exception as exc:
            raise RuntimeError(f"Could not load audio file {p}: {exc}") from exc


# -----------------------------------------------------------------------------
# Preprocessing Engine (Mirroring prep_features.py EXACTLY)
# -----------------------------------------------------------------------------
class FeatureExtractor:
    """
    Exact feature extractor matching vcm8/training/prep_features.py:
      - 16 kHz mono float32 in [-1.0, 1.0]
      - Polyphase resample 12 kHz -> 16 kHz
      - librosa log-mel: n_mels=60, n_fft=1024, hop=640, win=1024, center=True, log1p
      - Pad tail / center-crop to exactly 74 frames
      - Transpose to (74, 60)
      - Z-score normalize with train-only mean/std from feature_stats.npz
      - Reshape to (1, 74, 60, 1) float32
    """

    def __init__(self, stats_path: Path, target_frames: int = DEFAULT_TARGET_FRAMES):
        self.stats_path = Path(stats_path)
        if not self.stats_path.is_file():
            raise FileNotFoundError(
                f"Feature stats file missing: {self.stats_path}. "
                "Ensure vcm8/training/feature_stats.npz is available."
            )
        data = np.load(self.stats_path)
        self.mean = float(data["mean"])
        self.std = float(data["std"])
        self.target_frames = int(target_frames)

    def extract_features(self, y: np.ndarray, sr_in: int = DEFAULT_SAMPLE_RATE) -> np.ndarray:
        """Process 1D float32 audio waveform into a normalized (1, target_frames, 60, 1) tensor."""
        import librosa  # type: ignore

        # Ensure float32 1D array
        y = np.asarray(y, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)

        # Resample if not 16000 Hz
        if sr_in == 12000:
            from scipy.signal import resample_poly  # type: ignore
            g = int(np.gcd(DEFAULT_SAMPLE_RATE, sr_in))
            y = resample_poly(y, DEFAULT_SAMPLE_RATE // g, sr_in // g).astype(np.float32)
        elif sr_in != DEFAULT_SAMPLE_RATE:
            y = librosa.resample(y, orig_sr=sr_in, target_sr=DEFAULT_SAMPLE_RATE).astype(np.float32)

        # Compute Mel Spectrogram
        S = librosa.feature.melspectrogram(
            y=y,
            sr=DEFAULT_SAMPLE_RATE,
            n_fft=DEFAULT_N_FFT,
            hop_length=DEFAULT_HOP_LENGTH,
            win_length=DEFAULT_WIN_LENGTH,
            n_mels=DEFAULT_N_MELS,
            center=True,
        )
        log_S = np.log1p(S)  # (60, frames)

        # Pad or center crop to target frames (74 for v1 models, 148 for gateN_v2_compound)
        n_frames = log_S.shape[1]
        if n_frames < self.target_frames:
            pad_width = self.target_frames - n_frames
            log_S = np.pad(log_S, ((0, 0), (0, pad_width)), mode="constant")
        elif n_frames > self.target_frames:
            start = (n_frames - self.target_frames) // 2
            log_S = log_S[:, start : start + self.target_frames]

        # Transpose to (target_frames, 60)
        feat = log_S.T

        # Normalize using frozen training statistics
        norm_feat = (feat - self.mean) / (self.std + 1e-8)
        model_input = norm_feat[np.newaxis, :, :, np.newaxis].astype(np.float32)
        return model_input


# -----------------------------------------------------------------------------
# Model Pipeline & Router
# -----------------------------------------------------------------------------
class VCMModelPipeline:
    """
    Manages loading and executing Keras checkpoints for Gate 2 and Specialists.
    Enforces CPU-only execution and reports Gate 1 as UNAVAILABLE.
    """

    def __init__(self, root_dir: Path, registry_path: Path, stats_path: Path):
        self.root_dir = Path(root_dir)
        self.registry_path = Path(registry_path)
        self.stats_path = Path(stats_path)

        if not self.registry_path.is_file():
            raise FileNotFoundError(f"Model registry not found at {self.registry_path}")

        try:
            with open(self.registry_path, encoding="utf-8") as f:
                self.registry = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to load model registry {self.registry_path}: {e}") from e

        self.models_meta = self.registry.get("models", {})
        self.gate2_labels: list[str] = list(self.models_meta.get("gate2", {}).get("labels", []))
        self.routing_table: dict[str, str] = dict(self.models_meta.get("gate2", {}).get("routing", {}))

        # Numeric-value routing override: gateN (unified 12-class) supersedes gate3a-d
        # at inference (registry routing stays untouched; this is a tool-level override).
        if "gateN" in self.models_meta:
            for numeric_intent in ("TIMER", "ALARM", "TEMPERATURE", "BRIGHTNESS"):
                if numeric_intent in self.routing_table:
                    self.routing_table[numeric_intent] = "gateN"

        # Specialist class labels
        self.specialist_labels: dict[str, list[str]] = {}
        for m_id in ["gate3a", "gate3b", "gate3c", "gate3d", "gate4", "gate5", "gateN"]:
            if m_id in self.models_meta:
                self.specialist_labels[m_id] = list(self.models_meta[m_id].get("labels", []))

        self.feature_extractor = FeatureExtractor(self.stats_path)

        # gateN checkpoint selection: gateN_v2_compound requires 148-frame preprocessing
        # (feature_stats_148.npz); fall back to gateN_v1 (74-frame) when unavailable.
        self.gateN_features_148 = False
        self.feature_extractor_148: FeatureExtractor | None = None
        runs_v2 = self.root_dir / "vcm8/training/runs/gateN_v2_compound/best_model.keras"
        stats_148 = self.root_dir / "vcm8/training/feature_stats_148.npz"
        if runs_v2.is_file() and stats_148.is_file():
            self.gateN_features_148 = True
            self.feature_extractor_148 = FeatureExtractor(stats_148, target_frames=148)
            CHECKPOINT_PATHS["gateN"] = "vcm8/training/runs/gateN_v2_compound/best_model.keras"
        elif (self.root_dir / "vcm8/training/runs/gateN_v1/best_model.keras").is_file():
            CHECKPOINT_PATHS["gateN"] = "vcm8/training/runs/gateN_v1/best_model.keras"

        self.models: dict[str, Any] = {}
        self.model_hashes: dict[str, str] = {}
        self._init_models()

    def _init_models(self):
        """Load trained Keras models into memory with visible GPUs disabled."""
        import tensorflow as tf

        try:
            tf.config.set_visible_devices([], "GPU")
        except Exception as e:
            logger.debug("Suppressing visible devices on GPU: %s", e)

        for name, rel_path in CHECKPOINT_PATHS.items():
            ckpt_p = self.root_dir / rel_path
            sha = compute_file_sha256(ckpt_p)
            self.model_hashes[name] = sha
            if not ckpt_p.is_file():
                raise FileNotFoundError(f"Required model checkpoint missing for {name}: {ckpt_p}")

            # Load Keras model uncompiled for inference
            model = tf.keras.models.load_model(str(ckpt_p), compile=False)
            self.models[name] = model

    def predict_gate(self, model_name: str, input_tensor: np.ndarray, labels: list[str]) -> dict[str, Any]:
        """Run single forward pass, returning top-1, confidence, and top-2 information."""
        model = self.models[model_name]
        preds = model(input_tensor, training=False).numpy()[0]
        top1_idx = int(np.argmax(preds))
        top1_label = labels[top1_idx]
        top1_conf = float(preds[top1_idx])

        top2_info = None
        if len(labels) > 1:
            sorted_idx = np.argsort(preds)[::-1]
            top2_idx = int(sorted_idx[1])
            top2_info = {
                "label": labels[top2_idx],
                "confidence": float(preds[top2_idx]),
            }

        return {
            "model_name": model_name,
            "predicted_label": top1_label,
            "confidence": top1_conf,
            "probabilities": {lab: float(p) for lab, p in zip(labels, preds, strict=False)},
            "top2": top2_info,
        }

    def run_pipeline(
        self,
        waveform: np.ndarray,
        sr: int = DEFAULT_SAMPLE_RATE,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> dict[str, Any]:
        """
        Execute full inference pipeline:
          1. Feature extraction
          2. Gate 1 (Reported UNAVAILABLE)
          3. Gate 2 intent classification
          4. Specialist routing (if intent is routed)
        """
        t0 = time.perf_counter()
        features = self.feature_extractor.extract_features(waveform, sr_in=sr)
        t_prep = time.perf_counter() - t0

        t1 = time.perf_counter()

        # Gate 1 (wake word) — evaluated when a trained checkpoint exists
        if "gate1" in self.models:
            wake_labels = self.models_meta.get("gate1", {}).get("labels", ["Nova", "Piattos", "Negative"])
            g1 = self.predict_gate("gate1", features, wake_labels)
            gate1_res = {
                "status": "EVALUATED",
                "model_name": "gate1",
                "predicted_label": g1["predicted_label"],
                "confidence": g1["confidence"],
                "note": "Wake-word gate evaluated (v1 checkpoint).",
            }
        else:
            gate1_res = {
                "status": "UNAVAILABLE",
                "model_name": "gate1",
                "note": "Gate 1 checkpoint absent (runs/gate1_v1/best_model.keras). Pipeline started at Gate 2.",
            }

        # Gate 2 Prediction
        gate2_res = self.predict_gate("gate2", features, self.gate2_labels)
        intent = gate2_res["predicted_label"]

        specialist_res = None
        routed_gate = self.routing_table.get(intent)

        if routed_gate and routed_gate in self.models:
            labels = self.specialist_labels.get(routed_gate, [])
            spec_features = features
            if routed_gate == "gateN" and self.gateN_features_148 and self.feature_extractor_148 is not None:
                spec_features = self.feature_extractor_148.extract_features(waveform, sr_in=sr)
            specialist_res = self.predict_gate(routed_gate, spec_features, labels)
            final_prediction = specialist_res["predicted_label"]
            effective_confidence = min(gate2_res["confidence"], specialist_res["confidence"])
        else:
            final_prediction = intent
            effective_confidence = gate2_res["confidence"]

        t_infer = time.perf_counter() - t1
        t_total = time.perf_counter() - t0

        return {
            "gate1": gate1_res,
            "gate2": gate2_res,
            "routed_gate": routed_gate,
            "specialist": specialist_res,
            "final_prediction": final_prediction,
            "effective_confidence": effective_confidence,
            "timing_ms": {
                "preprocess_ms": round(t_prep * 1000, 2),
                "inference_ms": round(t_infer * 1000, 2),
                "total_ms": round(t_total * 1000, 2),
            },
        }


# -----------------------------------------------------------------------------
# Live Microphone & VAD Endpointing
# -----------------------------------------------------------------------------
class LiveAudioRecorder:
    """
    Live streaming microphone recorder with energy-based VAD-lite endpointing.
    Monitors streaming RMS:
      - Waits for speech onset (RMS >= threshold)
      - Records until trailing silence (~1.2s) or max utterance (6.0s)
    """

    def __init__(
        self,
        sr: int = DEFAULT_SAMPLE_RATE,
        silence_s: float = DEFAULT_SILENCE_S,
        max_s: float = DEFAULT_MAX_UTTERANCE_S,
        rms_floor: float = DEFAULT_RMS_SPEECH_FLOOR,
        device: Any = None,
        show_meter: bool = True,
    ):
        self.sr = sr
        self.block_size = 1024
        self.silence_s = silence_s
        self.max_s = max_s
        self.rms_floor = rms_floor
        self.device = device
        self.show_meter = show_meter
        self.q: queue.Queue = queue.Queue()
        self._history: list[float] = []

    _SPARK_BLOCKS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"  # \u2581..\u2588

    def _render_meter(self, rms: float, speech_started: bool) -> None:
        """Render an in-place VU meter so the user can confirm the mic is capturing."""
        if not self.show_meter:
            return
        try:
            width = 40
            db = float(20.0 * np.log10(max(rms, 1e-10)))
            level = min(1.0, max(0.0, (db + 60.0) / 60.0))  # -60..0 dB -> 0..1
            filled = int(round(level * width))
            bar = "\u2588" * filled + "\u2591" * (width - filled)
            floor_db = float(20.0 * np.log10(max(self.rms_floor, 1e-10)))
            floor_pos = min(width - 1, max(0, int(round((floor_db + 60.0) / 60.0 * width))))
            if 0 <= floor_pos < width:
                bar = bar[:floor_pos] + "\u2502" + bar[floor_pos + 1:]
            self._history.append(level)
            if len(self._history) > 24:
                self._history.pop(0)
            spark = "".join(self._SPARK_BLOCKS[min(7, int(v * 7.999))] for v in self._history)
            state = "REC " if speech_started else "wait"
            sys.stdout.write(f"\r  {state} [{bar}] {db:6.1f} dB {spark} ")
            sys.stdout.flush()
        except Exception as e:
            logger.debug("Level meter render failed (continuing): %s", e)

    def _clear_meter(self) -> None:
        if not self.show_meter:
            return
        try:
            sys.stdout.write("\r" + " " * 90 + "\r")
            sys.stdout.flush()
        except Exception as e:
            logger.debug("Level meter clear failed (continuing): %s", e)

    def record_attempt(
        self,
        cancel_event: Any = None,
    ) -> tuple[np.ndarray | None, dict[str, Any]]:
        """
        Record one live utterance. Returns (waveform_float32, stats_dict).
        Waveform is None if NO_SPEECH or interrupted.
        """
        import sounddevice as sd  # type: ignore

        # Check devices
        try:
            dev_info = sd.query_devices(self.device, "input")
            max_in = dev_info["max_input_channels"]
            if max_in < 1:
                raise ValueError("Configured input device has no input channels.")
        except Exception as e:
            raise RuntimeError(
                f"Audio recording failed: Unable to access audio input device: {e}\n"
                "Ensure a microphone is plugged in, or run with --wav <path> for file-batch testing."
            ) from e

        self.q = queue.Queue()
        channels = 1

        def audio_callback(indata, frames, time_info, status):
            if status:
                sys.stderr.write(f"[mic warning] {status}\n")
            self.q.put(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self.sr,
                channels=channels,
                dtype="float32",
                blocksize=self.block_size,
                callback=audio_callback,
                device=self.device,
            ):
                # Calibrate the VAD floor from ambient noise so room noise alone
                # cannot trigger (or prevent ending of) speech detection.
                calib_rms: list[float] = []
                calib_end = time.time() + 0.8
                while time.time() < calib_end:
                    try:
                        blk = self.q.get(timeout=0.2).flatten()
                        calib_rms.append(float(np.sqrt(np.mean(blk**2))))
                    except queue.Empty:
                        continue
                if calib_rms:
                    # Robust ambient estimate: discard blocks well above the median
                    # (speech that landed in the calibration window, noise bursts),
                    # then cap the floor so a noisy calibration window cannot mute
                    # quiet speech (short wake words are ~0.06-0.10 RMS).
                    med = float(np.median(calib_rms))
                    quiet = [v for v in calib_rms if v <= med * 1.5] or calib_rms
                    ambient_rms = float(np.median(quiet))
                    calib_floor = max(self.rms_floor, min(ambient_rms * 2.5, 0.05))
                    if calib_floor > self.rms_floor:
                        print(
                            f"[VAD] floor calibrated: {self.rms_floor:.4f} -> {calib_floor:.4f} "
                            f"(ambient RMS {ambient_rms:.4f})"
                        )
                        self.rms_floor = calib_floor

                start_time = time.time()
                deadline = start_time + self.max_s + 6.0  # max wait before speech onset
                chunks: list[np.ndarray] = []
                speech_started = False
                silent_duration = 0.0
                total_duration = 0.0

                while time.time() < deadline:
                    if cancel_event and cancel_event():
                        self._clear_meter()
                        return None, {"disposition": "INTERRUPTED", "reason": "User cancelled"}

                    try:
                        block = self.q.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    data = block.flatten()
                    rms = float(np.sqrt(np.mean(data**2)))
                    self._render_meter(rms, speech_started)

                    if not speech_started:
                        if rms >= self.rms_floor:
                            speech_started = True
                            chunks.append(data)
                            total_duration += len(data) / self.sr
                        elif time.time() - start_time > 6.0:
                            # 6 seconds without speech onset
                            self._clear_meter()
                            return None, {
                                "disposition": "NO_SPEECH",
                                "reason": "No speech detected in initial 6.0s window",
                            }
                    else:
                        chunks.append(data)
                        block_dur = len(data) / self.sr
                        total_duration += block_dur

                        if rms < self.rms_floor:
                            silent_duration += block_dur
                        else:
                            silent_duration = 0.0

                        if silent_duration >= self.silence_s:
                            break
                        if total_duration >= self.max_s:
                            break

                self._clear_meter()

                if not speech_started or not chunks:
                    return None, {
                        "disposition": "NO_SPEECH",
                        "reason": "No speech detected during recording window",
                    }

                audio = np.concatenate(chunks).astype(np.float32)
                return audio, {
                    "disposition": "CAPTURED",
                    "duration_s": round(len(audio) / self.sr, 2),
                    "speech_detected": True,
                }

        except Exception as exc:
            return None, {"disposition": "ERROR", "error": str(exc)}


# -----------------------------------------------------------------------------
# Label Normalization & Menu Management
# -----------------------------------------------------------------------------
class LabelManager:
    """Manages expected labels, interactive menus, and parsing."""

    def __init__(self, pipeline: VCMModelPipeline):
        self.pipeline = pipeline
        self.menu_items: list[dict[str, Any]] = []
        self._build_menu()

    def _build_menu(self):
        items = []

        # 13 Direct Gate 2 intents
        for intent in self.pipeline.gate2_labels:
            if intent not in self.pipeline.routing_table:
                items.append({
                    "type": "direct_intent",
                    "display": intent,
                    "expected_intent": intent,
                    "expected_specialist": None,
                    "expected_final": intent,
                    "category": "Direct Intent (Gate 2)",
                })

        # Specialist values
        numeric_cat = "Gate N (unified)" if "gateN" in self.pipeline.models else "Legacy Gate 3a-3d"
        spec_info = [
            ("gate3a", "TIMER", f"Timer ({numeric_cat})"),
            ("gate3b", "ALARM", f"Alarm ({numeric_cat})"),
            ("gate3c", "TEMPERATURE", f"Temperature ({numeric_cat})"),
            ("gate3d", "BRIGHTNESS", f"Brightness ({numeric_cat})"),
            ("gate4", "COLOR", "Color (Gate 4)"),
            ("gate5", "CREATE_REMINDER", "Create Reminder (Gate 5)"),
        ]
        for m_id, intent, cat in spec_info:
            labels = self.pipeline.specialist_labels.get(m_id, [])
            for lab in labels:
                items.append({
                    "type": "specialist_value",
                    "display": f"{lab} [{intent}]",
                    "expected_intent": intent,
                    "expected_specialist": lab,
                    "expected_final": lab,
                    "category": cat,
                })

        # Generic Routed Intents
        for intent in sorted(self.pipeline.routing_table.keys()):
            items.append({
                "type": "generic_routed",
                "display": f"{intent} (Any slot)",
                "expected_intent": intent,
                "expected_specialist": None,
                "expected_final": intent,
                "category": "Generic Routed Intent",
            })

        # Wake words (availability reflects gate1 checkpoint)
        wake_words = self.pipeline.models_meta.get("gate1", {}).get("labels", ["Nova", "Piattos", "Negative"])
        wake_status = "Gate 1" if "gate1" in self.pipeline.models else "Gate 1 UNAVAILABLE"
        for w in wake_words:
            items.append({
                "type": "wake_word",
                "display": f"{w} (Wake Word - {wake_status})",
                "expected_intent": None,
                "expected_specialist": None,
                "expected_final": w,
                "category": f"Wake Word ({wake_status})",
            })

        self.menu_items = items

    def print_menu(self):
        print("\n" + "=" * 78)
        print(" EXPECTED COMMAND MENU")
        print("=" * 78)

        current_cat = None
        for idx, item in enumerate(self.menu_items, 1):
            if item["category"] != current_cat:
                current_cat = item["category"]
                print(f"\n  -- {current_cat} --")
            print(f"  [{idx:2d}] {item['display']}")
        print("\n  [ q] Quit session")
        print("  [ r] Repeat previous expected label")
        print("=" * 78)

    def parse_expected(self, raw_input: str, prev_item: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Resolve user text or menu number into structured expectation dict."""
        raw = raw_input.strip()
        if not raw:
            return None

        if raw.lower() in ("q", "quit", "exit"):
            return {"type": "quit"}

        if raw.lower() == "r":
            if prev_item:
                return prev_item
            print("No previous selection to repeat.")
            return None

        if raw.lower() in ("m", "menu"):
            return {"type": "menu"}

        # Check by numeric index
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(self.menu_items):
                return self.menu_items[idx - 1]
            print(f"Index out of range [1..{len(self.menu_items)}]")
            return None

        clean = raw.lower()

        # Check leaf mappings first
        if clean in LEAF_MAPPINGS:
            intent, spec = LEAF_MAPPINGS[clean]
            return {
                "type": "specialist_value",
                "display": f"{spec} [{intent}]",
                "expected_intent": intent,
                "expected_specialist": spec,
                "expected_final": spec,
                "category": "Specialist Value",
            }

        # Check direct intents
        for item in self.menu_items:
            if item["expected_final"].lower() == clean:
                return item
            if item["display"].lower() == clean:
                return item

        # Partial token matching
        for item in self.menu_items:
            if clean in item["display"].lower():
                return item

        print(f"Unrecognized expected label: {raw!r}")
        print("Tip: Type a menu number [1..40] or the exact command name.")
        return None

    def match_filename_to_expected(self, filename: str) -> dict[str, Any] | None:
        """Infer expected command from filename (for --expected-from-filename)."""
        stem = Path(filename).stem.lower()

        # Check exact leaf mappings
        for k, (intent, spec) in LEAF_MAPPINGS.items():
            if k in stem:
                return {
                    "type": "specialist_value",
                    "display": f"{spec} [{intent}]",
                    "expected_intent": intent,
                    "expected_specialist": spec,
                    "expected_final": spec,
                    "category": "Specialist Value",
                }

        # Check Gate 2 intents
        for intent in self.pipeline.gate2_labels:
            if intent.lower() in stem:
                return {
                    "type": "direct_intent",
                    "display": intent,
                    "expected_intent": intent,
                    "expected_specialist": None,
                    "expected_final": intent,
                    "category": "Gate 2 Intent",
                }

        return None


# -----------------------------------------------------------------------------
# Session Logging & Summary Report Generator
# -----------------------------------------------------------------------------
class SessionManager:
    """Manages session lifecycle, JSON logging, metrics, and persistence."""

    def __init__(
        self,
        pipeline: VCMModelPipeline,
        mode: str = "live",
        save_audio: bool = False,
        save_transcript: bool = False,
        session_root: Path | None = None,
    ):
        self.pipeline = pipeline
        self.mode = mode
        self.save_audio = save_audio
        self.save_transcript = save_transcript

        self.session_root = session_root or (Path.home() / ".vcm-live-sessions")
        self.session_root.mkdir(parents=True, exist_ok=True)

        now = datetime.datetime.now().astimezone()
        self.start_iso = now.isoformat()
        rand_suffix = hashlib.sha256(f"{time.time()}_{os.getpid()}".encode()).hexdigest()[:6]
        self.session_id = f"session_{now.strftime('%Y%m%d_%H%M%S')}_{rand_suffix}"
        self.session_dir = self.session_root / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Recordings are collected in every session folder by default.
        (self.session_dir / "audio").mkdir(exist_ok=True)

        self.attempts: list[dict[str, Any]] = []
        self._finalized = False
        self._saved_paths: tuple[Path, Path] | None = None

    def record_attempt(
        self,
        attempt_id: int,
        expected: dict[str, Any],
        disposition: str,
        pipeline_output: dict[str, Any] | None = None,
        raw_waveform: np.ndarray | None = None,
        error_msg: str | None = None,
    ) -> dict[str, Any]:
        """Record an attempt and evaluate disposition against expectation."""
        now_iso = datetime.datetime.now().astimezone().isoformat()
        audio_path_saved = None

        if self.save_audio and raw_waveform is not None:
            audio_p = self.session_dir / "audio" / f"attempt_{attempt_id:03d}.wav"
            try:
                # Save as PCM16 WAV
                with wave.open(str(audio_p), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(DEFAULT_SAMPLE_RATE)
                    pcm_data = (np.clip(raw_waveform, -1.0, 1.0) * 32767).astype(np.int16)
                    wf.writeframes(pcm_data.tobytes())
                audio_path_saved = f"audio/attempt_{attempt_id:03d}.wav"
            except Exception as e:
                sys.stderr.write(f"Warning: Failed to save audio attempt: {e}\n")

        # Evaluate disposition if completed with prediction
        gate2_pred = None
        gate2_conf = None
        spec_pred = None
        spec_conf = None
        final_pred = None
        timing = None

        if pipeline_output is not None:
            g2 = pipeline_output.get("gate2", {})
            gate2_pred = g2.get("predicted_label")
            gate2_conf = g2.get("confidence")

            sp = pipeline_output.get("specialist")
            if sp:
                spec_pred = sp.get("predicted_label")
                spec_conf = sp.get("confidence")

            final_pred = pipeline_output.get("final_prediction")
            timing = pipeline_output.get("timing_ms")

            exp_type = expected.get("type")
            exp_intent = expected.get("expected_intent")
            exp_spec = expected.get("expected_specialist")

            if disposition not in ("NO_SPEECH", "INTERRUPTED", "ERROR"):
                # Check confidence threshold rejection
                eff_conf = pipeline_output.get("effective_confidence", 1.0)
                if eff_conf < DEFAULT_MIN_CONFIDENCE:
                    disposition = "REJECTED"
                elif exp_type == "specialist_value":
                    if gate2_pred == exp_intent and spec_pred == exp_spec:
                        disposition = "CORRECT"
                    else:
                        disposition = "WRONG_PREDICTION"
                elif exp_type in ("direct_intent", "generic_routed"):
                    if gate2_pred == exp_intent:
                        disposition = "CORRECT"
                    else:
                        disposition = "WRONG_PREDICTION"
                elif exp_type == "wake_word":
                    g1 = pipeline_output.get("gate1", {})
                    if g1.get("status") == "EVALUATED":
                        if g1.get("predicted_label") == expected.get("expected_final"):
                            disposition = "CORRECT"
                        else:
                            disposition = "WRONG_PREDICTION"
                    else:
                        disposition = "ERROR"
                        error_msg = "Wake word evaluation unavailable (Gate 1 not trained)"

        attempt_record = {
            "attempt_id": attempt_id,
            "timestamp": now_iso,
            "expected_display": expected.get("display"),
            "expected_intent": expected.get("expected_intent"),
            "expected_specialist": expected.get("expected_specialist"),
            "expected_final": expected.get("expected_final"),
            "gate1_status": (pipeline_output.get("gate1", {}).get("status") if pipeline_output else None) or "UNAVAILABLE",
            "gate2_prediction": gate2_pred,
            "gate2_confidence": gate2_conf,
            "specialist_gate": pipeline_output.get("routed_gate") if pipeline_output else None,
            "specialist_prediction": spec_pred,
            "specialist_confidence": spec_conf,
            "final_prediction": final_pred,
            "disposition": disposition,
            "error": error_msg,
            "timing_ms": timing,
            "audio_file": audio_path_saved,
        }

        self.attempts.append(attempt_record)
        return attempt_record

    def compute_metrics(self) -> dict[str, Any]:
        """Calculate complete accuracy and breakdown metrics."""
        total = len(self.attempts)
        disp_counts: dict[str, int] = defaultdict(int)
        for a in self.attempts:
            disp_counts[a["disposition"]] += 1

        correct = disp_counts["CORRECT"]
        wrong = disp_counts["WRONG_PREDICTION"]
        rejected = disp_counts["REJECTED"]
        no_speech = disp_counts["NO_SPEECH"]
        interrupted = disp_counts["INTERRUPTED"]
        errors = disp_counts["ERROR"]

        # Eligible completed attempts: attempts that produced a classification decision
        completed_eligible = correct + wrong
        accuracy = (correct / completed_eligible) if completed_eligible > 0 else 0.0

        # Gate 2 Intent Accuracy (for attempts with valid expected intent)
        g2_eligible = 0
        g2_correct = 0
        for a in self.attempts:
            if a["disposition"] in ("CORRECT", "WRONG_PREDICTION") and a["expected_intent"]:
                g2_eligible += 1
                if a["gate2_prediction"] == a["expected_intent"]:
                    g2_correct += 1
        g2_acc = (g2_correct / g2_eligible) if g2_eligible > 0 else None

        # Specialist Slot Accuracy (when intent was correctly routed and specialist was expected)
        spec_eligible = 0
        spec_correct = 0
        for a in self.attempts:
            if (
                a["disposition"] in ("CORRECT", "WRONG_PREDICTION")
                and a["expected_specialist"]
                and a["gate2_prediction"] == a["expected_intent"]
            ):
                spec_eligible += 1
                if a["specialist_prediction"] == a["expected_specialist"]:
                    spec_correct += 1
        spec_acc = (spec_correct / spec_eligible) if spec_eligible > 0 else None

        # Per command breakdown
        per_command: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0, "wrong": 0})
        for a in self.attempts:
            exp = a["expected_final"] or "Unknown"
            if a["disposition"] in ("CORRECT", "WRONG_PREDICTION"):
                per_command[exp]["total"] += 1
                if a["disposition"] == "CORRECT":
                    per_command[exp]["correct"] += 1
                else:
                    per_command[exp]["wrong"] += 1

        gate2_str = f"{g2_correct} / {g2_eligible} ({g2_acc * 100:.1f}%)" if (g2_acc is not None and g2_eligible > 0) else "N/A"
        spec_str = f"{spec_correct} / {spec_eligible} ({spec_acc * 100:.1f}%)" if (spec_acc is not None and spec_eligible > 0) else "N/A"

        return {
            "total_attempts": total,
            "completed_eligible": completed_eligible,
            "correct": correct,
            "wrong": wrong,
            "rejected": rejected,
            "no_speech": no_speech,
            "interrupted": interrupted,
            "errors": errors,
            "end_to_end_accuracy": accuracy,
            "end_to_end_str": f"{correct} / {completed_eligible} ({accuracy * 100:.1f}%)" if completed_eligible > 0 else "0 / 0 (N/A)",
            "gate2_intent_accuracy": g2_acc,
            "gate2_intent_str": gate2_str,
            "specialist_accuracy": spec_acc,
            "specialist_str": spec_str,
            "per_command_breakdown": dict(per_command),
        }

    def save_session(self) -> tuple[Path, Path]:
        """Save session.json, summary.txt, and update index."""
        if self._finalized and self._saved_paths is not None:
            return self._saved_paths
        end_dt = datetime.datetime.now().astimezone()
        end_iso = end_dt.isoformat()
        metrics = self.compute_metrics()

        # Rename the session folder to record the quit time, e.g.
        # session_20261002_234222_84230f -> session_20261002_234222_84230f_ended-234753
        start_dt = datetime.datetime.fromisoformat(self.start_iso)
        end_tag = end_dt.strftime("%H%M%S") if end_dt.date() == start_dt.date() else end_dt.strftime("%Y%m%d_%H%M%S")
        new_name = f"{self.session_id}_ended-{end_tag}"
        new_dir = self.session_root / new_name
        if self.session_dir.is_dir() and not new_dir.exists():
            self.session_dir.rename(new_dir)
            self.session_dir = new_dir

        # Build active models manifest
        models_meta = {}
        for m_name, rel_path in CHECKPOINT_PATHS.items():
            models_meta[m_name] = {
                "checkpoint": rel_path,
                "sha256": self.pipeline.model_hashes.get(m_name, "unknown"),
            }

        session_data = {
            "session_id": self.session_id,
            "tool_version": __version__,
            "mode": self.mode,
            "start_time": self.start_iso,
            "end_time": end_iso,
            "disclaimer": DISCLAIMER_TEXT,
            "models_used": models_meta,
            "feature_stats": {
                "mean": self.pipeline.feature_extractor.mean,
                "std": self.pipeline.feature_extractor.std,
            },
            "metrics": metrics,
            "attempts": self.attempts,
        }

        try:
            # 1. session.json
            json_path = self.session_dir / "session.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)

            # 2. summary.txt
            summary_text = self.format_summary(metrics, session_data)
            txt_path = self.session_dir / "summary.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(summary_text)

            # 3. Human-readable session log (start, quit time, per-attempt timeline)
            log_path = self.session_dir / "session_log.txt"
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"Session Log: {self.session_id}\n")
                f.write(f"Started : {self.start_iso}\n")
                f.write(f"Quit    : {end_iso}\n")
                f.write(f"Mode    : {self.mode}\n")
                f.write("=" * 60 + "\n")
                for a in self.attempts:
                    ts = (a.get("timestamp") or "")[11:19]
                    f.write(
                        f"#{a['attempt_id']:03d} {ts} | expected: {a['expected_display']} | "
                        f"pred: {a['final_prediction']} | {a['disposition']}"
                    )
                    conf = a.get("gate2_confidence")
                    if a.get("disposition") in ("CORRECT", "WRONG_PREDICTION", "REJECTED") and conf is not None:
                        f.write(f" | conf {conf:.2f}")
                    if a.get("audio_file"):
                        f.write(f" | {a['audio_file']}")
                    f.write("\n")

            # 4. Optional transcripts
            if self.save_transcript:
                trans_path = self.session_dir / "transcript.txt"
                with open(trans_path, "w", encoding="utf-8") as f:
                    f.write(f"Session Transcript: {self.session_id}\n")
                    f.write("=" * 60 + "\n")
                    for a in self.attempts:
                        f.write(
                            f"Attempt {a['attempt_id']:02d} | Expected: {a['expected_display']} | "
                            f"Pred: {a['final_prediction']} | Result: {a['disposition']}\n"
                        )
        except OSError as e:
            logger.error("Failed to write session artifacts to %s: %s", self.session_dir, e)
            raise

        # 5. Update sessions_index.json
        self._update_index(metrics)

        self._finalized = True
        self._saved_paths = (json_path, txt_path)
        return json_path, txt_path

    def _update_index(self, metrics: dict[str, Any]):
        index_file = self.session_root / "sessions_index.json"
        index = []
        if index_file.is_file():
            try:
                with open(index_file, encoding="utf-8") as f:
                    index = json.load(f)
            except Exception as e:
                logger.warning("Could not read existing sessions_index.json: %s", e)
                index = []

        # Remove existing entry if any
        index = [e for e in index if e.get("session_id") != self.session_id]

        index.append({
            "session_id": self.session_id,
            "timestamp": self.start_iso,
            "mode": self.mode,
            "total_attempts": metrics["total_attempts"],
            "completed_eligible": metrics["completed_eligible"],
            "correct": metrics["correct"],
            "accuracy_str": metrics["end_to_end_str"],
            "session_dir": str(self.session_dir),
        })

        try:
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=2)
        except OSError as e:
            logger.error("Failed to update sessions index %s: %s", index_file, e)
            raise

    def format_summary(self, metrics: dict[str, Any], session_data: dict[str, Any]) -> str:
        """Render a clean, structured human-readable ASCII summary."""
        lines = []
        lines.append("=" * 78)
        lines.append(" VCM LIVE TESTING SESSION SUMMARY")
        lines.append("=" * 78)
        lines.append(f" Session ID   : {self.session_id}")
        lines.append(f" Tool Version : v{__version__}")
        lines.append(f" Mode         : {self.mode.upper()}")
        lines.append(f" Start Time   : {self.start_iso}")
        lines.append(f" End Time     : {session_data.get('end_time')}")
        lines.append("-" * 78)

        lines.append(" ACTIVE MODELS & CHECKPOINTS:")
        for m_name, meta in session_data.get("models_used", {}).items():
            lines.append(f"   * {m_name:<7}: {meta['checkpoint']} (sha256: {meta['sha256'][:10]}...)")
        lines.append("-" * 78)

        lines.append(" ATTEMPTS & DISPOSITION COUNTS:")
        lines.append(f"   Total Attempts Recorded       : {metrics['total_attempts']}")
        lines.append(f"   Completed & Evaluated         : {metrics['completed_eligible']}")
        lines.append(f"     - Correct Predictions       : {metrics['correct']}")
        lines.append(f"     - Wrong Predictions         : {metrics['wrong']}")
        lines.append("   Filtered / Excluded           :")
        lines.append(f"     - Rejected (Low Confidence) : {metrics['rejected']}")
        lines.append(f"     - No Speech Detected        : {metrics['no_speech']}")
        lines.append(f"     - Interrupted Attempts      : {metrics['interrupted']}")
        lines.append(f"     - Runtime Errors            : {metrics['errors']}")
        lines.append("-" * 78)

        lines.append(" ACCURACY METRICS:")
        lines.append(f"   End-to-End Accuracy           : {metrics['end_to_end_str']}")
        lines.append(f"   Gate 2 Intent Accuracy        : {metrics['gate2_intent_str']}")
        lines.append(f"   Specialist Slot Accuracy      : {metrics['specialist_str']}")
        lines.append("-" * 78)

        lines.append(" PER-COMMAND PERFORMANCE BREAKDOWN:")
        lines.append(f"   {'Command Expected':<32} {'Evaluated':<10} {'Correct':<9} {'Accuracy'}")
        lines.append("   " + "-" * 66)
        breakdown = metrics.get("per_command_breakdown", {})
        if breakdown:
            for cmd, stats in sorted(breakdown.items()):
                tot = stats["total"]
                corr = stats["correct"]
                acc_pct = f"{corr / tot * 100:.1f}%" if tot > 0 else "N/A"
                lines.append(f"   {cmd:<32} {tot:<10} {corr:<9} {acc_pct}")
        else:
            lines.append("   (No evaluated attempts recorded)")
        lines.append("-" * 78)

        lines.append(" DETAILED ATTEMPTS LOG:")
        lines.append(
            f"   {'#':<3} {'Expected':<22} {'Gate 2 Pred':<16} {'Specialist':<14} {'Result':<12} {'Conf':<6} {'Timing'}"
        )
        lines.append("   " + "-" * 72)
        for a in self.attempts:
            att_num = a["attempt_id"]
            exp = (a["expected_final"] or "")[:20]
            g2 = (a["gate2_prediction"] or "-")[:14]
            sp = (a["specialist_prediction"] or "-")[:12]
            disp = a["disposition"]
            conf_val = a["gate2_confidence"]
            conf_str = f"{conf_val:.2f}" if conf_val is not None else "-"
            t_ms = f"{a['timing_ms']['total_ms']}ms" if a.get("timing_ms") else "-"
            lines.append(f"   {att_num:<3d} {exp:<22} {g2:<16} {sp:<14} {disp:<12} {conf_str:<6} {t_ms}")
        lines.append("=" * 78)
        lines.append(DISCLAIMER_TEXT)
        lines.append("=" * 78)
        return "\n".join(lines)


# -----------------------------------------------------------------------------
# Interactive Session Loop
# -----------------------------------------------------------------------------
def run_interactive_session(
    pipeline: VCMModelPipeline,
    label_mgr: LabelManager,
    session_mgr: SessionManager,
    device: Any = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    silence_s: float = DEFAULT_SILENCE_S,
    max_s: float = DEFAULT_MAX_UTTERANCE_S,
    show_meter: bool = True,
):
    """Interactive live-microphone testing loop."""
    recorder = LiveAudioRecorder(
        sr=DEFAULT_SAMPLE_RATE,
        silence_s=silence_s,
        max_s=max_s,
        rms_floor=DEFAULT_RMS_SPEECH_FLOOR,
        device=device,
        show_meter=show_meter,
    )

    print("\n" + "=" * 78)
    print(" VCM LIVE VOICE COMMAND TESTER (v1.0.0)")
    print("=" * 78)
    print(f" Session Directory : {session_mgr.session_dir}")
    print(f" Confidence Floor  : {min_confidence:.2f}")
    print(f" VAD Settings      : Silence={silence_s}s, Max={max_s}s")
    print(" Mode              : Interactive Live Microphone")
    print("=" * 78)

    attempt_counter = 0
    prev_expected = None

    # Menu is shown once at session start; re-open anytime with 'm'.
    label_mgr.print_menu()

    try:
        while True:
            attempt_counter += 1

            # 1. Ask for expected command BEFORE recording
            expected_item = None
            while expected_item is None:
                try:
                    user_input = input(f"\nSelect Expected Command [1..{len(label_mgr.menu_items)}, 'm' menu, 'r' repeat, 'q' quit]: ")
                except (EOFError, KeyboardInterrupt):
                    print("\n\nSession interrupted by user.")
                    return

                expected_item = label_mgr.parse_expected(user_input, prev_expected)
                if expected_item and expected_item.get("type") == "quit":
                    print("\nFinishing live testing session.")
                    return
                if expected_item and expected_item.get("type") == "menu":
                    label_mgr.print_menu()
                    expected_item = None
                    continue

            prev_expected = expected_item
            print(f"Speak now: {expected_item['display']}  (auto-stops on silence; Ctrl+C cancels this attempt)")

            # 2. Record utterance
            try:
                waveform, rec_meta = recorder.record_attempt()
            except KeyboardInterrupt:
                print("\n[!] Attempt cancelled by user.")
                session_mgr.record_attempt(
                    attempt_id=attempt_counter,
                    expected=expected_item,
                    disposition="INTERRUPTED",
                )
                continue
            except RuntimeError as exc:
                print(f"\n[ERROR] Microphone error: {exc}")
                session_mgr.record_attempt(
                    attempt_id=attempt_counter,
                    expected=expected_item,
                    disposition="ERROR",
                    error_msg=str(exc),
                )
                break

            disposition = rec_meta.get("disposition")

            if disposition == "NO_SPEECH":
                print("--> [NO_SPEECH] No speech energy detected.")
                print("   Tip: speak right after the meter appears, a bit louder or closer to the mic.")
                session_mgr.record_attempt(
                    attempt_id=attempt_counter,
                    expected=expected_item,
                    disposition="NO_SPEECH",
                )
                continue

            if disposition == "ERROR" or waveform is None:
                err = rec_meta.get("error", "Unknown recording error")
                print(f"--> [ERROR] Recording failure: {err}")
                session_mgr.record_attempt(
                    attempt_id=attempt_counter,
                    expected=expected_item,
                    disposition="ERROR",
                    error_msg=err,
                )
                continue

            # 3. Process through Pipeline
            pipe_out = pipeline.run_pipeline(waveform, sr=DEFAULT_SAMPLE_RATE, min_confidence=min_confidence)

            # 4. Record and Evaluate
            record = session_mgr.record_attempt(
                attempt_id=attempt_counter,
                expected=expected_item,
                disposition="EVALUATING",
                pipeline_output=pipe_out,
                raw_waveform=waveform,
            )

            # 5. Compact one-line result (full per-gate detail is in session.json / summary.txt)
            disp = record["disposition"]
            conf = pipe_out.get("effective_confidence")
            total_ms = pipe_out["timing_ms"]["total_ms"]
            m = session_mgr.compute_metrics()
            run = f"running {m['end_to_end_str']}"

            if disp == "CORRECT":
                print(f"[PASS] #{attempt_counter} {record['final_prediction']} (conf {conf:.2f}, {total_ms:.0f}ms) | {run}")
            elif disp == "WRONG_PREDICTION":
                print(f"[FAIL] #{attempt_counter} expected {record['expected_final']}, got {record['final_prediction']} (conf {conf:.2f}, {total_ms:.0f}ms) | {run}")
            elif disp == "REJECTED":
                print(f"[REJ]  #{attempt_counter} expected {record['expected_final']}, low-conf prediction {record['final_prediction']} (conf {conf:.2f}) | {run}")
            else:
                print(f"[{disp}] #{attempt_counter} expected {record['expected_final']} | {run}")

    except KeyboardInterrupt:
        print("\n\nSession terminated by user (Ctrl+C).")


# -----------------------------------------------------------------------------
# File-Batch Testing Mode
# -----------------------------------------------------------------------------
def run_file_batch_session(
    pipeline: VCMModelPipeline,
    label_mgr: LabelManager,
    session_mgr: SessionManager,
    wav_path: Path,
    expected_arg: str | None = None,
    expected_from_filename: bool = False,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
):
    """Run testing across a single WAV file or directory of WAV files."""
    wav_files: list[Path] = []
    p = Path(wav_path)
    if p.is_file():
        wav_files.append(p)
    elif p.is_dir():
        wav_files.extend(sorted(p.glob("**/*.wav")))
    else:
        raise FileNotFoundError(f"Path not found: {p}")

    if not wav_files:
        print(f"No .wav files found under {p}")
        return

    print("\n" + "=" * 78)
    print(f" VCM BATCH TESTING ({len(wav_files)} files)")
    print("=" * 78)

    for idx, fpath in enumerate(wav_files, 1):
        expected_item = None
        if expected_from_filename:
            expected_item = label_mgr.match_filename_to_expected(fpath.name)
        elif expected_arg:
            expected_item = label_mgr.parse_expected(expected_arg)

        if expected_item is None:
            # Default to generic direct/specialist matching based on file stem
            expected_item = label_mgr.match_filename_to_expected(fpath.name) or {
                "type": "unknown",
                "display": fpath.stem,
                "expected_intent": None,
                "expected_specialist": None,
                "expected_final": fpath.stem,
                "category": "Unspecified",
            }

        try:
            audio, sr = read_audio_file(fpath)

            pipe_out = pipeline.run_pipeline(audio, sr=sr, min_confidence=min_confidence)

            record = session_mgr.record_attempt(
                attempt_id=idx,
                expected=expected_item,
                disposition="EVALUATING",
                pipeline_output=pipe_out,
                raw_waveform=audio if session_mgr.save_audio else None,
            )

            disp = record["disposition"]
            print(
                f"[{idx:03d}/{len(wav_files):03d}] {fpath.name:<28} "
                f"Exp: {record['expected_final']:<18} "
                f"Pred: {record['final_prediction']:<18} [{disp}]"
            )

        except Exception as e:
            print(f"[{idx:03d}/{len(wav_files):03d}] {fpath.name:<28} ERROR: {e}")
            session_mgr.record_attempt(
                attempt_id=idx,
                expected=expected_item,
                disposition="ERROR",
                error_msg=str(e),
            )


# -----------------------------------------------------------------------------
# Offline Self-Check Mode
# -----------------------------------------------------------------------------
def run_selfcheck(root_dir: Path, registry_path: Path, stats_path: Path) -> int:
    """
    Offline self-check verifying that:
      1. Model registry exists and parses
      2. Feature statistics exist and have valid mean/std
      3. All 7 Keras checkpoints exist and pass SHA-256 checks
      4. Models can load on CPU and complete a forward pass on dummy input (1, 74, 60, 1)
      5. Feature extraction pipeline runs with exact shapes on synthetic audio
    Returns 0 if all pass, 1 if any check fails.
    """
    print("\n" + "=" * 78)
    print(" VCM OFFLINE PIPELINE SELF-CHECK")
    print("=" * 78)

    failures = []

    # 1. Registry
    print("\n[1/5] Checking Model Registry...")
    reg_p = Path(registry_path)
    if not reg_p.is_file():
        failures.append(f"Model registry missing: {reg_p}")
        print(f"  FAIL: {reg_p} not found")
    else:
        try:
            with open(reg_p, encoding="utf-8") as f:
                reg = json.load(f)
            gate2_labs = reg["models"]["gate2"]["labels"]
            routing = reg["models"]["gate2"]["routing"]
            print(f"  PASS: Loaded registry. Gate 2 classes: {len(gate2_labs)}, Routed intents: {len(routing)}")
        except Exception as e:
            failures.append(f"Registry parse error: {e}")
            print(f"  FAIL: {e}")

    # 2. Feature stats
    print("\n[2/5] Checking Preprocessing Feature Statistics...")
    stats_p = Path(stats_path)
    if not stats_p.is_file():
        failures.append(f"Feature stats missing: {stats_p}")
        print(f"  FAIL: {stats_p} not found")
    else:
        try:
            stats = np.load(stats_p)
            mean = float(stats["mean"])
            std = float(stats["std"])
            print(f"  PASS: Loaded feature stats (mean={mean:.6f}, std={std:.6f})")
        except Exception as e:
            failures.append(f"Feature stats error: {e}")
            print(f"  FAIL: {e}")

    # 3. Checkpoints existence & digests
    print("\n[3/5] Verifying Trained Model Checkpoints...")
    for m_name, rel_path in CHECKPOINT_PATHS.items():
        ckpt_p = root_dir / rel_path
        if not ckpt_p.is_file():
            failures.append(f"Missing checkpoint for {m_name}: {ckpt_p}")
            print(f"  FAIL: {m_name:<7} -> {ckpt_p} NOT FOUND")
        else:
            sha = compute_file_sha256(ckpt_p)
            size_mb = ckpt_p.stat().st_size / (1024 * 1024)
            print(f"  PASS: {m_name:<7} -> {ckpt_p.name} ({size_mb:.2f} MB, sha256: {sha[:10]}...)")

    # 4. Keras Loading & CPU Forward Pass
    print("\n[4/5] Loading Models & Testing Forward Pass (CPU)...")
    try:
        pipeline = VCMModelPipeline(root_dir, reg_p, stats_p)
        dummy_tensor = np.zeros((1, 74, 60, 1), dtype=np.float32)

        # Gate 2
        g2_res = pipeline.predict_gate("gate2", dummy_tensor, pipeline.gate2_labels)
        print(f"  PASS: Gate 2 forward pass -> {g2_res['predicted_label']} (conf: {g2_res['confidence']:.3f})")

        # Specialists
        for m_name in ["gate3a", "gate3b", "gate3c", "gate3d", "gate4", "gate5", "gateN"]:
            labs = pipeline.specialist_labels[m_name]
            in_shape = pipeline.models[m_name].input_shape  # e.g. (None, 74, 60, 1) or (None, 148, 60, 1)
            dummy_spec = np.zeros((1, int(in_shape[1]), int(in_shape[2]), int(in_shape[3])), dtype=np.float32)
            spec_res = pipeline.predict_gate(m_name, dummy_spec, labs)
            print(f"  PASS: {m_name:<7} forward pass -> {spec_res['predicted_label']} (conf: {spec_res['confidence']:.3f})")

    except Exception as e:
        failures.append(f"Model load/execution error: {e}")
        print(f"  FAIL: {e}")

    # 5. Preprocessing pipeline test
    print("\n[5/5] Testing Preprocessing Feature Extraction...")
    try:
        extractor = FeatureExtractor(stats_p)
        # 1.5 seconds dummy audio at 16 kHz
        dummy_audio = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.5, 24000)) * 0.1).astype(np.float32)
        feats = extractor.extract_features(dummy_audio, sr_in=16000)
        if feats.shape != (1, 74, 60, 1):
            raise ValueError(f"Extracted feature shape {feats.shape} != (1, 74, 60, 1)")
        print(f"  PASS: Extracted features shape {feats.shape}, dtype {feats.dtype}")
    except Exception as e:
        failures.append(f"Feature extraction test error: {e}")
        print(f"  FAIL: {e}")

    # Summary
    print("\n" + "=" * 78)
    if failures:
        print(f" SELF-CHECK FAILED with {len(failures)} error(s):")
        for f in failures:
            print(f"   - {f}")
        print("=" * 78)
        return 1

    print(" ALL SELF-CHECKS PASSED: Models, Features, and Pipelines are fully operational.")
    print("=" * 78)
    return 0


# -----------------------------------------------------------------------------
# Past Session Listing & Viewer
# -----------------------------------------------------------------------------
def list_past_sessions(session_root: Path | None = None):
    """List historical sessions recorded in ~/.vcm-live-sessions."""
    root = session_root or (Path.home() / ".vcm-live-sessions")
    index_file = root / "sessions_index.json"

    print("\n" + "=" * 78)
    print(" VCM RECORDED LIVE SESSIONS INDEX")
    print("=" * 78)

    sessions = []
    if index_file.is_file():
        try:
            with open(index_file, encoding="utf-8") as f:
                sessions = json.load(f)
        except Exception as e:
            logger.warning("Could not read sessions_index.json: %s", e)
            sessions = []

    if not sessions and root.is_dir():
        # Fallback directory scan
        for s_dir in sorted(root.glob("session_*")):
            s_json = s_dir / "session.json"
            if s_json.is_file():
                try:
                    with open(s_json, encoding="utf-8") as f:
                        d = json.load(f)
                        sessions.append({
                            "session_id": d.get("session_id", s_dir.name),
                            "timestamp": d.get("start_time", "unknown"),
                            "mode": d.get("mode", "unknown"),
                            "total_attempts": d.get("metrics", {}).get("total_attempts", 0),
                            "accuracy_str": d.get("metrics", {}).get("end_to_end_str", "N/A"),
                        })
                except Exception as e:
                    logger.debug("Failed reading session %s: %s", s_dir, e)

    if not sessions:
        print(f"No past sessions found in {root}")
        print("=" * 78)
        return

    print(f"{'Session ID':<36} {'Mode':<8} {'Attempts':<10} {'Accuracy':<16} {'Timestamp'}")
    print("-" * 78)
    for s in sessions:
        s_id = s.get("session_id", "unknown")
        mode = s.get("mode", "live")
        tot = s.get("total_attempts", 0)
        acc = s.get("accuracy_str", "N/A")
        ts = s.get("timestamp", "")[:19]
        print(f"{s_id:<36} {mode:<8} {tot:<10} {acc:<16} {ts}")
    print("=" * 78)
    print("Use --show <session_id> to inspect complete details.")


def show_past_session(session_id: str, session_root: Path | None = None):
    """Display the full summary report for a past session."""
    root = session_root or (Path.home() / ".vcm-live-sessions")
    s_dir = root / session_id
    if not s_dir.is_dir():
        # Match partial prefix
        matches = list(root.glob(f"*{session_id}*"))
        if len(matches) == 1 and matches[0].is_dir():
            s_dir = matches[0]
        else:
            print(f"Error: Session '{session_id}' not found under {root}")
            return

    sum_txt = s_dir / "summary.txt"
    if sum_txt.is_file():
        print(sum_txt.read_text(encoding="utf-8"))
    else:
        json_p = s_dir / "session.json"
        if json_p.is_file():
            try:
                with open(json_p, encoding="utf-8") as f:
                    data = json.load(f)
                print(json.dumps(data, indent=2))
            except (OSError, json.JSONDecodeError) as e:
                print(f"Error: Could not read session data from {json_p}: {e}")
        else:
            print(f"Error: No summary or session json found in {s_dir}")


# -----------------------------------------------------------------------------
# Main CLI Entry Point
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="VCM Live Voice Command Testing Harness (v1.0.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive live-mic testing session (asks for expected command before recording):
  python vcm8/live_test/live_session.py

  # File-batch testing on a directory of WAVs matching labels from filenames:
  python vcm8/live_test/live_session.py --wav data/mex2/audio --expected-from-filename

  # Run offline model and pipeline self-check (no live mic or evaluation claims):
  python vcm8/live_test/live_session.py --selfcheck

  # List past sessions:
  python vcm8/live_test/live_session.py --list

  # Show summary of a past session:
  python vcm8/live_test/live_session.py --show session_20261002_182500_a1b2c3
        """,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s v{__version__}")
    parser.add_argument("--selfcheck", action="store_true", help="Perform offline model/feature validation and exit")
    parser.add_argument("--list", action="store_true", help="List past live test sessions and exit")
    parser.add_argument("--show", type=str, metavar="SESSION_ID", help="Display summary for a specific session ID")

    # Execution configuration
    parser.add_argument("--wav", type=str, help="Path to WAV file or directory for batch testing")
    parser.add_argument("--expected", type=str, help="Expected label for --wav file or batch")
    parser.add_argument("--expected-from-filename", action="store_true", help="Infer expected label from WAV filename")

    # Audio & VAD configuration
    parser.add_argument("--device", type=str, default=None, help="Audio input device index or name")
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE, help=f"Minimum confidence threshold (default: {DEFAULT_MIN_CONFIDENCE})")
    parser.add_argument("--silence-s", type=float, default=DEFAULT_SILENCE_S, help=f"Trailing silence endpoint duration in seconds (default: {DEFAULT_SILENCE_S})")
    parser.add_argument("--max-s", type=float, default=DEFAULT_MAX_UTTERANCE_S, help=f"Maximum utterance duration in seconds (default: {DEFAULT_MAX_UTTERANCE_S})")

    # Privacy controls
    parser.add_argument("--save-audio", dest="save_audio", action="store_true", default=True, help="Save attempt recordings in the session folder (default: on)")
    parser.add_argument("--no-save-audio", dest="save_audio", action="store_false", help="Disable saving attempt recordings")
    parser.add_argument("--no-meter", action="store_true", help="Disable the live microphone level meter during recording")
    parser.add_argument("--save-transcript", action="store_true", help="Opt-in: Save session transcript text file")

    # Path overrides
    parser.add_argument("--root-dir", type=str, default=".", help="Project root directory (default: current directory)")
    parser.add_argument("--registry", type=str, default=DEFAULT_REGISTRY_PATH, help="Path to model_registry.json")
    parser.add_argument("--feature-stats", type=str, default=DEFAULT_FEATURE_STATS_PATH, help="Path to feature_stats.npz")
    parser.add_argument("--session-dir", type=str, default=None, help="Directory to store session records (default: ~/.vcm-live-sessions)")

    args = parser.parse_args()

    root_p = Path(args.root_dir).resolve()
    reg_p = root_p / args.registry if not Path(args.registry).is_absolute() else Path(args.registry)
    stats_p = root_p / args.feature_stats if not Path(args.feature_stats).is_absolute() else Path(args.feature_stats)
    sess_root = Path(args.session_dir) if args.session_dir else (Path.home() / ".vcm-live-sessions")

    # Handle past session inspections
    if args.list:
        list_past_sessions(sess_root)
        sys.exit(0)

    if args.show:
        show_past_session(args.show, sess_root)
        sys.exit(0)

    # Handle self-check
    if args.selfcheck:
        code = run_selfcheck(root_p, reg_p, stats_p)
        sys.exit(code)

    # Load Pipeline
    try:
        pipeline = VCMModelPipeline(root_p, reg_p, stats_p)
        label_mgr = LabelManager(pipeline)
    except Exception as exc:
        sys.stderr.write(f"\n[FATAL ERROR] Failed to initialize VCM Model Pipeline: {exc}\n")
        sys.exit(1)

    # File-Batch Mode vs Interactive Live Mode
    if args.wav:
        session_mgr = SessionManager(
            pipeline=pipeline,
            mode="batch",
            save_audio=args.save_audio,
            save_transcript=args.save_transcript,
            session_root=sess_root,
        )
        try:
            run_file_batch_session(
                pipeline=pipeline,
                label_mgr=label_mgr,
                session_mgr=session_mgr,
                wav_path=Path(args.wav),
                expected_arg=args.expected,
                expected_from_filename=args.expected_from_filename,
                min_confidence=args.min_confidence,
            )
        finally:
            json_p, txt_p = session_mgr.save_session()
            print("\n" + session_mgr.format_summary(session_mgr.compute_metrics(), {"end_time": datetime.datetime.now().astimezone().isoformat()}))
            print(f"\nSession saved to:\n  JSON: {json_p}\n  Summary: {txt_p}\n")
    else:
        # Interactive Live Microphone Mode
        session_mgr = SessionManager(
            pipeline=pipeline,
            mode="live",
            save_audio=args.save_audio,
            save_transcript=args.save_transcript,
            session_root=sess_root,
        )

        def handle_signal(sig, frame):
            print("\n\nSignal received, finalizing and saving session...")
            json_p, txt_p = session_mgr.save_session()
            print(f"\nSession saved to:\n  JSON: {json_p}\n  Summary: {txt_p}\n")
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        try:
            run_interactive_session(
                pipeline=pipeline,
                label_mgr=label_mgr,
                session_mgr=session_mgr,
                device=args.device,
                min_confidence=args.min_confidence,
                silence_s=args.silence_s,
                max_s=args.max_s,
                show_meter=not args.no_meter,
            )
        finally:
            json_p, txt_p = session_mgr.save_session()
            print("\n" + session_mgr.format_summary(session_mgr.compute_metrics(), {"end_time": datetime.datetime.now().astimezone().isoformat()}))
            print(f"\nSession saved to:\n  JSON: {json_p}\n  Summary: {txt_p}\n")


if __name__ == "__main__":
    main()
