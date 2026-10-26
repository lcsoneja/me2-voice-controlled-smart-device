"""Exercise the new one-shot recordings endpoints: list, score, delete, holdout guard."""

import base64
import io
import json
import urllib.error
import urllib.request
import wave

import numpy as np

BASE = "http://127.0.0.1:8765"


def call(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path, data=data, method="POST" if data else "GET"
    )
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SystemExit(
            "request failed for " + path + ": " + type(exc).__name__ + " " + str(exc)
        )


def main() -> int:
    listing = call("/api/oneshot/recordings")
    rows = listing["recordings"]
    holdout = [r for r in rows if r["holdout"] and r["action"]]
    takes = [r for r in rows if r["action"] and not r["holdout"]]
    print(
        "LIST count="
        + str(listing["count"])
        + " labelled_takes="
        + str(len(takes))
        + " holdout_with_label="
        + str(len(holdout))
    )

    ids = [r["id"] for r in holdout[:3]]
    models = ["gate2v108_ownerft_v93b", "gate2v64d_expandedneg", "gate2v56_v54"]
    scored = call("/api/oneshot/recordings/score", {"ids": ids, "models": models})
    for take in scored["takes"]:
        print(
            "  TAKE "
            + take["id"]
            + " expected="
            + take["action"]
            + " -> "
            + ", ".join(
                r["model"][:20] + ":" + r["intent"] + ("+" if r["match"] else "-")
                for r in take["results"]
            )
        )
    print(
        "  SUMMARY "
        + ", ".join(
            s["model"][:20] + " " + str(s["correct"]) + "/" + str(s["scored"])
            for s in scored["summary"]
        )
    )

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(np.zeros(16000, dtype=np.int16).tobytes())
    created = call(
        "/api/recordings",
        {
            "wav_base64": base64.b64encode(buffer.getvalue()).decode(),
            "label": "DELETE-ME api test take",
            "wake_word": "wake",
            "action": "PLAY_MUSIC",
        },
    )
    new_id = (
        created.get("id")
        or (created.get("recording") or {}).get("id")
        or str(created)[:80]
    )
    print("CREATED new_id=" + str(new_id))

    before = call("/api/oneshot/recordings")["count"]
    removed = call("/api/oneshot/recordings/delete", {"ids": [new_id]})
    after = call("/api/oneshot/recordings")["count"]
    print(
        "DELETE deleted="
        + str(removed["deleted"])
        + " remaining="
        + str(removed["remaining"])
        + " count "
        + str(before)
        + " -> "
        + str(after)
    )

    guarded = call("/api/oneshot/recordings/delete", {"ids": ["me2h_0000"]})
    print(
        "HOLDOUT_GUARD refused="
        + str(guarded["refused_holdout"])
        + " deleted="
        + str(guarded["deleted"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
