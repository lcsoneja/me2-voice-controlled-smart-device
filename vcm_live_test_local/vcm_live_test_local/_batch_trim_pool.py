"""Trimmed-pool tail driver: only the competitive lanes (from the 154-take ranking).

The full matrix already measured every lane on 154 takes; the losers keep that
ranking. The remaining takes run the POOL matrix (top Gate 1 variants x top
Gate 2 models + reject/owner specialists, raw, v1+v2) so the leaders get full
202-take data ~6x faster. me2h (no wake) runs lean on the winner's G1 variant.
"""

import json
import pathlib
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
HERE = pathlib.Path(__file__).resolve().parent
LOG = HERE / "_batch_all_demo_progress.log"
POOL = json.loads((HERE / "_trim_pool.json").read_text(encoding="utf-8"))
POOL_PAYLOAD = {
    "g1_models": POOL["g1"],
    "models": POOL["g2"],
    "hop_s": 1.0,
    "nc_modes": [False],
    "architectures": [0, 1],
    "workers": 0,
}
LEAN_PAYLOAD = {
    "g1_models": [POOL["g1"][0]],
    "models": POOL["g2"],
    "hop_s": 1.0,
    "nc_modes": [False],
    "architectures": [0],
    "workers": 0,
}


def api(path, data=None, timeout=240):
    url = BASE + path
    if data is None:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    req = urllib.request.Request(
        url,
        json.dumps(data).encode("utf-8"),
        {"Content-Type": "application/json"},
        method="POST",
    )
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
    ids = [r["id"] for r in recs if r["id"] not in done]
    t0 = time.time()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(
            f"trim-pool-start remaining={len(ids)} pool_g1={len(POOL['g1'])} pool_g2={len(POOL['g2'])}\n"
        )
    for n, rid in enumerate(ids, 1):
        payload = LEAN_PAYLOAD if rid.startswith("me2h_") else POOL_PAYLOAD
        try:
            d = api(f"/api/recordings/{rid}/test", payload)
            jid = d["job"]["id"]
        except Exception as exc:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(
                    f"T{n}/{len(ids)} {rid} POST-ERROR {type(exc).__name__} {exc}\n"
                )
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
            f.write(
                f"T{n}/{len(ids)} {rid} job={jid} {j['status']} elapsed={time.time() - t0:.0f}s "
                f"lanes={len(j.get('summaries') or [])}\n"
            )
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"TRIM-POOL-DONE {len(ids)} takes total={time.time() - t0:.0f}s\n")


if __name__ == "__main__":
    main()
