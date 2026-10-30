"""Verify every registered model (incl. the 12 new ones) scores through the live server."""

import json
import urllib.request

BASE = "http://127.0.0.1:8765"
NEW = [
    "gate2v120_timewarp",
    "gate2v121b_specaugonly",
    "gate2v126_mels180",
    "gate2v129_kw",
    "gate2v131_multiscaleauxkw",
    "gate2v132_singlewordmassive",
    "gate2v19p2_owner_vc",
    "gate2v21p2_owner_vc",
    "gate2v142_121b_ownerft",
    "gate2v142_129_kw_ownerft",
    "gate2v142_132_singleword_ownerft",
    "gate2v142_135_distilled_ownerft",
]


def call(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method="POST" if data else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    try:
        lab = call("/api/lab/models")
        names = lab.get("models") if isinstance(lab, dict) else lab
        if isinstance(names, list):
            missing = [n for n in NEW if n not in names]
            print(
                "lab_models="
                + str(len(names))
                + " new_in_lab="
                + str(12 - len(missing))
                + "/12 missing="
                + str(missing)
            )
    except Exception as exc:  # diagnostic probe only
        print("lab_models_error=" + str(exc))

    recs = call("/api/oneshot/recordings")["recordings"]
    mine = [r for r in recs if (r.get("action") or "").strip() and not r.get("holdout")]
    ids = [r["id"] for r in mine[:3]]
    out = call("/api/oneshot/recordings/score", {"ids": ids, "models": "all"})
    counts = [len(t["results"]) for t in out["takes"]]
    ok = bool(counts) and all(c == 92 for c in counts)
    print(
        "takes="
        + str(len(out["takes"]))
        + " results_per_take="
        + str(counts)
        + " ALL92_OK="
        + ("yes" if ok else "no")
    )
    for take in out["takes"]:
        res = take["results"]
        best = max(res, key=lambda r: r.get("conf") or 0)
        print(
            "  take "
            + str(take.get("id"))
            + " expected="
            + str(take.get("action"))
            + " best="
            + best["model"]
            + " -> "
            + str(best.get("intent"))
            + " ("
            + str(round(best.get("conf", 0), 2))
            + ")"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
