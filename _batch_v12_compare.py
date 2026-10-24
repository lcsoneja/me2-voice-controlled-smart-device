"""Controlled head-to-head: Gate1 v12 vs v3 x Gate2 v64p/v20_aux, same takes, raw, arch v1.

Runs 4 lanes per take against the live dashboard server so every lane sees the
exact same take set (an apples-to-apples comparison, unlike scanning stored
results whose per-lane coverage differs). Writes only to the server's own result
store; snapshots the pre-existing result files so the analyzer can scope to new ones.
"""

import http.client
import json
import pathlib
import time

# The dashboard server is local-only; connect explicitly so no URL scheme is ever parsed.
HOST = "127.0.0.1"
PORT = 8765
HERE = pathlib.Path(__file__).resolve().parent
APP = HERE / "vcm_live_test_local" / "vcm_live_test_local"
RES = APP / "recordings" / "results"
LOG = HERE / "_batch_v12_compare.log"
BEFORE = HERE / "_v12_results_before.txt"

G1 = ["gate1v12_f16", "gate1v3_f32"]
G2 = ["gate2v64p_paired_owner", "gate2v20_aux"]
PAYLOAD = {"g1_models": G1, "models": G2, "hop_s": 1.0,
           "nc_modes": [False], "architectures": [0], "workers": 0}


def api(path, data=None, timeout=300):
    conn = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    try:
        if data is None:
            conn.request("GET", path)
        else:
            conn.request("POST", path, body=json.dumps(data).encode("utf-8"),
                         headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        payload = resp.read()
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status} for {path}")
        return json.loads(payload)
    finally:
        conn.close()


def log(line):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    existing = sorted(p.name for p in RES.glob("*.json"))
    BEFORE.write_text("\n".join(existing) + "\n", encoding="utf-8")
    log(f"snapshot existing={len(existing)}")

    recs = api("/api/recordings")["recordings"]
    ids = [r["id"] for r in recs]
    log(f"batch-start takes={len(ids)} lanes_per_take={len(G1)}x{len(G2)}x1x1")
    t0 = time.time()
    errors = 0
    for n, rid in enumerate(ids, 1):
        try:
            d = api(f"/api/recordings/{rid}/test", PAYLOAD)
            jid = d["job"]["id"]
        except Exception as exc:
            errors += 1
            log(f"{n}/{len(ids)} {rid} POST-ERROR {type(exc).__name__} {exc}")
            continue
        while True:
            try:
                j = api(f"/api/jobs/{jid}")["job"]
            except Exception:
                time.sleep(2.0)
                continue
            if j["status"] not in ("running", "queued"):
                break
            time.sleep(1.0)
        log(f"{n}/{len(ids)} {rid} job={jid} {j['status']} elapsed={time.time() - t0:.0f}s "
            f"lanes={len(j.get('summaries') or [])}")
    log(f"BATCH-DONE {len(ids)} takes errors={errors} total={time.time() - t0:.0f}s")
    print(f"batch done takes={len(ids)} errors={errors} elapsed={time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
