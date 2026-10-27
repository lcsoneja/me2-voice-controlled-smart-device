"""Score one take across all 73 models on the live server."""

import json
import urllib.error
import urllib.request


def main() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/api/oneshot/recordings", timeout=120) as resp:
            rows = json.loads(resp.read().decode())["recordings"]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("LIST_FAILED " + type(exc).__name__)
        return 1
    take = next((r["id"] for r in rows if (r.get("action") or "").strip()), "")
    request = urllib.request.Request(
        "http://127.0.0.1:8765/api/oneshot/leaderboard/score",
        data=json.dumps({"ids": [take], "models": "all", "reset": True}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print("SCORE_HTTP " + str(exc.code))
        return 1
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("SCORE_FAILED " + type(exc).__name__)
        return 1
    rank = result["ranking"]
    new = [r for r in rank if r["model"] in ("gate2v69", "gate2v70", "gate2v71",
                                             "gate2v86_speechoos_mid", "gate2v86b_v77mix",
                                             "gate2v87_combo_intent")]
    print("RANKED=" + str(len(rank)) + " new_models_present=" + str(len(new)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
