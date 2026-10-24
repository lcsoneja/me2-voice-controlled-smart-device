"""V77 full-pipeline pass: all me2w takes with (pool + V77), fixed NEG masking.

Replaces each me2w take's newest result with the pool+V77 job (dedupe keeps
newest), so V77 lands in the final ranking with real full-pipeline data and
the pool lanes keep theirs. ~7s/take x 202.
"""

import json
import pathlib
import time
import urllib.request

BASE = "http://127.0.0.1:8765"
HERE = pathlib.Path(__file__).resolve().parent
POOL = json.loads((HERE / "_trim_pool.json").read_text(encoding="utf-8"))
G2 = POOL["g2"] + ["gate2v77_speech_neg"]
PAYLOAD = {
    "g1_models": POOL["g1"],
    "models": G2,
    "hop_s": 1.0,
    "nc_modes": [False],
    "architectures": [0, 1],
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
    recs = api("/api/recordings")["recordings"]
    ids = [r["id"] for r in recs if r["id"].startswith("me2w_")]
    t0 = time.time()
    print(f"v77-pass-start takes={len(ids)} pool_g2={len(G2)}", flush=True)
    for n, rid in enumerate(ids, 1):
        try:
            d = api(f"/api/recordings/{rid}/test", PAYLOAD)
            jid = d["job"]["id"]
        except Exception as exc:
            print(
                f"V{n}/{len(ids)} {rid} POST-ERROR {type(exc).__name__} {exc}",
                flush=True,
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
        if n % 20 == 0:
            print(
                f"V{n}/{len(ids)} {rid} {j['status']} elapsed={time.time() - t0:.0f}s",
                flush=True,
            )
    print(f"V77-PASS-DONE {len(ids)} takes total={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
