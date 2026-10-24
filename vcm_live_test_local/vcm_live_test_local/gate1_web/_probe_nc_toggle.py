"""One-shot probe: toggle the noise-canceller switch on the live server and confirm acks."""
import asyncio
import json

import aiohttp
import numpy as np

SR = 16000


async def main():
    async with aiohttp.ClientSession() as session, session.ws_connect(
        "ws://localhost:8766/ws", max_msg_size=0
    ) as ws:
        await ws.send_json({"type": "mode", "mode": "both"})

        async def send():
            z = np.zeros(4096, dtype="<f4").tobytes()
            for _ in range(int(12 * SR / 4096)):
                await ws.send_bytes(z)
                await asyncio.sleep(4096 / SR)

        task = asyncio.create_task(send())
        await asyncio.sleep(1.0)
        await ws.send_json({"type": "noise_canceller", "enabled": True})
        ack = None
        last_nc = None
        loop = asyncio.get_event_loop()
        end = loop.time() + 14
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
            if data.get("type") == "noise_canceller":
                ack = data
            if data.get("type") == "pipe":
                last_nc = (data.get("memory") or {}).get("noise_canceller")
        task.cancel()
        print(json.dumps({"ack": ack, "last_nc": last_nc}))


asyncio.run(main())
