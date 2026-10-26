from __future__ import annotations
import json, math, subprocess, time, wave
from collections import deque
from pathlib import Path
import numpy as np

ROOT = Path("C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b")
HERE = ROOT / "vcm_live_test_local" / "vcm_live_test_local"
NOISE_DIR = ROOT / "Shipping" / "10randomMicSilentRecordings"
VOICE_DIR = ROOT / "Shipping" / "real_voice_owner" / "audio"
OUT = HERE / "research_reports" / "_nc_bench_scratch" / "results.json"
SR = 16000
WIN = int(5.92 * SR)
FRAME = SR
_NC_STFT_N = 400
_NC_HOP = 160
_NC_BETA = 2.0
_NC_FLOOR = 0.08
_NC_EMA = 0.08
_NC_LEAK = 1.002
_NC_GUARD = 0.55
_NC_WIN = np.hanning(_NC_STFT_N).astype(np.float32)


def _nc_stft(x):
    starts = np.arange(0, x.shape[0] - _NC_STFT_N + 1, _NC_HOP)
    idx = starts[:, None] + np.arange(_NC_STFT_N)[None, :]
    return (np.fft.rfft(x[idx] * _NC_WIN[None, :], axis=1), starts)


def _nc_noise_update(win, nc):
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
    nc["profile"] = (
        est
        if prev is None
        else np.minimum(prev * _NC_LEAK, est * _NC_EMA + prev * (1.0 - _NC_EMA))
    )
    nc["updates"] = int(nc.get("updates", 0)) + 1


def _nc_apply(win, nc):
    profile = nc.get("profile")
    if not nc.get("enabled") or profile is None:
        return win
    x = np.asarray(win, dtype=np.float32)
    if x.shape[0] < _NC_STFT_N:
        return x
    X, starts = _nc_stft(x)
    mag = np.abs(X)
    clean = np.maximum(mag - _NC_BETA * profile[None, :], _NC_FLOOR * mag)
    Xc = X * (clean / np.maximum(mag, 1e-08))
    y = np.fft.irfft(Xc, n=_NC_STFT_N, axis=1) * _NC_WIN[None, :]
    out = np.zeros(x.shape[0], dtype=np.float32)
    norm = np.zeros(x.shape[0], dtype=np.float32)
    w2 = _NC_WIN * _NC_WIN
    for k, s in enumerate(starts):
        out[s : s + _NC_STFT_N] += y[k]
        norm[s : s + _NC_STFT_N] += w2
    covered = norm > 1e-06
    cleaned = np.where(covered, out / np.maximum(norm, 1e-08), x).astype(np.float32)
    pre = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    post = float(np.sqrt(np.mean(cleaned.astype(np.float64) ** 2)))
    if pre > 1e-06 and post < _NC_GUARD * pre:
        nc["guard_trips"] = int(nc.get("guard_trips", 0)) + 1
        for mix in (0.85, 0.7, 0.55, 0.4, 0.25, 0.1):
            cand = (cleaned * mix + x * (1.0 - mix)).astype(np.float32)
            if float(np.sqrt(np.mean(cand.astype(np.float64) ** 2))) >= _NC_GUARD * pre:
                return cand
        return x
    return cleaned


def _wiener(win, profile):
    x = np.asarray(win, dtype=np.float32)
    if profile is None or x.size < _NC_STFT_N:
        return x
    X, starts = _nc_stft(x)
    mag = np.abs(X)
    gain = np.maximum(
        _NC_FLOOR, mag * mag / (mag * mag + _NC_BETA * profile[None, :] ** 2 + 1e-12)
    )
    Xc = X * gain
    y = np.fft.irfft(Xc, n=_NC_STFT_N, axis=1) * _NC_WIN[None, :]
    out = np.zeros(x.size, dtype=np.float32)
    norm = np.zeros(x.size, dtype=np.float32)
    w2 = _NC_WIN * _NC_WIN
    for k, s in enumerate(starts):
        out[s : s + _NC_STFT_N] += y[k]
        norm[s : s + _NC_STFT_N] += w2
    return np.where(norm > 1e-06, out / np.maximum(norm, 1e-08), x).astype(np.float32)


