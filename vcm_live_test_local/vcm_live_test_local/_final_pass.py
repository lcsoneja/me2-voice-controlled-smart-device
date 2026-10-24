"""Equalization pass: every me2w + owner take with the top-22 G2 models.

The 424-take ranking surfaced leaders OUTSIDE the trim pool (v61_keyword_mix,
v36_17win, v19) whose data stopped at take 154 - their rates were measured on a
different sample than the pool lanes, and job-level dedupe (newest per take)
would erase them once the pool-only passes supersede those takes. This pass
re-runs every me2w + owner take with pool + V77 + those three, so the final
ranking compares ALL leaders over the SAME take base.
"""

import json
import pathlib
import time
import urllib.request

BASE = "http://127.0.0.1:8765"
HERE = pathlib.Path(__file__).resolve().parent
POOL = json.loads((HERE / "_trim_pool.json").read_text(encoding="utf-8"))
G2 = POOL["g2"] + [
    "gate2v77_speech_neg",
    "gate2v61_keyword_mix",
    "gate2v36_17win",
    "gate2v19",
]
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
    ids = [r["id"] for r in recs if not r["id"].startswith("me2h_")]
    t0 = time.time()
    print(
        f"final-pass-start takes={len(ids)} models={len(G2)} lanes={len(POOL['g1']) * len(G2) * 2}",
        flush=True,
    )
    for n, rid in enumerate(ids, 1):
        try:
            d = api(f"/api/recordings/{rid}/test", PAYLOAD)
            jid = d["job"]["id"]
        except Exception as exc:
            print(
                f"P{n}/{len(ids)} {rid} POST-ERROR {type(exc).__name__} {exc}",
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
                f"P{n}/{len(ids)} {rid} {j['status']} elapsed={time.time() - t0:.0f}s",
                flush=True,
            )
    print(f"FINAL-PASS-DONE {len(ids)} takes total={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
