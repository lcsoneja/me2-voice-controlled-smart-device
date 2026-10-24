"""Demo-prep batch: EVERY recording through all 13 Gate 1 variants x ALL Gate 2 models (raw, arch v1+v2)."""
import json
import pathlib
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
HERE = pathlib.Path(__file__).resolve().parent
LOG = HERE / "_batch_all_demo_progress.log"
G1_ALL = ["gate1v12_f16", "gate1v8_f32", "gate1v8_f16", "gate1v10_f16", "gate1v10_dr",
          "gate1v5_f32", "gate1v5_f16", "gate1v2_f32", "gate1v2_f16",
          "gate1v3_f32", "gate1v3_f16", "gate1v4_f32", "gate1v4_f16"]
PAYLOAD = {"g1_models": G1_ALL, "models": "all", "hop_s": 1.0,
           "nc_modes": [False], "architectures": [0, 1], "workers": 0}


def api(path, data=None, timeout=180):
    url = BASE + path
    if data is None:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    req = urllib.request.Request(url, json.dumps(data).encode("utf-8"),
                                 {"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main():
    recs = api("/api/recordings")["recordings"]
    ids = [r["id"] for r in recs]
    t0 = time.time()
    LOG.write_text("", encoding="utf-8")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"batch-start takes={len(ids)} lanes_per_take=13x55x1x2\n")
    for n, rid in enumerate(ids, 1):
        try:
            d = api(f"/api/recordings/{rid}/test", PAYLOAD)
            jid = d["job"]["id"]
        except Exception as exc:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(f"{n}/{len(ids)} {rid} POST-ERROR {type(exc).__name__} {exc}\n")
            continue
        while True:
            try:
                j = api(f"/api/jobs/{jid}")["job"]
            except Exception:
                time.sleep(2.0)
                continue
            if j["status"] not in ("running", "queued"):
                break
            time.sleep(1.5)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{n}/{len(ids)} {rid} job={jid} {j['status']} elapsed={time.time()-t0:.0f}s "
                    f"lanes={len(j.get('summaries') or [])} ticks={j.get('ticks_total')}\n")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"BATCH-DONE {len(ids)} takes total={time.time()-t0:.0f}s\n")


if __name__ == "__main__":
    main()
