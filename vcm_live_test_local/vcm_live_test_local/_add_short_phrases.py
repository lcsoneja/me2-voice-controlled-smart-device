"""Add the holdout-faithful short forms to the phrase bank."""

import json
import pathlib

APP = pathlib.Path(__file__).resolve().parent
PATH = APP / "gate1_web" / "data" / "test_phrases.json"

SHORT_FORMS = {
    "PLAY_MUSIC": ["play music", "start music"],
    "WEATHER": ["weather", "weather today"],
    "TIME": ["time"],
    "LIGHT_ON": ["lights on"],
    "LIGHT_OFF": ["lights out"],
    "PAUSE": ["pause"],
    "NEXT": ["next"],
    "CALL": ["call", "make a call"],
    "MESSAGE": ["message"],
    "LIST_REMINDERS": ["reminders"],
    "TIMER": ["timer 10 seconds", "timer 30 seconds"],
    "ALARM": ["alarm 6 am"],
    "TEMPERATURE": ["temperature 18 degrees"],
    "BRIGHTNESS": ["brightness 20 percent"],
    "COLOR": ["change color to red"],
}


def main() -> int:
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
        phrases = data["phrases"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print("READ " + type(exc).__name__)
        return 1
    existing = {row["phrase"] for row in phrases}
    for intent, forms in SHORT_FORMS.items():
        insert_at = next((i for i, row in enumerate(phrases) if row["intent"] == intent), None)
        for form in reversed(forms):
            if form in existing:
                continue
            row = {"phrase": form, "intent": intent}
            if insert_at is None:
                phrases.append(row)
            else:
                phrases.insert(insert_at, row)
                insert_at += 1
    data["phrases"] = phrases
    try:
        PATH.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    except OSError as exc:
        print("WRITE " + type(exc).__name__)
        return 1
    print("PHRASES=" + str(len(phrases)))
    for intent in sorted({row["intent"] for row in phrases}):
        mine = [row["phrase"] for row in phrases if row["intent"] == intent]
        print("  " + intent + " (" + str(len(mine)) + "): " + "; ".join(mine[:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
