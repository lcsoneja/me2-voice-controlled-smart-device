import asyncio
import json

import aiohttp
import numpy as np

SR = 16000


async def main():
    seen = []
    async with aiohttp.ClientSession() as session, session.ws_connect(
        "ws://localhost:8766/ws", max_msg_size=0
    ) as ws:
        await ws.send_json({"type": "mode", "mode": "both"})
        got = {}

        async def send():
            z = np.zeros(4096, dtype="<f4").tobytes()
            for _ in range(int(9 * SR / 4096)):
                await ws.send_bytes(z)
                await asyncio.sleep(4096 / SR)

        task = asyncio.create_task(send())
        loop = asyncio.get_event_loop()
        end = loop.time() + 16
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
                data = json.loads(msg.data)
            except (ValueError, TypeError):
                continue
            seen.append(data.get("type"))
            if data.get("type") == "pipe":
                mem = data.get("memory") or {}
                got = {
                    "scheduler": mem.get("scheduler"),
                    "mode": data.get("mode"),
                    "window_frames": mem.get("window_frames"),
                    "nc": mem.get("noise_canceller"),
                }
                break
        task.cancel()
        print(json.dumps({"got": got, "seen_types": seen[:12]}))


asyncio.run(main())
