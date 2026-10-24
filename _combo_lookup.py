"""Print exact metrics for specific (G1, G2, NC, arch) lanes from stored sweep results.

Replicates _best_combo_analysis.py scoring verbatim so the numbers quoted in the
deck match the published ranking. Read-only: never writes results.
"""

import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE / "vcm_live_test_local" / "vcm_live_test_local"
RES = APP / "recordings" / "results"
IDX = APP / "recordings" / "index.json"

RFZ_ALIAS = {
    "settimer": "timer", "alarmset": "alarm", "tempup": "temperature", "tempdown": "temperature",
    "lightsdim": "brightness", "lightsbright": "brightness", "lightson": "lighton", "lightsoff": "lightoff",
    "reminderset": "createreminder", "remindercheck": "listreminders", "checkreminders": "listreminders",
    "mediaplay": "playmusic", "mediapause": "pause", "medianext": "next", "silence": "stop",
}

WANTED = [
    ("gate1v12_f16", "gate2v64p_paired_owner", False, 0),
    ("gate1v12_f16", "gate2v20_aux", False, 0),
    ("gate1v3_f32", "gate2v64p_paired_owner", False, 0),
    ("gate1v3_f32", "gate2v20_aux", False, 0),
]


def bag(s):
    return "".join(sorted(p for p in re.split(r"[^a-z]+", str(s or "").lower()) if p))


def alias(b):
    return RFZ_ALIAS.get(b, b)


def match(pred, exp):
    return bool(exp) and alias(bag(pred)) == alias(bag(exp))


def arch_of(s):
    a = s.get("arch")
    if a is None or a == "":
        return 1 if s.get("gated") else 0
    return int(a)


def main():
    idx = json.loads(IDX.read_text(encoding="utf-8"))
    recs = idx["recordings"] if isinstance(idx, dict) else idx
    by_id = {r["id"]: r for r in recs}

    latest = {}
    for path in sorted(RES.glob("*.json")):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rid = str(job.get("recording") or "")
        if not rid or rid not in by_id:
            continue
        stamp = path.stat().st_mtime
        if rid not in latest or stamp > latest[rid][0]:
            latest[rid] = (stamp, job)

    lanes = {}
    for rid, (_stamp, job) in latest.items():
        rec = by_id[rid]
        exp_wake = str(rec.get("wake_word") or "").strip()
        exp_act = str(rec.get("action") or "").strip()
        is_oos = "OOS" in str(rec.get("label") or "")
        events = job.get("events") or []
        g1_by_lane = {}
        for e in events:
            if e.get("kind") == "g1":
                k = (e.get("g1_model"), e.get("model"), bool(e.get("nc")), arch_of(e))
                g1_by_lane.setdefault(k, []).append(e)
        for s in job.get("summaries") or []:
            if s.get("error"):
                continue
            k = (s.get("g1_model"), s.get("model"), bool(s.get("nc")), arch_of(s))
            if k not in WANTED:
                continue
            a = lanes.setdefault(k, {"takes": 0, "act_j": 0, "act_ok": 0, "full_j": 0,
                                     "full_ok": 0, "wake_ok": 0, "trig": 0, "oos": 0,
                                     "oos_fire": 0, "ms": [], "p95": []})
            a["takes"] += 1
            if is_oos:
                a["oos"] += 1
                if (s.get("trigger_ticks") or 0) > 0:
                    a["oos_fire"] += 1
                continue
            g1ok = None
            if exp_wake and events:
                g1ok = any(bag(e.get("label")) == bag(exp_wake) for e in g1_by_lane.get(k, []))
            matched = 0
            if exp_act:
                for intent, cnt in (s.get("intents") or {}).items():
                    if match(intent, exp_act):
                        matched += cnt
            g2ok = (matched > 0) if exp_act else None
            if exp_act:
                a["act_j"] += 1
                if g2ok:
                    a["act_ok"] += 1
                if (s.get("trigger_ticks") or 0) > 0:
                    a["trig"] += 1
            if exp_act and exp_wake and events:
                a["full_j"] += 1
                if g1ok:
                    a["wake_ok"] += 1
                if g1ok and g2ok:
                    a["full_ok"] += 1
            if s.get("mean_infer_ms"):
                a["ms"].append(float(s["mean_infer_ms"]))
            if s.get("p95_infer_ms"):
                a["p95"].append(float(s["p95_infer_ms"]))

    print(f"takes_deduped={len(latest)} lanes_requested={len(WANTED)}")
    out = {}
    for k in WANTED:
        a = lanes.get(k)
        if not a:
            print(f"LANE {k} -> NO DATA")
            continue
        full_rate = a["full_ok"] / a["full_j"] if a["full_j"] else -1.0
        act_rate = a["act_ok"] / a["act_j"] if a["act_j"] else -1.0
        wake_rate = a["wake_ok"] / a["full_j"] if a["full_j"] else -1.0
        ms = sorted(a["ms"])[len(a["ms"]) // 2] if a["ms"] else -1.0
        p95 = sorted(a["p95"])[len(a["p95"]) // 2] if a["p95"] else -1.0
        oos_rej = 1 - (a["oos_fire"] / a["oos"]) if a["oos"] else -1.0
        row = {"g1": k[0], "g2": k[1], "nc": k[2], "arch": k[3],
               "takes": a["takes"], "act_j": a["act_j"], "act_ok": a["act_ok"],
               "full_j": a["full_j"], "full_ok": a["full_ok"], "wake_ok": a["wake_ok"],
               "rate": round(full_rate, 6), "act": round(act_rate, 6), "wake": round(wake_rate, 6),
               "trig": a["trig"], "oos": a["oos"], "oos_fire": a["oos_fire"],
               "oos_rej": round(oos_rej, 6), "ms": round(ms, 3), "p95": round(p95, 3)}
        out["|".join(str(x) for x in k)] = row
        print(f"LANE {k[0]:14s} x {k[1]:22s} raw v{k[3] + 1}  full {a['full_ok']}/{a['full_j']} "
              f"({100 * full_rate:.1f}%)  act {100 * act_rate:.1f}%  wake {100 * wake_rate:.1f}% "
              f"oos_rej {100 * oos_rej:.1f}% (n={a['oos']})  p95 {p95:.1f}ms  mean {ms:.1f}ms")
    HERE.joinpath("_combo_lookup.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("wrote _combo_lookup.json")


if __name__ == "__main__":
    main()
