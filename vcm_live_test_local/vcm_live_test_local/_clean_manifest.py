"""Inspect and clean stale probe rows from the trash manifest."""

import json
import pathlib

STORE = pathlib.Path(__file__).resolve().parent / "recordings"
MANIFEST = STORE / "trash_manifest.json"


def main() -> int:
    if not MANIFEST.is_file():
        print("NO_MANIFEST")
        return 0
    try:
        entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("READ " + type(exc).__name__)
        return 1
    if not isinstance(entries, list):
        entries = []
    print("ENTRIES=" + str(len(entries)))
    for entry in entries:
        print(
            "  id="
            + str(entry.get("id") or "-")[:26]
            + " label="
            + repr(str(entry.get("label") or "")[:36])
            + " session="
            + str(entry.get("deleted_session") or entry.get("session") or "-")
        )
    kept = [
        entry
        for entry in entries
        if not str(entry.get("label") or "").startswith(
            ("probe", "trash probe", "sman probe", "export probe")
        )
    ]
    if len(kept) != len(entries):
        try:
            MANIFEST.write_text(json.dumps(kept, indent=1), encoding="utf-8")
        except OSError:
            pass
        print("CLEANED_TO=" + str(len(kept)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
