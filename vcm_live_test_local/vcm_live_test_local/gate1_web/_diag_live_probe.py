"""Paced live-diag probe: stream a loud command at REALTIME pace for ~8 s so
the ticker scores it, then dump /api/diag. Verifies the live tick log path.

Run: py -3.12 gate1_web/_diag_live_probe.py
"""
import asyncio
import contextlib
import wave
from pathlib import Path

import aiohttp
import numpy as np

HERE = Path(__file__).resolve().parent
APP = HERE.parent
SR = 16000
BASE = "http://127.0.0.1:8765"
SAMPLES_DIR = APP / "synthetic_samples"


def load_clip(filename):
    """Load one synthetic WAV from the fixtures directory."""
    source = (SAMPLES_DIR / filename).resolve()
    if not source.is_relative_to(SAMPLES_DIR.resolve()):
        raise ValueError("clip outside samples dir")
    with wave.open(str(source), "rb") as handle:
        return np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


async def main():
    try:
        cmd = load_clip("gate2_PLAY_MUSIC_f02_pitchnorm_fast.wav")
    except (OSError, wave.Error) as exc:
        print("cannot load clip:", exc)
        return 2
    target = 8 * SR
    audio = np.zeros(target, dtype=np.float32)
    audio[1000:1000 + cmd.size] = cmd[:min(cmd.size, target - 1000)]
    audio[40000:40000 + cmd.size] = cmd[:min(cmd.size, target - 40000)]

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(BASE + "/ws") as ws:
            await ws.send_json({"type": "mode", "mode": "both"})
            chunk = SR // 10
            for i in range(0, audio.size, chunk):
                part = audio[i:i + chunk]
                if part.shape[0] < chunk:
                    part = np.pad(part, (0, chunk - part.shape[0]))
                await ws.send_bytes(part.astype("<f4").tobytes())
                await asyncio.sleep(0.1)
            for _ in range(6):
                with contextlib.suppress(TimeoutError, asyncio.TimeoutError):
                    msg = await asyncio.wait_for(ws.receive(), timeout=1.2)
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
        async with session.get(BASE + "/api/diag?last=12") as resp:
            lines = (await resp.json())["lines"]
    print("diag entries:", len(lines))
    for entry in lines[-8:]:
        kind = entry.get("kind")
        if kind == "tick":
            print(f"  tick tick={entry.get('tick')} eval={entry.get('eval_ms')}ms late={entry.get('late')} "
                  f"g1={entry.get('g1_label')} g1act={entry.get('g1_active')} "
                  f"g2={entry.get('g2_intent')} conf={entry.get('g2_conf')} trig={entry.get('triggered')}")
        elif kind == "tick_gated":
            print(f"  gated tick={entry.get('tick')} rms={entry.get('rms')} floor={entry.get('floor')}")
        elif kind == "tick_calib":
            print(f"  calib tick={entry.get('tick')} max={entry.get('calib_max')}")
        else:
            print(f"  {kind}: {entry}")
    ticks = [e for e in lines if str(e.get("kind", "")).startswith("tick")]
    print("LIVE-DIAG", "PASS" if ticks else "FAIL")
    return 0

raise SystemExit(asyncio.run(main()))
