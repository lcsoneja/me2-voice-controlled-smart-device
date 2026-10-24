"""Live smoke test: switch every selectable Gate2 model and verify its pipe output shape.
This checks model loading/inference plumbing only; it is not an accuracy test.
"""
import asyncio
import json

import aiohttp
import numpy as np

MODELS = {
    "gate2v2": 19,
    "gate2v6_keras": 19,
    "gate2v16": 19,
    "gate2v18": 19,
    "gate2v19": 19,
    "gate2v19p": 19,
    "gate2v21": 20,
    "gate2v21p": 20,
    "gate2v22": 20,
    "gate2v22s": 20,
}
SAMPLE_RATE = 16000


async def main():
    results = []
    async with aiohttp.ClientSession() as session, session.ws_connect(
        "ws://127.0.0.1:8765/ws", max_msg_size=0
    ) as ws:
        await ws.send_json({"type": "mode", "mode": "both"})
        await ws.send_json({"type": "interval", "interval_s": 1})
        await ws.send_json({"type": "thr", "thr": {"Nova": 0.95, "Piattos": 0.95, "gate2MinConf": 0.95}})

        async def feed_noise():
            rng = np.random.default_rng(20261017)
            audio = rng.normal(0.0, 0.015, SAMPLE_RATE * 40).astype("<f4")
            for start in range(0, audio.size, 4096):
                await ws.send_bytes(audio[start:start + 4096].tobytes())
                await asyncio.sleep(4096 / SAMPLE_RATE)

        feeder = asyncio.create_task(feed_noise())
        loop = asyncio.get_running_loop()
        for model, expected_outputs in MODELS.items():
            await ws.send_json({"type": "g2model", "model": model})
            acknowledged = False
            observed = None
            error = None
            deadline = loop.time() + 25
            while loop.time() < deadline:
                try:
                    message = await asyncio.wait_for(ws.receive(), timeout=3.0)
                except TimeoutError:
                    continue
                if message.type != aiohttp.WSMsgType.TEXT:
                    if message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        error = "websocket closed"
                        break
                    continue
                try:
                    data = json.loads(message.data)
                except (ValueError, TypeError):
                    continue
                if data.get("type") == "status" and "model error" in data.get("text", ""):
                    error = data["text"]
                elif data.get("type") == "g2model" and data.get("model") == model:
                    acknowledged = True
                elif data.get("type") == "pipe":
                    g2 = data.get("g2") or {}
                    if g2.get("model") == model:
                        probs = g2.get("probs") or []
                        observed = len(probs)
                        if observed == expected_outputs:
                            break
                if error:
                    break
            ok = acknowledged and observed == expected_outputs and not error
            results.append({"model": model, "ack": acknowledged, "outputs": observed, "expected": expected_outputs, "ok": ok, "error": error})
            print(json.dumps(results[-1]))

        await ws.send_json({"type": "g2model", "model": "gate2v21p"})
        await ws.send_json({"type": "reset"})
        feeder.cancel()
    failed = [item for item in results if not item["ok"]]
    print(json.dumps({"summary": f"{len(results) - len(failed)}/{len(results)} smoke checks passed", "failed": failed}))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
