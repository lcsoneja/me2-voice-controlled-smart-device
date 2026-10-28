"""Phrase list vs the real holdout labels: canonical wording + short forms."""

import json
import pathlib

APP = pathlib.Path(__file__).resolve().parent


def main() -> int:
    try:
        phrases = json.loads(
            (APP / "gate1_web" / "data" / "test_phrases.json").read_text(
                encoding="utf-8"
            )
        )["phrases"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print("PHRASES_READ " + type(exc).__name__)
        return 1
    by_intent: dict[str, list[str]] = {}
    for row in phrases:
        by_intent.setdefault(row["intent"], []).append(row["phrase"])

    try:
        index = json.loads(
            (APP / "recordings" / "index.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        print("INDEX_READ " + type(exc).__name__)
        return 1
    recs = index["recordings"] if isinstance(index, dict) else index
    labels: dict[str, list[str]] = {}
    for rec in recs:
        label = str(rec.get("label") or "")
        action = str(rec.get("action") or "").strip()
        if "me2h" in str(rec.get("id")) and "(real)" in label.lower() and action:
            text = label.split(":")[-1].strip()
            labels.setdefault(action, [])
            if text not in labels[action]:
                labels[action].append(text)

    for action in ("CALL", "ALARM", "BRIGHTNESS"):
        if action in labels:
            print(action + " HOLD=" + " / ".join(labels[action])[:200])
    for action in sorted(labels):
        hold = " / ".join(labels[action])
        mine = "; ".join(by_intent.get(action, []))
        print(action)
        print("  HOLD=" + hold[:90])
        print("  LIST=" + mine[:110])
    print("--- intents with NO holdout real clip ---")
    print([action for action in by_intent if action not in labels])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