def _track_ambient(amb, wrms):
    ambient = sorted(amb)[max(0, len(amb) // 10)] if amb else 0.0
    floor = max(0.005, 2.5 * ambient)
    if wrms < floor:
        amb.append(wrms)
    return floor


def _ambient_gate(x, floor):
    rms = float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2)))
    gain = float(np.clip((rms - floor) / max(floor, 1e-12), 0.0, 1.0))
    return np.asarray(x, dtype=np.float32) * gain


def _hum_filter(x):
    x = np.asarray(x, dtype=np.float32)
    n = x.size
    if n != SR:
        x = np.pad(x[:SR], (0, max(0, SR - min(n, SR))))
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(SR, 1.0 / SR)
    keep = f >= 30.0
    for base in (50.0, 60.0):
        for harmonic in range(1, int(800 // base) + 1):
            keep &= np.abs(f - base * harmonic) > 1.0
    X[~keep] = 0
    return np.fft.irfft(X, n=SR).astype(np.float32)[:n]


def rms(x):
    return (
        float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2))) if len(x) else 0.0
    )


def db_ratio(a, b):
    return 20.0 * math.log10(max(float(a), 1e-15) / max(float(b), 1e-15))


def pad_window(x):
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    return np.pad(x[-WIN:], (max(0, WIN - min(WIN, x.size)), 0))[-WIN:]


def read_wav(p):
    with wave.open(str(p), "rb") as w:
        ch, sw, sr, n = (
            w.getnchannels(),
            w.getsampwidth(),
            w.getframerate(),
            w.getnframes(),
        )
        raw = w.readframes(n)
    if sw == 2:
        a = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif sw == 4:
        a = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
    elif sw == 1:
        a = (np.frombuffer(raw, "u1").astype(np.float32) - 128) / 128
    else:
        raise ValueError(f"Unsupported PCM width {sw}: {p}")
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        raise ValueError(f"Expected 16kHz WAV, got {sr}: {p}")
    return a.astype(np.float32)


