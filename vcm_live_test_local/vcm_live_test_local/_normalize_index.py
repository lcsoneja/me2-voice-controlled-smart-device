"""Reset the take index to the holdout bank, dropping leaked probe takes.

Keeps every me2h (holdout) row and removes rows whose audio is not part of the
bank, then deletes the leftover wav files to match.
"""

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
    keep = [e for e in entries if str(e.get("id") or "").startswith("me2h")]
    dropped = len(entries) - len(keep)
    removed_files = 0
    for entry in entries:
        if str(entry.get("id") or "").startswith("me2h"):
            continue
        path = STORE / str(entry.get("file") or "")
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
            removed_files += 1
    try:
        INDEX.write_text(json.dumps(keep, indent=2), encoding="utf-8")
    except OSError as exc:
        print("INDEX_WRITE " + type(exc).__name__)
        return 1
    print("KEPT=" + str(len(keep)) + " dropped=" + str(dropped)
          + " files_removed=" + str(removed_files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
