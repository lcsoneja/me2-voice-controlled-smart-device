"""Find which registry entry fails label loading, and how its labels.json is shaped."""

import json

import gate1_server as gs


def label_file_for(name: str):
    pkg, _rel, spec_dir = gs.GATE2_PACKAGE_RUNNERS[name]
    path = pkg / "labels.json"
    if not path.is_file() and spec_dir is not None:
        path = spec_dir / "labels.json"
    return pkg, spec_dir, path


def load_labels(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    labels = raw["labels"] if isinstance(raw, dict) else raw
    if not isinstance(labels, list):
        raise TypeError("labels is not a list")
    return labels


def main() -> int:
    names = sorted(gs.GATE2_PACKAGE_RUNNERS)
    print("total=" + str(len(names)) + " #89=" + names[88])
    bad = []
    for index, name in enumerate(names, 1):
        _pkg, _spec, path = label_file_for(name)
        try:
            labels = load_labels(path)
            if not labels:
                raise ValueError("empty label list")
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            bad.append((index, name, path, type(exc).__name__))
            print(
                "BAD #"
                + str(index)
                + " "
                + name.ljust(34)
                + " "
                + type(exc).__name__
                + "  labels_path="
                + path.name
            )
    print("bad_count=" + str(len(bad)))
    for index, name, path, kind in bad:
        pkg, spec_dir, _path = label_file_for(name)
        own = pkg / "labels.json"
        print(
            name
            + " own_labels="
            + str(own.is_file())
            + " spec_dir="
            + str(spec_dir.name if spec_dir else None)
            + " used="
            + path.parent.name
            + "/"
            + path.name
        )
        if own.is_file():
            text = own.read_text(encoding="utf-8")
            print("   own_first100=" + text[:100].replace(chr(10), " "))
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            print("   used_first100=" + text[:100].replace(chr(10), " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
