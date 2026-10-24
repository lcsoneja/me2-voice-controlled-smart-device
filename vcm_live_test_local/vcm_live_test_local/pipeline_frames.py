"""Pipeline audio-frame memory, variable-length windows, and deadline helpers.

The ring buffer retains up to 20 seconds of one-second audio frames. Callers request
windows by sample count; model preprocessing still owns its fixed tensor contract.
"""
from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping
from typing import Any

import numpy as np

FRAME_MEMORY_SECONDS = 20
FRAME_WINDOW_FRAMES = 6

_GATE_DISPLAY = {"gateN": "G3", "gate4": "G4", "gate5": "G5"}


def append_second_frame(frame_mem: deque, frame: np.ndarray, frame_samples: int) -> None:
    """Store 1-second frames; front-pad short frame, append all full 1s frames without discarding audio."""
    data = np.asarray(frame, dtype=np.float32).reshape(-1)
    if data.size == 0:
        return  # no audio arrived this tick
    if data.size < frame_samples:
        data = np.concatenate([np.zeros(frame_samples - data.size, dtype=np.float32), data])
        frame_mem.append(data)
        return
    while data.size >= frame_samples:
        frame_mem.append(data[:frame_samples])
        data = data[frame_samples:]


def frame_window(frame_mem: deque, win_samples: int) -> np.ndarray | None:
    """Return the newest requested audio window; require enough whole frames."""
    if win_samples <= 0:
        raise ValueError("win_samples must be positive")
    frame_samples = frame_mem[-1].size if frame_mem else 0
    if frame_samples <= 0:
        return None
    required_frames = (win_samples + frame_samples - 1) // frame_samples
    if len(frame_mem) < required_frames:
        return None
    win = np.concatenate(list(frame_mem)[-required_frames:])
    if win.size > win_samples:
        return win[-win_samples:]
    if win.size < win_samples:
        return np.concatenate([np.zeros(win_samples - win.size, dtype=np.float32), win])
    return win


def advance_deadline(deadline: float, now: float, interval: float, grace: float = 0.05) -> tuple[float, int]:
    """Move a missed scheduled tick to the first future deadline; never queue catch-up work."""
    if interval <= 0:
        raise ValueError("interval must be positive")
    if now <= deadline + max(0.0, grace):
        return deadline, 0
    skipped = math.floor((now - deadline) / interval) + 1
    return deadline + skipped * interval, skipped


def pipe_path_steps(*, g1: Mapping[str, Any] | None, g2: Mapping[str, Any] | None,
                    spec: Mapping[str, Any] | None, action_gate: Mapping[str, Any] | None,
                    g2_ran: bool) -> list[dict[str, Any]]:
    """Ordered path steps actually taken this tick: G1 → G2 → G3/G4/G5 → ACTION."""
    steps: list[dict[str, Any]] = []
    if g1:
        steps.append({"gate": "G1",
                      "label": g1.get("activation_label") or g1.get("wake") or g1.get("label") or "—",
                      "conf": g1.get("activation_conf") if g1.get("active") else None,
                      "on": bool(g1.get("active"))})
    if g2_ran and g2:
        steps.append({"gate": "G2",
                      "label": g2.get("activation_intent") or g2.get("intent") or "—",
                      "conf": g2.get("activation_conf") if g2.get("active") else None,
                      "threshold": g2.get("threshold"),
                      "on": bool(g2.get("active"))})
    if spec and spec.get("label"):
        gate = _GATE_DISPLAY.get(str(spec.get("gate") or ""), str(spec.get("gate") or "").upper())
        steps.append({"gate": gate, "label": spec["label"], "conf": spec.get("conf"), "on": True})
    triggered = bool(action_gate and action_gate.get("triggered"))
    steps.append({"gate": "ACTION", "label": (action_gate or {}).get("intent") or "waiting",
                  "on": triggered, "light": triggered})
    return steps


def _conf_text(conf: Any) -> str:
    if isinstance(conf, (int, float)):
        return " " + str(round(float(conf) * 100)) + "%"
    return ""


def pipe_path_text(steps: list[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for step in steps:
        if step["gate"] == "ACTION":
            parts.append(("LIGHT ON: " + str(step.get("label") or "—")) if step.get("on") else "action idle")
        else:
            parts.append(str(step["gate"]) + " " + str(step.get("label") or "—") + _conf_text(step.get("conf")))
    return " → ".join(parts)
