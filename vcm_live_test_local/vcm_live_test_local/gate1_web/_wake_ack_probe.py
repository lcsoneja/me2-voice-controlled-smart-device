#!/usr/bin/env python3
"""Live probe: does the pipe stream carry a wake_response for a real wake word?

Streams 16 kHz PCM into /ws in "both" mode (the dashboard's mode), plays a
synthetic wake clip the way the browser mic would, and reports every pipe
payload that carried wake_response - i.e. the shipped one-word wake reply.
Requires gate1_server.py to be running (default http://127.0.0.1:8765).

Run: py -3.12 gate1_web/_wake_ack_probe.py [Nova|Piattos] [g1-model]
"""

from __future__ import annotations

import asyncio
import json
import sys
import wave
from pathlib import Path

import aiohttp
import numpy as np

HERE = Path(__file__).resolve().parent
APP = HERE.parent
SR = 16000
CHUNK = SR // 10  # 100 ms frames, the server's expected stream granularity
CLIPS = {
    "Nova": "gate1_wake_nova_f01_pitchhigh_normal.wav",
    "Piattos": "gate1_wake_piattos_m01_pitchnorm_fast.wav",
}


def load_wake(persona: str) -> np.ndarray:
    path = APP / "synthetic_samples" / CLIPS[persona]
    with wave.open(str(path), "rb") as handle:
        assert handle.getframerate() == SR, path
        assert handle.getnchannels() == 1, path
        audio = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)
    # The dashboard streams float32 PCM in [-1, 1]; the server ingests "<f4".
    return (audio.astype(np.float32) / 32768.0).astype("<f4")


def script(persona: str) -> np.ndarray:
    """Silence, then two wake utterances, then silence for the trailing ticks."""
    wake = load_wake(persona)
    gap = np.zeros(SR // 2, dtype="<f4")
    silence = np.zeros(8 * SR, dtype="<f4")
    tail = np.zeros(6 * SR, dtype="<f4")
    return np.concatenate([silence, wake, gap, wake, gap, tail])


async def main() -> int:
    persona = sys.argv[1] if len(sys.argv) > 1 else "Nova"
    model = sys.argv[2] if len(sys.argv) > 2 else None
    audio = script(persona)
    acks: list[dict] = []
    stages: dict[str, int] = {}
    payloads = 0

    async with (
        aiohttp.ClientSession() as session,
        session.ws_connect("ws://127.0.0.1:8765/ws") as ws,
    ):
        await ws.send_json({"type": "mode", "mode": "both"})
        if model:
            await ws.send_json({"type": "model", "model": model})

        async def receiver() -> None:
            nonlocal payloads
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except (TypeError, json.JSONDecodeError):
                    continue
                if data.get("type") != "pipe":
                    continue
                payloads += 1
                stage = str(data.get("stage", ""))[:48]
                stages[stage] = stages.get(stage, 0) + 1
                if data.get("wake_response"):
                    acks.append(dict(data["wake_response"]))

        async def sender() -> None:
            for start in range(0, audio.shape[0], CHUNK):
                chunk = audio[start : start + CHUNK]
                if chunk.shape[0] < CHUNK:
                    chunk = np.pad(chunk, (0, CHUNK - chunk.shape[0]))
                await ws.send_bytes(chunk.tobytes())
                await asyncio.sleep(CHUNK / SR)

        recv = asyncio.create_task(receiver())
        await sender()
        await asyncio.sleep(1.0)
        recv.cancel()

    print(f"persona={persona} model={model or 'default'} pipe_payloads={payloads}")
    for stage, count in sorted(stages.items(), key=lambda item: -item[1]):
        print(f"  {count:3d} x {stage}")
    if not acks:
        print("RESULT: no wake_response emitted")
        return 1
    for ack in acks[:3]:
        print(f"RESULT: wake_response url={ack.get('url')} persona={ack.get('persona')} "
              f"text={ack.get('text')!r} event_id={ack.get('event_id')} "
              f"room_active={ack.get('room_active')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
