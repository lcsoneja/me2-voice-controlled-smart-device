"""Parallel tail driver: remaining takes on the second server process.

The main driver keeps the critical me2w (wake+command) set on 8765; this one
replays everything else in parallel. me2h_* takes (no wake word) get the LEAN
matrix - one Gate 1 variant, architecture v1 only - because without a wake
their Gate 2 stats are identical across all 13 G1 variants, so the 13x
redundant scoring is pure waste. Everything else keeps the full matrix.
"""
import json
import pathlib
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8767"
HERE = pathlib.Path(__file__).resolve().parent
LOG = HERE / "_batch_all_demo_progress.log"
G1_ALL = ["gate1v12_f16", "gate1v8_f32", "gate1v8_f16", "gate1v10_f16", "gate1v10_dr",
          "gate1v5_f32", "gate1v5_f16", "gate1v2_f32", "gate1v2_f16",
          "gate1v3_f32", "gate1v3_f16", "gate1v4_f32", "gate1v4_f16"]
FULL = {"g1_models": G1_ALL, "models": "all", "hop_s": 1.0, "nc_modes": [False],
        "architectures": [0, 1], "workers": 0}
LEAN = {"g1_models": ["gate1v12_f16"], "models": "all", "hop_s": 1.0, "nc_modes": [False],
        "architectures": [0], "workers": 0}


def api(path, data=None, timeout=240):
    url = BASE + path
    if data is None:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    req = urllib.request.Request(url, json.dumps(data).encode("utf-8"),
                                 {"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main():
    done = set()
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and (" done " in line or " error " in line):
                done.add(parts[1])
    recs = api("/api/recordings")["recordings"]
    ids = [r["id"] for r in recs
           if r["id"] not in done and not r["id"].startswith("me2w_")]
    t0 = time.time()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"fast-tail-start base={BASE} remaining={len(ids)}\n")
    for n, rid in enumerate(ids, 1):
        payload = LEAN if rid.startswith("me2h_") else FULL
        try:
            d = api(f"/api/recordings/{rid}/test", payload)
            jid = d["job"]["id"]
        except Exception as exc:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(f"F{n}/{len(ids)} {rid} POST-ERROR {type(exc).__name__} {exc}\n")
            continue
        while True:
            try:
                j = api(f"/api/jobs/{jid}")["job"]
            except Exception:
                time.sleep(2.0)
                continue
            if j["status"] not in ("running", "queued"):
                break
            time.sleep(1.2)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"F{n}/{len(ids)} {rid} job={jid} {j['status']} elapsed={time.time()-t0:.0f}s "
                    f"lanes={len(j.get('summaries') or [])}\n")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"FAST-TAIL-DONE {len(ids)} takes total={time.time()-t0:.0f}s\n")


if __name__ == "__main__":
    main()
