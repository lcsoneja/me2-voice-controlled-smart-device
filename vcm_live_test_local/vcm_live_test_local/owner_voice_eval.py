"""Batch accuracy evaluation of Leandro's recorded voice test set (280 WAVs).

Scores each manifest entry through the live Gate 2 inference path using the same
5.92 s window contract as the PIPELINE page (audio front-padded to the model
window), then reports overall/per-intent accuracy and every mismatch.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np


def load_manifest_text(text: str) -> list[dict[str, str]]:
    """Parse manifest.csv content: file_name, intent, phrase (+ optional columns)."""
    rows = csv.DictReader(io.StringIO(text))
    entries: list[dict[str, str]] = []
    for row in rows:
        file_name = (row.get("file_name") or "").strip()
        intent = (row.get("intent") or "").strip()
        if not file_name or not intent:
            continue
        entries.append({"file": file_name, "intent": intent,
                        "phrase": (row.get("phrase") or "").strip()})
    return entries


def load_manifest(csv_path: Path) -> list[dict[str, str]]:
    return load_manifest_text(Path(csv_path).read_text(encoding="utf-8-sig"))


def evaluate_recordings(entries: list[Mapping[str, str]], predict_fn: Callable[..., tuple[str | None, float]],
                        *, loader: Callable[..., np.ndarray] | None = None) -> dict[str, Any]:
    """Score every entry; predict_fn(waveform, entry) -> (intent, conf).

    The waveform is passed at native length: the model preprocessing pads/crops
    per utterance (its training contract), so batch evaluation must NOT emulate
    the live 5.92 s sliding window.
    """
    total = 0
    correct = 0
    per_intent: dict[str, dict[str, Any]] = {}
    mismatches: list[dict[str, Any]] = []
    for entry in entries:
        total += 1
        intent = entry["intent"]
        bucket = per_intent.setdefault(intent, {"total": 0, "correct": 0, "accuracy": 0.0})
        bucket["total"] += 1
        waveform = loader(entry["file"], entry) if loader else np.zeros(0, dtype=np.float32)
        predicted, conf = predict_fn(waveform, entry)
        hit = predicted == intent
        if hit:
            correct += 1
            bucket["correct"] += 1
        else:
            mismatches.append({"file": entry["file"], "expected": intent,
                               "predicted": predicted, "conf": conf, "phrase": entry.get("phrase", "")})
    for bucket in per_intent.values():
        bucket["accuracy"] = bucket["correct"] / bucket["total"] if bucket["total"] else 0.0
    return {"total": total, "correct": correct,
            "accuracy": (correct / total) if total else 0.0,
            "per_intent": per_intent, "mismatches": mismatches}
