"""Drop index rows whose wav file no longer exists (probe-run orphans only)."""

import json
import pathlib

STORE = pathlib.Path(__file__).resolve().parent / "recordings"
INDEX = STORE / "index.json"


def main() -> int:
    try:
        entries = json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("INDEX_READ " + type(exc).__name__)
        return 1
    if not isinstance(entries, list):
        print("INDEX_FORMAT")
        return 1
    kept = []
    dropped = 0
    for entry in entries:
        path = STORE / str(entry.get("file") or "")
        if path.is_file():
            kept.append(entry)
        else:
            dropped += 1
    try:
        INDEX.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    except OSError as exc:
        print("INDEX_WRITE " + type(exc).__name__)
        return 1
    print("KEPT=" + str(len(kept)) + " orphan_rows_dropped=" + str(dropped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
