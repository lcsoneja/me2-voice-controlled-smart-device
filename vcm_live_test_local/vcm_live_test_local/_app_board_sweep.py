"""Refresh the app's scoreboard: back up the old board, reset, then score every labelled
take x all 92 models (raw, as recorded). This is the app's own "Test all mine x all models"
mechanism, run over the whole recordings store so the in-app ranking covers all models."""

import json
import pathlib
import shutil
import time
import urllib.request

BASE = "http://127.0.0.1:8765"
CHUNK = 12


def call(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method="POST" if data else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    board = pathlib.Path("recordings/leaderboard.json")
    if board.is_file():
        shutil.copy2(board, board.with_name("leaderboard.pre92_backup.json"))
        print("board_backup_ok")
    recs = call("/api/oneshot/recordings")["recordings"]
    scoreable = [r for r in recs if (r.get("action") or "").strip()]
    print("sweep_takes=" + str(len(scoreable)) + " of " + str(len(recs)) + " rows")
    call("/api/oneshot/leaderboard/reset", {})
    print("board_reset")
    started = time.time()
    rounds = 0
    fails = []
    for i in range(0, len(scoreable), CHUNK):
        ids = [r["id"] for r in scoreable[i : i + CHUNK]]
        resp = None
        for attempt in range(2):
            try:
                resp = call(
                    "/api/oneshot/leaderboard/score",
                    {"ids": ids, "models": "all", "trim": False},
                )
                break
            except Exception as exc:  # retry once, then record the failure
                if attempt:
                    fails.append((i, str(exc)))
                    print("round_fail at " + str(i) + ": " + str(exc))
                else:
                    time.sleep(2)
        if resp is None:
            continue
        rounds += 1
        top = (resp.get("ranking") or [{}])[0]
        print(
            "round "
            + str(rounds)
            + " up to take "
            + str(i + len(ids))
            + " top="
            + str(top.get("model"))
            + " "
            + str(round(100 * (top.get("acc") or 0), 1))
            + "%"
        )
    final = call("/api/oneshot/leaderboard")
    with open("_app_board_sweep_results.json", "w", encoding="utf-8") as handle:
        json.dump(final, handle, indent=1)
    print(
        "elapsed_s="
        + str(round(time.time() - started, 1))
        + " failed_rounds="
        + str(len(fails))
    )
    print("SWEEP_DONE models=" + str(final["models"]))
    for row in final["ranking"]:
        acc = row["acc"]
        print(
            "  "
            + row["model"].ljust(34)
            + " "
            + str(row["correct"])
            + "/"
            + str(row["scored"])
            + " = "
            + (str(round(100 * acc, 1)) + "%" if acc is not None else "-")
            + " runs="
            + str(row["runs"])
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
