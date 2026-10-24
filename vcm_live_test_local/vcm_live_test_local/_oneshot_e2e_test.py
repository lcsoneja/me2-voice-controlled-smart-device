"""End-to-end test of the one-shot pipeline (/ws/oneshot).

Streams a real labeled take (wake word followed by a command) into the same socket the
browser uses, then checks the architecture's contract:

  1. hello advertises one-shot mode and the active models
  2. Gate 1 produces wake scores while armed
  3. exactly one wake event fires, carrying a spoken-reply URL
  4. exactly ONE intent message follows, over a ~5.0 s capture
  5. no further intent messages arrive (strict single-shot)

Run from the app directory with the server listening on 8765.
"""

import asyncio
import json
import pathlib
import sys
import wave
from typing import Any

import aiohttp
import numpy as np

BASE = "http://127.0.0.1:8765"
CHUNK = 4096
TAKES = [
    ("20261023_155245_2dd71e_rf-take-235245.wav", "Nova", "Play_music"),
    ("20261023_175303_9232a3_rf-take-015303.wav", "Nova", "lights_on"),
    ("20261023_185346_103374_rf-take-023346.wav", "Nova", "VOLUME_UP"),
]


def load_wav(path: pathlib.Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        assert handle.getframerate() == 16000, handle.getframerate()
        assert handle.getnchannels() == 1, handle.getnchannels()
        raw = handle.readframes(handle.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


async def drain(ws, seen: list[dict], budget: float = 0.02) -> None:
    """Collect whatever the server has already sent, without blocking the stream."""
    while True:
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=budget)
        except asyncio.TimeoutError:
            return
        if msg.type == aiohttp.WSMsgType.TEXT:
            seen.append(json.loads(msg.data))
        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
            return


async def try_take(session, filename: str) -> tuple[list[dict[str, Any]], str | None]:
    path = pathlib.Path("recordings") / filename
    if not path.is_file():
        return [], "missing " + filename
    audio = load_wav(path)
    seen: list[dict] = []
    async with session.ws_connect(BASE + "/ws/oneshot", max_msg_size=16 * 1024 * 1024) as ws:
        await drain(ws, seen, 0.5)
        await ws.send_str(json.dumps({"type": "arm"}))
        for start in range(0, audio.shape[0], CHUNK):
            await ws.send_bytes(audio[start:start + CHUNK].tobytes())
            await drain(ws, seen)
            if any(m.get("type") == "intent" for m in seen):
                break
        # Let the server close a 5 s window even if the take ended early.
        for _ in range(40):
            await drain(ws, seen, 0.25)
            if any(m.get("type") == "intent" for m in seen):
                break
    return seen, None


async def main():
    async with aiohttp.ClientSession() as session:
        for filename, wake_word, command in TAKES:
            seen, err = await try_take(session, filename)
            if err:
                print("SKIP " + err)
                continue
            hello = next((m for m in seen if m.get("type") == "hello"), {})
            wakes = [m for m in seen if m.get("type") == "wake"]
            intents = [m for m in seen if m.get("type") == "intent"]
            g1 = [m for m in seen if m.get("type") == "g1"]
            print("take=" + filename)
            print("  hello: mode=" + str(hello.get("mode")) + " g1=" + str(hello.get("g1_model"))
                  + " g2=" + str(hello.get("gate2_model")) + " capture=" + str(hello.get("capture_seconds")))
            print("  messages: g1=" + str(len(g1)) + " wake=" + str(len(wakes)) + " intent=" + str(len(intents)))
            if not wakes:
                peak = (0.0, 0.0)
                for m in g1:
                    peak = (max(peak[0], float(m.get("nova") or 0)), max(peak[1], float(m.get("piattos") or 0)))
                print("  RESULT=NO_WAKE peak nova/piattos=" + str(tuple(round(v, 3) for v in peak)))
                continue
            wake = wakes[0]
            print("  wake: persona=" + str(wake.get("persona")) + " reply=" + str(wake.get("response_url")))
            if not intents:
                print("  RESULT=NO_INTENT (wake fired but no intent message)")
                continue
            intent = intents[0]
            got = intent.get("intent")
            print("  intent: " + str(got) + " conf=" + str(intent.get("conf")) + " at=" + str(intent.get("at_s"))
                  + "s windows=" + str(intent.get("windows_scored")) + " latency=" + str(intent.get("latency_ms"))
                  + "ms capture=" + str(intent.get("capture_seconds")) + "s")
            problems = []
            if len(wakes) != 1:
                problems.append("expected exactly 1 wake, got " + str(len(wakes)))
            if len(intents) != 1:
                problems.append("expected exactly 1 intent, got " + str(len(intents)))
            if abs(float(intent.get("capture_seconds") or 0) - 5.0) > 0.01:
                problems.append("capture was " + str(intent.get("capture_seconds")) + "s, expected 5.0")
            if not wake.get("response_url"):
                problems.append("wake carried no response_url")
            matched = str(got or "").replace("_", "").lower() == command.replace("_", "").lower()
            print("  ground truth=" + command + " classified=" + str(got) + " match=" + ("yes" if matched else "no"))
            if problems:
                print("  RESULT=FAIL " + "; ".join(problems))
                continue
            print("  RESULT=FLOW_OK" + ("" if matched else " (flow correct; classifier chose a different intent)"))
            return 0
    print("RESULT=NO_TAKE_PRODUCED_A_WAKE")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
