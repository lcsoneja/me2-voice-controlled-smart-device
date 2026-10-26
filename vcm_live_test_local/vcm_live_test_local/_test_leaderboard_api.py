"""Exercise the leaderboard endpoints: single model, all models, persistence, reset."""

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"


def call(path: str, payload: dict | None = None) -> dict:
    """GET by default; POST when a payload is supplied or the path is a reset action."""
    post = payload is not None or path.endswith("/reset")
    body = json.dumps(payload if payload is not None else {}).encode() if post else None
    request = urllib.request.Request(
        BASE + path, data=body, method="POST" if post else "GET"
    )
    if post:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            "request failed for " + path + ": " + type(exc).__name__ + " " + str(exc)
        )


def main() -> int:
    recs = call("/api/oneshot/recordings")["recordings"]
    labelled = [r for r in recs if r["action"]][:3]
    ids = [r["id"] for r in labelled]
    print("TAKES " + str(ids) + " actions=" + str([r["action"] for r in labelled]))
    print("INITIAL ranking=" + str(len(call("/api/oneshot/leaderboard")["ranking"])))

    one = call(
        "/api/oneshot/leaderboard/score",
        {"ids": ids, "models": ["gate2v108_ownerft_v93b"], "reset": True},
    )
    print(
        "SINGLE_MODEL "
        + str(
            [(r["model"], r["correct"], r["scored"], r["acc"]) for r in one["ranking"]]
        )
    )

    every = call("/api/oneshot/leaderboard/score", {"ids": ids, "models": "all"})
    print(
        "ALL_MODELS n="
        + str(len(every["ranking"]))
        + " top3="
        + str(
            [
                (r["model"][:20], r["correct"], r["scored"], r["acc"])
                for r in every["ranking"][:3]
            ]
        )
    )

    persisted = call("/api/oneshot/leaderboard")
    top = persisted["ranking"][0]
    print(
        "PERSISTED n="
        + str(len(persisted["ranking"]))
        + " top1="
        + top["model"][:22]
        + " scored="
        + str(top["scored"])
        + " runs="
        + str(top["runs"])
    )

    cleared = call("/api/oneshot/leaderboard/reset")
    print("RESET ranking=" + str(len(cleared["ranking"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
