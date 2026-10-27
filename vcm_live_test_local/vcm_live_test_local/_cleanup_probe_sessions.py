"""Remove probe-created session folders and their takes from the index."""

import json
import pathlib
import shutil

STORE = pathlib.Path(__file__).resolve().parent / "recordings"
INDEX = STORE / "index.json"


def main() -> int:
    folder = STORE / "sessions"
    removed_ids: list[str] = []
    take_ids: list[str] = []
    if folder.is_dir():
        for child in folder.iterdir():
            if not child.is_dir():
                continue
            meta_path = child / "session.json"
            if not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            sid = str(meta.get("id") or child.name)
            label = str(meta.get("label") or "")
            if sid.startswith("20261027_03") and label.startswith("session 2026-10-27"):
                take_ids += [p.stem.split("_")[0] for p in child.glob("*.wav")]
                try:
                    shutil.rmtree(child)
                except OSError:
                    pass
                removed_ids.append(sid)
    if removed_ids:
        try:
            entries = json.loads(INDEX.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            entries = []
        if isinstance(entries, list):
            prefix = tuple(take_ids)
            try:
                kept = [e for e in entries if not (str(e.get("id") or "").startswith(prefix))]
                INDEX.write_text(json.dumps(kept, indent=2), encoding="utf-8")
            except OSError:
                pass
    print("REMOVED_SESSIONS=" + str(removed_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
