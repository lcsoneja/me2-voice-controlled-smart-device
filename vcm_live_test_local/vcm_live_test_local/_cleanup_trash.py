"""Remove probe trash artifacts and their manifest entries."""

import json
import pathlib
import shutil

APP = pathlib.Path(__file__).resolve().parent
STORE = APP / "recordings"
MANIFEST = STORE / "trash_manifest.json"
PREFIXES = ("_trash_20261027_0951",)


def main() -> int:
    removed_dirs = 0
    for folder in STORE.glob("_trash_*"):
        if not folder.name.startswith(PREFIXES):
            continue
        try:
            shutil.rmtree(folder)
        except OSError:
            pass
        removed_dirs += 1
    history: list = []
    if MANIFEST.is_file():
        try:
            raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = []
        if isinstance(raw, list):
            history = [
                entry for entry in raw
                if not str(entry.get("label") or "").startswith("trash probe")
            ]
    try:
        MANIFEST.write_text(json.dumps(history, indent=1), encoding="utf-8")
    except OSError:
        pass
    print("TRASH_DIRS_REMOVED=" + str(removed_dirs)
          + " manifest_left=" + str(len(history)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