def read_m4a(p):
    raw = subprocess.run(
        [
            "C:/ffmpeg/bin/ffmpeg.exe",
            "-v",
            "error",
            "-i",
            str(p),
            "-f",
            "f32le",
            "-ac",
            "1",
            "-ar",
            str(SR),
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype="<f4").copy()


def rolling(waveform):
    buf = np.zeros(0, dtype=np.float32)
    wins = []
    for start in range(0, len(waveform), FRAME):
        buf = np.concatenate((buf, waveform[start : start + FRAME]))[-20 * SR :]
        if buf.size >= WIN:
            wins.append(buf[-WIN:])
    return wins


def profile_stream(wins):
    st = {"profile": None, "updates": 0, "enabled": True}
    for w in wins:
        _nc_noise_update(w, st)
    return st


def _timed_spectral_tick(x, profile):
    state = {"profile": np.array(profile, copy=True), "enabled": True}
    _nc_noise_update(x, state)
    return _nc_apply(x, state)


def _timed_wiener_tick(x, profile):
    state = {"profile": np.array(profile, copy=True), "enabled": True}
    _nc_noise_update(x, state)
    return _wiener(x, state["profile"])


def infer_time(f, n=20):
    x = np.random.default_rng(445566).normal(0, 0.03, WIN).astype(np.float32)
    prof = np.ones(_NC_STFT_N // 2 + 1, dtype=np.float64) * 0.3
    for _ in range(3):
        f(x, prof)
    vals = []
    for _ in range(n):
        t = time.perf_counter()
        f(x, prof)
        vals.append((time.perf_counter() - t) * 1000)
    return float(np.median(vals))


def main():
    voices = sorted(VOICE_DIR.glob("*.wav"))
    if len(voices) != 150:
        raise RuntimeError(f"expected 150 voice WAVs, found {len(voices)}")
    owner = [read_wav(p) for p in voices]
    owner_rms = [rms(x) for x in owner]
    voice_ref = float(np.median(owner_rms))
    silences = sorted(NOISE_DIR.glob("*.m4a"))
    if len(silences) != 8:
        raise RuntimeError(f"expected 8 real mic recordings, found {len(silences)}")
    real = [read_m4a(p) for p in silences]
    profile_state = {"profile": None, "updates": 0}
    real_window_map = []
    ambient_state = deque(maxlen=30)
    ambient_floor = 0.005
    for noise in real:
        wins = rolling(noise)
        if not wins:
            repeats = int(np.ceil(WIN / max(len(noise), 1)))
            wins = [np.tile(noise, repeats)[:WIN].astype(np.float32)]
        real_window_map.append(wins)
        for w in wins:
            _nc_noise_update(w, profile_state)
            ambient_floor = _track_ambient(ambient_state, rms(w[-SR:]))
    shared_profile = profile_state["profile"]
    if shared_profile is None:
        raise RuntimeError("no profile learned from real noise")
    noise_stats = {
        k: [] for k in ("spectral_subtraction", "wiener", "ambient_gate", "hum_notch")
    }
    guard_frames = guard_total = 0
    for wins in real_window_map:
        st = {"profile": None, "updates": 0, "enabled": True}
        amb = deque(maxlen=30)
        for w in wins:
            _nc_noise_update(w, st)
            old_guard_trips = int(st.get("guard_trips", 0))
            outa = _nc_apply(w, st)
            outb = _wiener(w, st["profile"])
            floor = _track_ambient(amb, rms(w[-SR:]))
            outc = _ambient_gate(w[-SR:], floor)
            outd = _hum_filter(w[-SR:])
            noise_stats["spectral_subtraction"].append((rms(w), rms(outa)))
            noise_stats["wiener"].append((rms(w), rms(outb)))
            noise_stats["ambient_gate"].append((rms(w[-SR:]), rms(outc)))
            noise_stats["hum_notch"].append((rms(w[-SR:]), rms(outd)))
            guard_total += 1
            guard_frames += int(st.get("guard_trips", 0)) - old_guard_trips
    retention = {
        k: [] for k in ("spectral_subtraction", "wiener", "ambient_gate", "hum_notch")
    }
    for x in owner:
        w = pad_window(x)
        a = _nc_apply(w, {"enabled": True, "profile": shared_profile})
        b = _wiener(w, shared_profile)
        c = np.zeros_like(x)
        for st0 in range(0, len(x), SR):
            xx = x[st0 : st0 + SR]
            frame = np.pad(xx, (0, SR - len(xx))) if len(xx) < SR else xx
            c[st0 : st0 + len(xx)] = _ambient_gate(frame, ambient_floor)[: len(xx)]
        d = np.zeros_like(x)
        for st0 in range(0, len(x), SR):
            xx = x[st0 : st0 + SR]
            z = _hum_filter(xx)
            d[st0 : st0 + len(xx)] = z[: len(xx)]
        sl = slice(WIN - len(x), WIN) if len(x) <= WIN else slice(0, len(x))
        retention["spectral_subtraction"].append(rms(a[sl]) / max(rms(x), 1e-12))
        retention["wiener"].append(rms(b[sl]) / max(rms(x), 1e-12))
        retention["ambient_gate"].append(rms(c) / max(rms(x), 1e-12))
        retention["hum_notch"].append(rms(d) / max(rms(x), 1e-12))
    tone = (
        voice_ref * np.sqrt(2) * np.sin(2 * np.pi * 900 * np.arange(WIN) / SR)
    ).astype(np.float32)
    tone_in = rms(tone)
    tone_out = {
        "spectral_subtraction": rms(
            _nc_apply(tone, {"enabled": True, "profile": shared_profile})
        )
        / tone_in,
        "wiener": rms(_wiener(tone, shared_profile)) / tone_in,
        "ambient_gate": rms(_ambient_gate(tone, ambient_floor)) / tone_in,
        "hum_notch": rms(_hum_filter(tone[-SR:])) / tone_in,
    }
    synth_snr = {str(snr): {} for snr in (0, 5, 10, 20)}
    synth_seeds = {}
    t = np.arange(WIN, dtype=np.float64) / SR
    for snr in (0, 5, 10, 20):
        seed = 20261017 + snr
        synth_seeds[str(snr)] = seed
        rng = np.random.default_rng(seed)
        base = rng.normal(0, 1, WIN)
        hum = (
            np.sin(2 * np.pi * 50 * t)
            + 0.6 * np.sin(2 * np.pi * 100 * t)
            + 0.4 * np.sin(2 * np.pi * 60 * t)
            + 0.25 * np.sin(2 * np.pi * 120 * t)
        )
        raw = hum + 0.35 * base
        scale = voice_ref / (10 ** (snr / 20) * rms(raw))
        noise = (raw * scale).astype(np.float32)
        wins = [noise] * 7
        st = profile_stream(wins)
        prof = st["profile"]
        outs = {
            "spectral_subtraction": _nc_apply(noise, st),
            "wiener": _wiener(noise, prof),
            "ambient_gate": _ambient_gate(noise, ambient_floor),
            "hum_notch": _hum_filter(noise[-SR:]),
        }
        for name, out in outs.items():
            synth_snr[str(snr)][name] = round(db_ratio(rms(noise), rms(out)), 4)
    timings = {
        "spectral_subtraction_ms": infer_time(_timed_spectral_tick),
        "wiener_ms": infer_time(_timed_wiener_tick),
        "ambient_gate_ms": infer_time(
            lambda x, p: _ambient_gate(x[-SR:], ambient_floor)
        ),
        "hum_notch_ms": infer_time(lambda x, p: _hum_filter(x[-SR:])),
    }
    noise_db = {}
    for name, pairs in noise_stats.items():
        noise_db[name] = round(float(np.median([db_ratio(i, o) for i, o in pairs])), 4)
    summary = {}
    for name, vals in retention.items():
        a = np.asarray(vals, dtype=float)
        summary[name] = {
            "median": round(float(np.median(a)), 5),
            "p10": round(float(np.percentile(a, 10)), 5),
            "tone900": round(float(tone_out[name]), 5),
        }
    result = {
        "files": {
            "owner_wav_count": len(owner),
            "owner_duration_seconds_median": round(
                float(np.median([len(x) / SR for x in owner])), 5
            ),
            "owner_duration_seconds_max": round(
                float(max(len(x) / SR for x in owner)), 5
            ),
            "manifest_csv": str(ROOT / "Shipping/real_voice_owner/manifest_150.csv"),
            "voice_dir": str(VOICE_DIR),
            "real_noise_count": len(real),
            "real_noise_files": [str(p) for p in silences],
            "real_noise_format": "M4A decoded locally with C:/ffmpeg/bin/ffmpeg.exe to mono float32 16kHz; processing itself NumPy-only",
            "real_noise_seconds": [round(len(x) / SR, 3) for x in real],
        },
        "protocol": {
            "sample_rate_hz": SR,
            "frame_seconds": 1,
            "ring_seconds": 20,
            "eval_window_seconds": WIN / SR,
            "eval_window_samples": WIN,
            "noise_profile_updates": int(profile_state["updates"]),
            "ambient_floor_owner_test": round(ambient_floor, 8),
            "ambient_floor_update_count": int(sum(len(ws) for ws in real_window_map)),
            "short_silence_handling": "Records shorter than 5.92s are tiled to one full evaluation window for stationary-noise assessment; longer files are evaluated on trailing windows after the ring fills.",
            "ambient_floor_note": "Exact _track_ambient rule simulated over the 8 real silent streams, updating on each 1 Hz evaluation using newest one-second RMS. Final floor is reused for owner WAVs and synthetic tests; per-frame soft gate ramps from zero at floor to unity at 2x floor.",
            "synthetic_snr_db": [0, 5, 10, 20],
            "synthetic_seeds": synth_seeds,
            "synthetic_snr_reference_median_owner_rms": voice_ref,
            "synthetic_recipe": "50/100/60/120 Hz sinusoids + seeded white hiss (0.35 amplitude before scaling); each noise RMS set to median owner WAV RMS / 10^(SNR/20). Noise-only attenuation; not mixed speech recognition testing.",
            "owner_profile": "Shared A/B profile adapted across all 8 real noise-only recordings, then frozen while processing each owner WAV.",
        },
        "metrics": {
            "real_noise_median_attenuation_db": noise_db,
            "synthetic_noise_attenuation_db_by_snr": synth_snr,
            "owner_rms_retention": summary,
            "spectral_guard_trip_fraction": round(
                guard_frames / max(guard_total, 1), 5
            ),
            "spectral_guard_frames": guard_frames,
            "spectral_guard_total": guard_total,
            "local_cpu_median_ms_per_eval": timings,
            "pi5_estimate_ms_per_eval_assuming_4x_local": {
                k: round(v * 4, 4) for k, v in timings.items()
            },
        },
        "implementation_complexity_estimate_lines": {
            "spectral_subtraction": "~65 (ported helper/profile + guard)",
            "wiener": "~30 additional (shared profile and STFT/OLA)",
            "ambient_gate": "~15",
            "hum_notch": "~20",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
