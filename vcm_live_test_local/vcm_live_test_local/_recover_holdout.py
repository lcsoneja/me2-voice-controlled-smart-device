"""Recover a consistent holdout state after archive/restore churn.

Finds the archive folder that actually holds the wave files, resets the index to a
clean list, and restores from it so every index row has its audio on disk.
"""

import json
import pathlib
import shutil

HERE = pathlib.Path(__file__).resolve().parent
STORE = HERE / "recordings"
INDEX = STORE / "index.json"


def main() -> int:
    archives = sorted(STORE.glob("_archive_me2h_holdout_*"))
    best: tuple[pathlib.Path, list[pathlib.Path]] | None = None
    for folder in archives:
        wavs = list(folder.glob("*.wav"))
        if best is None or len(wavs) > len(best[1]):
            best = (folder, wavs)
    if best is None or not best[1]:
        print("NO_ARCHIVE_WITH_WAVS")
        return 1
    folder, wavs = best
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        archived = manifest["archived"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print("BAD_MANIFEST " + str(folder) + " " + type(exc).__name__)
        return 1
    print(
        "SOURCE="
        + folder.name
        + " wavs="
        + str(len(wavs))
        + " entries="
        + str(len(archived))
    )
    restored = 0
    for entry in archived:
        source = folder / str(entry.get("file") or "")
        if not source.is_file():
            continue
        target = STORE / source.name
        if target.is_file():
            restored += 1
            continue
        try:
            shutil.move(str(source), str(target))
        except OSError as exc:
            print("MOVE_FAILED " + source.name + " " + type(exc).__name__)
            continue
        restored += 1
    try:
        INDEX.write_text(json.dumps(archived, indent=2), encoding="utf-8")
    except OSError as exc:
        print("INDEX_WRITE_FAILED " + type(exc).__name__)
        return 1
    print("INDEX=" + str(len(archived)) + " wav_present=" + str(restored))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
