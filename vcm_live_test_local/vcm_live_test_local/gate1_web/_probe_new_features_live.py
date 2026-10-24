"""Live WebSocket probe: verify interval options, skip_ticks toggle, and reset on running server."""
import asyncio
import json

import aiohttp
import numpy as np

SR = 16000


async def main():
    results = {}
    async with aiohttp.ClientSession() as session, session.ws_connect(
        "ws://localhost:8766/ws", max_msg_size=0
    ) as ws:
        await ws.send_json({"type": "mode", "mode": "both"})

        # Test 1: Change interval to 2s
        await ws.send_json({"type": "interval", "interval_s": 2})

        # Test 2: Enable skip_ticks
        await ws.send_json({"type": "skip_ticks", "enabled": True})

        # Test 3: Reset pipeline
        await ws.send_json({"type": "reset"})

        # Stream small audio
        async def send_audio():
            z = np.zeros(4096, dtype="<f4").tobytes()
            for _ in range(int(8 * SR / 4096)):
                await ws.send_bytes(z)
                await asyncio.sleep(4096 / SR)

        task = asyncio.create_task(send_audio())
        loop = asyncio.get_event_loop()
        end = loop.time() + 12

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

            mtype = data.get("type")
            if mtype == "interval":
                results["interval_ack"] = data
            elif mtype == "skip_ticks":
                results["skip_ticks_ack"] = data
            elif mtype == "reset":
                results["reset_ack"] = data
            elif mtype == "pipe" and "pipe_scheduler" not in results:
                sched = (data.get("memory") or {}).get("scheduler") or {}
                results["pipe_scheduler"] = sched
                if len(results) >= 4:
                    break

        task.cancel()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
