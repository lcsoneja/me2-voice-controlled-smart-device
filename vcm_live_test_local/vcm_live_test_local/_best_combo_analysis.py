"""Rank every (G1, G2, NC, arch) lane across stored batch results.

Usage:
  py -3.12 _best_combo_analysis.py              # all stored results
  py -3.12 _best_combo_analysis.py --only-new   # only this batch's new results
  py -3.12 _best_combo_analysis.py --top=15
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
RES = HERE / "recordings" / "results"
IDX = HERE / "recordings" / "index.json"
BEFORE = HERE / "_results_before_batch.txt"

ONLY_NEW = "--only-new" in sys.argv
TOP_N = 15
for arg in sys.argv:
    if arg.startswith("--top="):
        TOP_N = int(arg.split("=", 1)[1])

RFZ_ALIAS = {
    "settimer": "timer", "alarmset": "alarm", "tempup": "temperature", "tempdown": "temperature",
    "lightsdim": "brightness", "lightsbright": "brightness", "lightson": "lighton", "lightsoff": "lightoff",
    "reminderset": "createreminder", "remindercheck": "listreminders", "checkreminders": "listreminders",
    "mediaplay": "playmusic", "mediapause": "pause", "medianext": "next", "silence": "stop",
}


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
    skip = set(BEFORE.read_text(encoding="utf-8").split()) if (ONLY_NEW and BEFORE.exists()) else set()

    lanes = {}
    jobs = 0
    # Two drivers can process the same take around a boundary; keep only the
    # newest result file per recording so no take is double-counted.
    latest = {}
    for path in sorted(RES.glob("*.json")):
        if path.name in skip:
            continue
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"skip-unreadable {path.name}: {type(exc).__name__}", file=sys.stderr)
            continue
        rid = str(job.get("recording") or "")
        if not rid or rid not in by_id:
            continue
        stamp = path.stat().st_mtime
        if rid not in latest or stamp > latest[rid][0]:
            latest[rid] = (stamp, job)
    for rid, (_stamp, job) in latest.items():
        rec = by_id[rid]
        jobs += 1
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

    rows = []
    for k, a in lanes.items():
        full_rate = a["full_ok"] / a["full_j"] if a["full_j"] else -1.0
        act_rate = a["act_ok"] / a["act_j"] if a["act_j"] else -1.0
        wake_rate = a["wake_ok"] / a["full_j"] if a["full_j"] else -1.0
        ms = sorted(a["ms"])[len(a["ms"]) // 2] if a["ms"] else -1.0
        p95 = sorted(a["p95"])[len(a["p95"]) // 2] if a["p95"] else -1.0
        rows.append({"g1": k[0], "g2": k[1], "nc": k[2], "arch": k[3],
                     "takes": a["takes"], "act_j": a["act_j"], "act_ok": a["act_ok"],
                     "full_j": a["full_j"], "full_ok": a["full_ok"], "wake_ok": a["wake_ok"],
                     "rate": full_rate, "act": act_rate, "wake": wake_rate,
                     "trig": a["trig"], "oos": a["oos"], "oos_fire": a["oos_fire"],
                     "oos_rej": (1 - a["oos_fire"] / a["oos"]) if a["oos"] else -1.0, "ms": ms,
                     "p95": p95})
    rows.sort(key=lambda r: (-max(r["rate"], 0), -max(r["act"], 0), r["ms"]))

    print("jobs-analyzed:", jobs)
    hdr = f"{'#':<3} {'G1':<10} {'G2':<22} {'nc':<4} {'arch':<5} {'full':>5} {'rate':>7} {'act':>7} {'wake':>7} {'oosrej':>7} {'ms':>5} {'p95':>5}"
    print(hdr)
    for i, r in enumerate(rows[:TOP_N], 1):
        print(f"{i:<3} {r['g1'].replace('gate1',''):<10} {r['g2'].replace('gate2',''):<22} "
              f"{'nc' if r['nc'] else 'raw':<4} {'v'+str(r['arch']+1):<5} {r['full_ok']:>5} "
              f"{100*max(r['rate'], 0):>6.1f}% {100*max(r['act'], 0):>6.1f}% "
              f"{100*max(r['wake'], 0):>6.1f}% "
              f"{100*max(r['oos_rej'], 0):>6.1f}% {r['ms']:>5.1f} {r['p95']:>5.1f}")
    best = rows[0] if rows else None
    pathlib.Path(HERE / "_best_combo.json").write_text(json.dumps(
        {"jobs": jobs, "best": best, "top": rows[:50], "lane_count": len(rows)}, indent=1), encoding="utf-8")
    # Top-5 dashboard bookmarks: refreshed whenever this analysis runs, so the
    # preset strip always carries the newest full-batch ranking.
    js_rows = []
    for i, r in enumerate(rows[:5], 1):
        js_rows.append({"rank": i, "g1": r["g1"], "g2": r["g2"], "nc": bool(r["nc"]), "arch": int(r["arch"]),
                        "full": f"{r['full_ok']}/{r['full_j']}",
                        "rate": round(100 * max(r["rate"], 0), 1), "act": round(100 * max(r["act"], 0), 1),
                        "wake": round(100 * max(r["wake"], 0), 1),
                        "oos_rej": round(100 * max(r["oos_rej"], 0), 1),
                        "ms": round(r["ms"], 1) if r["ms"] >= 0 else -1,
                        "p95": round(r.get("p95", -1), 1) if r.get("p95", -1) >= 0 else -1})
    pathlib.Path(HERE / "gate1_web" / "js" / "best_combo.js").write_text(
        "// Auto-generated from the batch replay ranking (_best_combo_analysis.py).\n"
        "window.VCM_TOP_COMBOS = " + json.dumps(js_rows) + ";\n", encoding="utf-8")
    print("wrote gate1_web/js/best_combo.js (top", len(js_rows), "bookmarks)")
    if best:
        print("BEST:", best["g1"], "x", best["g2"], "nc" if best["nc"] else "raw", "v" + str(best["arch"] + 1),
              "full", str(best["full_ok"]) + "/" + str(best["full_j"]),
              "act", str(best["act_ok"]) + "/" + str(best["act_j"]),
              "p95ms", best.get("p95"))
    print("wrote _best_combo.json")


if __name__ == "__main__":
    main()
