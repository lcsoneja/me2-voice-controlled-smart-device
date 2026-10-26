"""Archive recordings out of the active index, reversibly.

Moves the selected entries and their WAV files into recordings/_archive_<name>_<timestamp>/ with a
manifest, then rewrites the index without them. Nothing is deleted, so the Gate 2 ranking can be
re-measured after a restore. The already-computed ranking file is unaffected either way.

    py -3.12 _archive_recordings.py                 # archive every me2h* holdout clip
    py -3.12 _archive_recordings.py --oos-only      # archive only the "ME2 OOS: ..." clips
    py -3.12 _archive_recordings.py --restore <dir> # put an archive back
"""

import argparse
import datetime
import json
import pathlib
import shutil

HERE = pathlib.Path(__file__).resolve().parent
STORE = HERE / "recordings"
INDEX = STORE / "index.json"


def read_index() -> list[dict]:
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "cannot read " + str(INDEX) + ": " + type(exc).__name__
        ) from exc
    return data["recordings"] if isinstance(data, dict) else data


def write_index(entries: list[dict]) -> None:
    # RecordingStore._read() only accepts a bare JSON array; an object would be read as "no
    # recordings" and the lab pane would come up empty.
    INDEX.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def archive(entries: list[dict], keep: list[dict], name: str) -> pathlib.Path:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = STORE / ("_archive_" + name + "_" + stamp)
    target.mkdir(parents=True, exist_ok=True)
    moved = 0
    failed: list[str] = []
    for entry in entries:
        source = STORE / str(entry.get("file") or "")
        if source.is_file():
            try:
                shutil.move(str(source), str(target / source.name))
            except OSError as exc:
                failed.append(source.name + " (" + type(exc).__name__ + ")")
                continue
            moved += 1
    if failed:
        print("move_failed=" + str(len(failed)) + " " + "; ".join(failed[:3]))
    (target / "manifest.json").write_text(
        json.dumps(
            {"archived": entries, "count": len(entries)}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    write_index(keep)
    return target


def restore(folder_arg: pathlib.Path) -> None:
    # Accept either a full path or just the folder name printed by the archive step, which is
    # relative to recordings/.
    folder = folder_arg
    if not (folder / "manifest.json").is_file():
        alternate = STORE / folder_arg.name
        if (alternate / "manifest.json").is_file():
            folder = alternate
    manifest = folder / "manifest.json"
    if not manifest.is_file():
        raise SystemExit("no manifest.json in " + str(folder))
    try:
        archived = json.loads(manifest.read_text(encoding="utf-8"))["archived"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        raise SystemExit(
            "cannot read " + str(manifest) + ": " + type(exc).__name__
        ) from exc
    entries = read_index()
    have = {str(e.get("id")) for e in entries}
    restored = 0
    for entry in archived:
        source = folder / str(entry.get("file") or "")
        if source.is_file():
            try:
                shutil.move(str(source), str(STORE / source.name))
            except OSError as exc:
                print("restore_failed=" + source.name + " (" + type(exc).__name__ + ")")
                continue
        if str(entry.get("id")) not in have:
            entries.append(entry)
            restored += 1
    write_index(entries)
    print("restored=" + str(restored) + " index_now=" + str(len(entries)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--oos-only", action="store_true", help="archive only the ME2 OOS clips"
    )
    parser.add_argument("--restore", metavar="DIR", help="restore an archive folder")
    args = parser.parse_args()

    if args.restore:
        restore(pathlib.Path(args.restore))
        return 0

    entries = read_index()
    if args.oos_only:
        selected = [
            e for e in entries if str(e.get("label") or "").startswith("ME2 OOS")
        ]
        name = "me2_oos"
    else:
        selected = [e for e in entries if str(e.get("id") or "").startswith("me2h")]
        name = "me2h_holdout"
    if not selected:
        print("nothing to archive")
        return 0
    ids = {str(e.get("id")) for e in selected}
    keep = [e for e in entries if str(e.get("id")) not in ids]
    target = archive(selected, keep, name)
    print(
        "archived="
        + str(len(selected))
        + " folder="
        + target.name
        + " index_now="
        + str(len(keep))
    )
    print("restore with: py -3.12 _archive_recordings.py --restore " + target.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
