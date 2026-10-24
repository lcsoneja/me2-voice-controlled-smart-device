"""Re-run the OOS trap takes with (pool + V77) under the FIXED NEG masking.

V68's earlier OOS data was collected with NEG treated as a real intent (the
pre-fix code), understating its rejection; this pass replaces those takes'
newest result files (dedupe keeps newest) and adds V77's OOS numbers.
"""
import json
import pathlib
import time
import urllib.request

BASE = "http://127.0.0.1:8765"
HERE = pathlib.Path(__file__).resolve().parent
POOL = json.loads((HERE / "_trim_pool.json").read_text(encoding="utf-8"))
G2 = POOL["g2"] + ["gate2v77_speech_neg"]
G1 = POOL["g1"]
FULL = {"g1_models": G1, "models": G2, "hop_s": 1.0, "nc_modes": [False],
        "architectures": [0, 1], "workers": 0}
LEAN = {"g1_models": [G1[0]], "models": G2, "hop_s": 1.0, "nc_modes": [False],
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
    recs = api("/api/recordings")["recordings"]
    oos_w = [r["id"] for r in recs if r["id"].startswith("me2w_") and "OOS" in str(r.get("label", ""))]
    oos_h = [r["id"] for r in recs if r["id"].startswith("me2h_") and "OOS" in str(r.get("label", ""))]
    print("me2w-oos:", len(oos_w), "| me2h-oos:", len(oos_h))
    t0 = time.time()
    done = 0
    for rid in oos_w + oos_h:
        payload = FULL if rid.startswith("me2w_") else LEAN
        try:
            d = api(f"/api/recordings/{rid}/test", payload)
            jid = d["job"]["id"]
        except Exception as exc:
            print(rid, "POST-ERROR", type(exc).__name__, exc)
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
        done += 1
        print(rid, j["status"], "lanes", len(j.get("summaries") or []),
              f"elapsed={time.time()-t0:.0f}s")
    print(f"OOS-RERUN-DONE takes={done} total={time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
