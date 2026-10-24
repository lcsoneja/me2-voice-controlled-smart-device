"""Probe: Architectures v1/v2/v3 on two tagged takes — v3 confirms the same
intents as v1 (possibly one tick later, by vote design) and never more."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8765"
REC = "20261023_155245_2dd71e"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.load(r)


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


ok = True
def check(name, cond, detail=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (("  " + str(detail)) if detail else ""))


recs = get("/api/recordings")["recordings"]
second = next((r["id"] for r in recs if r.get("label") == "rf-take-015303"), REC)

for take in (REC, second):
    d = post("/api/recordings/" + take + "/test",
             {"g1_models": ["gate1v10_dr"], "models": ["gate2v16"], "hop_s": 1.0,
              "nc_modes": [True], "architectures": [0, 1, 2]})
    jid = d["job"]["id"]
    deadline = time.time() + 120
    job = {}
    while time.time() < deadline:
        job = get("/api/jobs/" + jid)["job"]
        if job["status"] not in ("queued", "running"):
            break
        time.sleep(0.5)
    # pi-lens-ignore: Pyright:reportPossiblyUnbound
    combos = job.get("combos", [])
    check("[" + take[:16] + "] 3 combos, arch 0/1/2",
          len(combos) == 3 and [c[3] for c in combos] == [0, 1, 2], "")
    # pi-lens-ignore: Pyright:reportPossiblyUnbound
    evs = job.get("events", [])
    lanes = {}
    for e in evs:
        if e.get("kind") != "g2":
            continue
        a = int(e.get("arch", 0))
        lanes.setdefault(a, []).append((round(e.get("t", 0), 1), e.get("label")))
    for a in sorted(lanes):
        print("  [" + take[:16] + "] arch", a, "g2 fires:", lanes[a])
    v1 = lanes.get(0, [])
    v2 = lanes.get(1, [])
    v3 = lanes.get(2, [])
    v1labels = {l for _, l in v1}
    check("[" + take[:16] + "] v3 intents confirmed within v1's intent set",
          all(l in v1labels for _, l in v3),
          "v3: " + json.dumps(v3)[:140])
    # pi-lens-ignore: Pyright:reportPossiblyUnbound
    ct = {s.get("arch"): s.get("command_ticks", 0) for s in job.get("summaries", [])}
    check("[" + take[:16] + "] v3 command_ticks <= v1", ct.get(2, 0) <= ct.get(0, 0), str(ct))
    if v2:
        first_g1 = min((e.get("t", 0) for e in evs if e.get("kind") == "g1"), default=None)
        first_v2 = min(t for t, _ in v2)
        if first_g1 is not None:
            check("[" + take[:16] + "] v2 lane: intent only after wake", first_v2 >= first_g1,
                  f"first_g1={first_g1} first_v2={first_v2}")

analysis = get("/api/analysis").get("rows", [])
print("analysis rows:", len(analysis))
print("OVERALL: " + ("PASS" if ok else "FAIL"))
