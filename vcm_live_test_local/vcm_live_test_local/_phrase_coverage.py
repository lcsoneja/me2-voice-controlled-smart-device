"""Phrase coverage vs the real holdout intents."""

import json
import pathlib

APP = pathlib.Path(__file__).resolve().parent


def main() -> int:
    phrases = json.loads(
        (APP / "gate1_web" / "data" / "test_phrases.json").read_text(encoding="utf-8")
    )["phrases"]
    by_intent: dict[str, list[str]] = {}
    for row in phrases:
        by_intent.setdefault(row["intent"], []).append(row["phrase"])

    index = json.loads((APP / "recordings" / "index.json").read_text(encoding="utf-8"))
    recs = index["recordings"] if isinstance(index, dict) else index
    real = [
        row
        for row in recs
        if "me2h" in str(row.get("id"))
        and "(real)" in str(row.get("label") or "").lower()
    ]
    held: dict[str, int] = {}
    for row in real:
        key = str(row.get("action") or "").strip()
        held[key] = held.get(key, 0) + 1

    print("HOLDOUT_REAL=" + str(len(real)) + " intents=" + str(len(held)))
    missing = [key for key in held if key not in by_intent]
    print(
        "PHRASE_COVERAGE with_phrase="
        + str(sum(1 for key in held if key in by_intent))
        + " missing="
        + str(missing)
    )
    for key, count in sorted(held.items()):
        have = len(by_intent.get(key, []))
        print(
            "  "
            + key
            + "  clips="
            + str(count)
            + " phrases="
            + str(have)
            + ("" if have else "  <-- NO PHRASE")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
