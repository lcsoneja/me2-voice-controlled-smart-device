"""Live WebSocket test: Gate2 mode accepts a 2s inference interval per connection."""
import asyncio
import json
from datetime import datetime

import numpy as np
from aiohttp import ClientSession, ClientTimeout, WSMsgType


async def main():
    async with (
        ClientSession(timeout=ClientTimeout(total=20)) as session,
        session.ws_connect("http://127.0.0.1:8765/ws") as ws,
    ):
            await ws.send_json({"type": "mode", "mode": "gate2", "interval_s": 2})
            pcm = np.zeros(16000, dtype="<f4").tobytes()
            for _ in range(7):
                await ws.send_bytes(pcm)
            times = []
            while len(times) < 2:
                message = await ws.receive(timeout=12)
                if message.type != WSMsgType.TEXT:
                    continue
                payload = json.loads(message.data)
                if payload.get("type") == "probs2":
                    times.append(datetime.fromisoformat(payload["ts"]))
            delta = (times[1] - times[0]).total_seconds()
            if not 1.5 <= delta <= 2.5:
                raise AssertionError(f"expected ~2 seconds between inferences; got {delta:.3f}s")
            print(f"PASS: Gate2 inference cadence {delta:.3f}s; input window remains 5.92s")


if __name__ == "__main__":
    asyncio.run(main())
