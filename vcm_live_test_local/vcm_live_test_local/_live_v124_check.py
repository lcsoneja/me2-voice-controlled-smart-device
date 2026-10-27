"""Score one take through the live server across ALL models, including V124.

Exercises _load_runner -> gates.gate2_model(name) -> Gate2V124EnsembleRunner inside the
server, which the leaderboard "all models" path uses after every recording.
"""

import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"


def main() -> int:
    try:
        with urllib.request.urlopen(BASE + "/api/oneshot/recordings", timeout=120) as resp:
            rows = json.loads(resp.read().decode())["recordings"]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("LIST_FAILED " + type(exc).__name__ + " " + str(exc)[:120])
        return 1
    take = next((row["id"] for row in rows if (row.get("action") or "").strip()), "")
    if not take:
        print("NO_TAKES")
        return 1
    started = time.perf_counter()
    request = urllib.request.Request(
        BASE + "/api/oneshot/leaderboard/score",
        data=json.dumps({"ids": [take], "models": "all", "reset": True}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as resp:
            result = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("SCORE_FAILED " + type(exc).__name__ + " " + str(exc)[:120])
        return 1
    rank = result["ranking"]
    row = next((r for r in rank if r["model"] == "gate2v124_ensemble4way"), None)
    print("TOOK " + str(round(time.perf_counter() - started, 1)) + "s")
    print("RANKED=" + str(len(rank)) + " v124=" + json.dumps(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
