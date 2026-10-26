"""Epoch-format and reset-during-round guard, exercised against the live server."""

import json
import threading
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
MODEL = "gate2v108_ownerft_v93b"


def call(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method="POST" if data else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            "call failed: "
            + str(exc.code)
            + " "
            + exc.read().decode(errors="replace")[:200]
        )


def main() -> int:
    rows = call("/api/oneshot/recordings")["recordings"]
    take = next(row["id"] for row in rows if (row.get("action") or "").strip())

    seeded = call(
        "/api/oneshot/leaderboard/score",
        {"ids": [take], "models": [MODEL], "reset": True},
    )
    top = seeded["ranking"][0] if seeded["ranking"] else {}
    print(
        "A_SINGLE model=" + top.get("model", "?") + " scored=" + str(top.get("scored"))
    )

    result: dict = {}
    thread = threading.Thread(
        target=lambda: result.update(
            resp=call(
                "/api/oneshot/leaderboard/score", {"ids": [take], "models": "all"}
            )
        )
    )
    thread.start()
    time.sleep(2)
    reset = call("/api/oneshot/leaderboard/reset", {})
    thread.join(300)
    print(
        "B_RESET epoch="
        + str(reset.get("epoch"))
        + " detected="
        + str(result.get("resp", {}).get("reset_detected"))
    )
    print("B_FINAL ranking=" + str(len(call("/api/oneshot/leaderboard")["ranking"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
