"""Noise-cancellation DSP shared by the live pipeline and the recording-lab replay.

Spectral-subtraction canceller with minimum-statistics noise-profile tracking
and an energy guard. This module has no project imports, so both gate1_server
(live ticker) and recording_lab (replay jobs) can use the identical functions —
a replay with the canceller on is bit-for-bit the same preprocessing as live.
"""

from __future__ import annotations

import numpy as np

_NC_STFT_N = 400
_NC_HOP = 160
_NC_WIN = None
_NC_BETA = 2.0
_NC_FLOOR = 0.08
_NC_EMA = 0.08
_NC_LEAK = 1.002
_NC_GUARD = 0.55


def _nc_window():
    global _NC_WIN
    if _NC_WIN is None:
        _NC_WIN = np.hanning(_NC_STFT_N).astype(np.float32)
    return _NC_WIN


def _nc_stft(x: np.ndarray):
    w = _nc_window()
    starts = np.arange(0, x.shape[0] - _NC_STFT_N + 1, _NC_HOP)
    idx = starts[:, None] + np.arange(_NC_STFT_N)[None, :]
    return np.fft.rfft(x[idx] * w[None, :], axis=1), starts


def _nc_noise_update(win: np.ndarray, nc: dict) -> None:
    """Track the noise magnitude profile with minimum statistics.

    Per frequency bin the profile follows the lowest magnitude seen recently,
    leaking upward slowly so a changing room is still tracked. Stationary hum
    and hiss are learned immediately after the switch is flipped, while speech
    only holds the floor down; _nc_apply's energy guard is the safety net that
    keeps over-subtraction from erasing a command.
    """
    x = np.asarray(win, dtype=np.float32)
    if x.shape[0] < _NC_STFT_N:
        return
    X, _ = _nc_stft(x)
    mag = np.abs(X)
    energy = (mag * mag).sum(axis=1)
    order = np.argsort(energy)
    keep = max(1, int(energy.shape[0] * 0.15))
    est = mag[order[:keep]].mean(axis=0)
    prev = nc.get("profile")
    nc["profile"] = est if prev is None else np.minimum(prev * _NC_LEAK, est * _NC_EMA + prev * (1.0 - _NC_EMA))
    nc["updates"] = int(nc.get("updates", 0)) + 1


def _nc_apply(win: np.ndarray, nc: dict) -> np.ndarray:
    """Phase-preserving spectral subtraction of the tracked noise profile."""
    profile = nc.get("profile")
    if not nc.get("enabled") or profile is None:
        return win
    x = np.asarray(win, dtype=np.float32)
    if x.shape[0] < _NC_STFT_N:
        return x
    w = _nc_window()
    X, starts = _nc_stft(x)
    mag = np.abs(X)
    clean = np.maximum(mag - _NC_BETA * profile[None, :], _NC_FLOOR * mag)
    Xc = X * (clean / np.maximum(mag, 1e-8))
    y = np.fft.irfft(Xc, n=_NC_STFT_N, axis=1) * w[None, :]
    out = np.zeros(x.shape[0], dtype=np.float32)
    norm = np.zeros(x.shape[0], dtype=np.float32)
    w2 = w * w
    for k, s in enumerate(starts):
        out[s:s + _NC_STFT_N] += y[k]
        norm[s:s + _NC_STFT_N] += w2
    covered = norm > 1e-6
    cleaned = np.where(covered, out / np.maximum(norm, 1e-8), x).astype(np.float32)
    # Safety guard: cancellation must never eat the command. If a sustained
    # sound was mistaken for noise the cleaned window loses too much energy,
    # so blend back toward the raw audio until the energy floor is respected.
    pre = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    post = float(np.sqrt(np.mean(cleaned.astype(np.float64) ** 2)))
    if pre > 1e-6 and post < _NC_GUARD * pre:
        for mix in (0.85, 0.70, 0.55, 0.40, 0.25, 0.10):
            cand = (cleaned * mix + x * (1.0 - mix)).astype(np.float32)
            if float(np.sqrt(np.mean(cand.astype(np.float64) ** 2))) >= _NC_GUARD * pre:
                return cand
        return x
    return cleaned
