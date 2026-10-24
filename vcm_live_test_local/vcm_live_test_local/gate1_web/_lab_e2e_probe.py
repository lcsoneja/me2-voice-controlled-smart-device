"""End-to-end recording-lab probe: stream 30 s over the live WS, capture it,
replay it through two Gate 2 models, and verify the saved result.

Run: py -3.12 gate1_web/_lab_e2e_probe.py   (server must be running on 8765)
"""

from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path

import aiohttp
import numpy as np

HERE = Path(__file__).resolve().parent
APP = HERE.parent
SR = 16000
BASE = "http://127.0.0.1:8765"


def clip(name: str) -> np.ndarray:
    with wave.open(str(APP / "synthetic_samples" / name), "rb") as handle:
        return np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


async def main() -> int:
    try:
        wake = clip("gate1_wake_nova_f01_pitchhigh_normal.wav")
        cmd = clip("gate2_PLAY_MUSIC_f02_pitchnorm_fast.wav")
    except (OSError, wave.Error) as exc:
        print("cannot load synthetic clip:", exc)
        return 2
    target = 30 * SR
    audio = np.concatenate([
        np.zeros(6 * SR, dtype=np.float32),
        wake, np.zeros(SR + SR // 2, dtype=np.float32),
        cmd, np.zeros(2 * SR, dtype=np.float32),
        wake, np.zeros(SR + SR // 2, dtype=np.float32),
        cmd,
    ])
    if audio.size < target:
        audio = np.concatenate([audio, np.zeros(target - audio.size, dtype=np.float32)])
    audio = audio[:target]

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(BASE + "/ws") as ws:
            await ws.send_json({"type": "mode", "mode": "both"})
            chunk = SR // 10
            for i in range(0, audio.size, chunk):
                part = audio[i:i + chunk]
                if part.shape[0] < chunk:
                    part = np.pad(part, (0, chunk - part.shape[0]))
                await ws.send_bytes(part.astype("<f4").tobytes())
                await asyncio.sleep(0.004)
            takes = []
            for take_no in (1, 2):
                # Repeatable saves: two clicks in one session, two distinct takes.
                await ws.send_json({"type": "save_capture", "label": "e2e-probe-" + str(take_no)})
                rec = None
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    try:
                        data = json.loads(msg.data)
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if data.get("type") == "capture_saved":
                        if data.get("error"):
                            print("CAPTURE ERROR:", data["error"])
                            return 1
                        rec = data["recording"]
                        break
                if rec is None:
                    print("no capture_saved reply")
                    return 1
                print("captured #" + str(take_no) + ":", rec["id"], rec["duration_s"], "s ->", rec["file"])
                takes.append(rec)
            rec = takes[0]

        models = ["gate2v21p", "gate2v46_impwarp"]
        async with session.post(BASE + f"/api/recordings/{rec['id']}/test", json={"models": models}) as resp:
            job = (await resp.json())["job"]
        print("job:", job["id"], "->", job["status"])
        while True:
            async with session.get(BASE + "/api/jobs/" + job["id"]) as resp:
                job = (await resp.json())["job"]
            if job["status"] in ("done", "error"):
                break
            await asyncio.sleep(1.0)
        print("job:", job["status"], "| elapsed", job["elapsed_s"], "s |", job["ticks_total"], "ticks")
        kinds: dict[str, int] = {}
        for event in job["events"]:
            kinds[event["kind"]] = kinds.get(event["kind"], 0) + 1
        print("event kinds:", kinds)
        for event in [e for e in job["events"] if e["kind"] == "g3"][:4]:
            print("  g3:", event["model"], "|", event["route"], "->", event["label"], event["conf"])
        for s in job["summaries"]:
            print("  summary:", s["model"], "triggers", s["trigger_ticks"], "top", s["top_intent"], "p95", s["p95_infer_ms"], "ms", s["error"] or "")
        async with session.get(BASE + "/api/recordings") as resp:
            all_recs = (await resp.json())["recordings"]
        listed = {r["id"] for r in all_recs}
        both_listed = all(t["id"] in listed for t in takes)
        print("recordings on disk:", len(all_recs), "| both captures listed:", both_listed)
        async with session.get(BASE + "/api/results") as resp:
            results = (await resp.json())["results"]
        saved = any(r["id"] == job["id"] for r in results)
        print("saved results:", len(results), "| this job persisted:", saved)
        ok = job["status"] == "done" and kinds.get("g1", 0) > 0 and saved and both_listed
        print("PROBE", "PASS" if ok else "FAIL")
        return 0 if ok else 1


raise SystemExit(asyncio.run(main()))
