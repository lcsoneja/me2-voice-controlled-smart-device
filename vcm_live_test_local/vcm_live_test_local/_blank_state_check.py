"""Final state: blank recordings, empty ranking."""

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"


def fetch(path: str) -> tuple[bool, dict]:
    """(ok, payload); every throwing call is inside this try."""
    try:
        with urllib.request.urlopen(BASE + path, timeout=120) as response:
            return True, json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("CHECK_FAILED " + type(exc).__name__ + " " + str(exc)[:120])
        return False, {}


def main() -> int:
    ok_recs, recs_payload = fetch("/api/oneshot/recordings")
    ok_rank, rank_payload = fetch("/api/oneshot/leaderboard")
    if not ok_recs or not ok_rank:
        return 1
    recs = recs_payload.get("recordings", [])
    rank = rank_payload.get("ranking", [])
    print("RECORDINGS=" + str(len(recs)) + " RANKING=" + str(len(rank)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
