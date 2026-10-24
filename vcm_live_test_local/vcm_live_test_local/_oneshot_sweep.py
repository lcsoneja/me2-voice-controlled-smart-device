"""Characterise the one-shot architecture over several labeled takes.

Streams each take into /ws/oneshot exactly as the browser does, then reports the wake
persona it fired on, the single intent it decided, and whether that intent matches the
take's recorded action. Flow correctness (does the architecture behave as designed) is kept
separate from classifier accuracy (how often the single decision is right).

Two details matter for honesty:
  * intent names and labels differ in word order (PLAY_MUSIC vs music_play), so comparison
    reuses the same bag-of-words + alias matching the project's own analyser uses.
  * a live microphone never stops, but a file does. A taken that ends shortly after the wake
    word would never accumulate a full 5 s capture, so each take is followed by silence to
    emulate an open mic.
"""

import asyncio
import json
import pathlib
import re
import sys
import wave

import aiohttp
import numpy as np

BASE = "http://127.0.0.1:8765"
MODEL = sys.argv[1] if len(sys.argv) > 1 else ""
CHUNK = 4096
LIMIT = 6
TAIL_SAMPLES = 96000  # 6.0 s at 16 kHz, emulating an open microphone after the take

RFZ_ALIAS = {
    "settimer": "timer",
    "alarmset": "alarm",
    "tempup": "temperature",
    "tempdown": "temperature",
    "lightsdim": "brightness",
    "lightsbright": "brightness",
    "lightson": "lighton",
    "lightsoff": "lightoff",
    "reminderset": "createreminder",
    "remindercheck": "listreminders",
    "checkreminders": "listreminders",
    "mediaplay": "playmusic",
    "mediapause": "pause",
    "medianext": "next",
    "silence": "stop",
}


def bag(value: object) -> str:
    parts = re.split(r"[^a-z]+", str(value or "").lower())
    return "".join(sorted(p for p in parts if p))


def same_command(a: object, b: object) -> bool:
    if not str(b or "").strip():
        return False
    left, right = bag(a), bag(b)
    return RFZ_ALIAS.get(left, left) == RFZ_ALIAS.get(right, right)


def load_wav(path: pathlib.Path) -> np.ndarray:
    try:
        with wave.open(str(path), "rb") as handle:
            raw = handle.readframes(handle.getnframes())
    except (OSError, wave.Error) as exc:
        raise SystemExit(
            "cannot read " + str(path) + ": " + type(exc).__name__
        ) from exc
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def load_index() -> list[dict]:
    path = pathlib.Path("recordings/index.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(
            "cannot read " + str(path) + ": " + type(exc).__name__
        ) from exc
    return data["recordings"] if isinstance(data, dict) else data


async def drain(ws, seen: list[dict], budget: float = 0.02) -> None:
    while True:
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=budget)
        except TimeoutError:
            return
        if msg.type == aiohttp.WSMsgType.TEXT:
            try:
                seen.append(json.loads(msg.data))
            except ValueError:
                continue  # ignore a malformed frame rather than killing the stream
        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
            return


async def run_take(session, path: pathlib.Path) -> dict:
    audio = load_wav(path)
    tail = np.zeros(TAIL_SAMPLES, dtype=np.float32)
    seen: list[dict] = []
    async with session.ws_connect(
        BASE + "/ws/oneshot", max_msg_size=16 * 1024 * 1024
    ) as ws:
        await drain(ws, seen, 0.4)
        if MODEL:
            await ws.send_str(json.dumps({"type": "gate2_model", "model": MODEL}))
            await drain(ws, seen, 0.3)
        await ws.send_str(json.dumps({"type": "arm"}))
        for block in (audio, tail):
            for start in range(0, block.shape[0], CHUNK):
                await ws.send_bytes(block[start : start + CHUNK].tobytes())
                await drain(ws, seen)
                if any(m.get("type") == "intent" for m in seen):
                    break
        for _ in range(30):
            if any(m.get("type") == "intent" for m in seen):
                break
            await drain(ws, seen, 0.2)
    wakes = [m for m in seen if m.get("type") == "wake"]
    intents = [m for m in seen if m.get("type") == "intent"]
    return {
        "wakes": len(wakes),
        "intents": len(intents),
        "persona": wakes[0].get("persona") if wakes else None,
        "intent": intents[0].get("intent") if intents else None,
        "conf": intents[0].get("conf") if intents else None,
        "capture": intents[0].get("capture_seconds") if intents else None,
        "windows": intents[0].get("windows_scored") if intents else None,
        "latency": intents[0].get("latency_ms") if intents else None,
    }


async def main() -> int:
    recs = load_index()
    takes = [
        r
        for r in recs
        if str(r.get("wake_word") or "").strip()
        and str(r.get("action") or "").strip()
        and (pathlib.Path("recordings") / str(r.get("file"))).is_file()
    ]
    print("candidate takes=" + str(len(takes)))
    wake_hits = wake_ok = intent_ok = flow_ok = 0
    async with aiohttp.ClientSession() as session:
        for rec in takes[:LIMIT]:
            got = await run_take(session, pathlib.Path("recordings") / str(rec["file"]))
            persona_ok = (
                str(got["persona"] or "").strip().lower()
                == str(rec.get("wake_word") or "").strip().lower()
            )
            match = same_command(got["intent"], rec.get("action"))
            single = got["wakes"] == 1 and got["intents"] == 1
            wake_hits += 1 if got["wakes"] else 0
            wake_ok += 1 if persona_ok else 0
            intent_ok += 1 if match else 0
            flow_ok += 1 if single else 0
            print(
                "  "
                + str(rec["id"])[:20]
                + " | wake exp="
                + str(rec.get("wake_word"))
                + " got="
                + str(got["persona"])
                + (" ok" if persona_ok else " NO")
                + " | action exp="
                + str(rec.get("action"))
                + " intent="
                + str(got["intent"])
                + " conf="
                + str(got["conf"])
                + (" ok" if match else " NO")
                + " | wakes="
                + str(got["wakes"])
                + " intents="
                + str(got["intents"])
                + " capture="
                + str(got["capture"])
                + "s win="
                + str(got["windows"])
                + " "
                + str(got["latency"])
                + "ms"
            )
    n = min(LIMIT, len(takes))
    print(
        "SUMMARY takes="
        + str(n)
        + " wakes_fired="
        + str(wake_hits)
        + "/"
        + str(n)
        + " persona_ok="
        + str(wake_ok)
        + " semantic_intent_ok="
        + str(intent_ok)
        + " single_shot_flow_ok="
        + str(flow_ok)
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
