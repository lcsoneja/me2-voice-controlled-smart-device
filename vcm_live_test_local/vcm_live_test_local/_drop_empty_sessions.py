"""Delete the empty sessions (user-requested cleanup) via the manager API."""

import json
import pathlib
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
STORE = pathlib.Path(__file__).resolve().parent / "recordings"


def api(path: str, payload: dict | None = None, post: bool = True) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path, data=data, method="POST" if post else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit("call failed " + path + ": " + type(exc).__name__ + " " + str(exc)[:120])


def main() -> int:
    sessions = api("/api/oneshot/sessions", post=False)["sessions"]
    empties = [session for session in sessions if not session.get("takes")]
    print("EMPTY_FOUND=" + str(len(empties)))
    for session in empties:
        outcome = api("/api/oneshot/sessions/delete", {"id": session["id"]})
        print("DELETED " + str(session["id"]) + " -> " + str(outcome["deleted"]))
    after = api("/api/oneshot/sessions", post=False)["sessions"]
    print("SESSIONS_LEFT=" + str(len(after))
          + " with_takes=" + str(sum(1 for s in after if s.get("takes"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
