"""Probe: live architecture option (v1/v2/v3) - Gate 2 must score in v1 and sleep in v2/v3 until wake."""
import asyncio
import json
import sys

import aiohttp
import numpy as np

SR = 16000
WS = "ws://127.0.0.1:8765/ws"


async def main():
    t = np.arange(0, 4096, dtype=np.float32)
    tone = (0.03 * np.sin(2 * np.pi * 260.0 * t / SR)).astype("<f4")
    async with aiohttp.ClientSession() as session, session.ws_connect(WS, max_msg_size=0) as ws:
        await ws.send_json({"type": "mode", "mode": "both"})

        async def send_tone():
            while True:
                await ws.send_bytes(tone.tobytes())
                await asyncio.sleep(4096 / SR)

        sender = asyncio.create_task(send_tone())

        async def collect(seconds):
            msgs = []
            loop = asyncio.get_event_loop()
            end = loop.time() + seconds
            while loop.time() < end:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=max(0.05, end - loop.time()))
                except TimeoutError:
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
                    continue
                try:
                    msgs.append(json.loads(msg.data))
                except (ValueError, TypeError):
                    continue
            return msgs

        def phase(name, msgs):
            pipes = [m for m in msgs if m.get("type") == "pipe"]
            g1_on = [m for m in pipes if (m.get("g1") or {}).get("active")]
            scored = [m for m in pipes if (m.get("g2") or {}).get("probs")]
            bad = [m for m in pipes if not (m.get("g1") or {}).get("active") and (m.get("g2") or {}).get("probs")]
            return {"name": name, "pipes": len(pipes), "g1_active_ticks": len(g1_on),
                    "g2_scored_ticks": len(scored), "bad_wakefree_scoring": len(bad)}

        await asyncio.sleep(7.0)  # fill the rolling window before judging

        results = []
        await ws.send_json({"type": "arch", "arch": 0})
        results.append(phase("v1", await collect(6)))
        await ws.send_json({"type": "arch", "arch": 1})
        results.append(phase("v2", await collect(6)))
        await ws.send_json({"type": "arch", "arch": 2})
        results.append(phase("v3", await collect(6)))

        await ws.send_json({"type": "g2model", "model": "gate2v67_timeshift_only"})
        msgs = await collect(8)
        acks = [m for m in msgs if m.get("type") == "g2model"]
        errors = [m for m in msgs if m.get("type") == "status" and "error" in str(m.get("text", "")).lower()]
        new_model = {"ack": acks[-1] if acks else None, "error": errors[-1] if errors else None}
        await ws.send_json({"type": "g2model", "model": "gate2v21p"})
        await collect(5)

        await ws.send_json({"type": "arch", "arch": 0})
        sender.cancel()
        print(json.dumps({"arch": results, "new_model": new_model}, indent=1))
        v1, v2, v3 = results
        ok = (v1["g2_scored_ticks"] > 0
              and v2["bad_wakefree_scoring"] == 0 and v2["pipes"] > 0
              and v3["bad_wakefree_scoring"] == 0 and v3["pipes"] > 0
              and new_model["ack"] is not None and new_model["error"] is None)
        print("PROBE:", "PASS" if ok else "FAIL")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
