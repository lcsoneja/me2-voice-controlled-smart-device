"""Full inventory of Shipping: every package, its weights, its status."""

import pathlib
import re

import gate1_server as gs

REG = set(gs.GATE2_PACKAGE_RUNNERS)
DISABLED = set(gs.GATE2_DISABLED_CANDIDATES)
SHIP = gs.SHIP_DIR
NESTED = SHIP / "Shipping Container 1"


def folder_status(pkg: pathlib.Path) -> str:
    keys = [k for k, v in gs.GATE2_PACKAGE_RUNNERS.items()
            if pathlib.Path(v[0]).resolve() == pkg.resolve()]
    if keys:
        return "REGISTERED:" + ",".join(keys)
    low = pkg.name.lower()
    if any(k in low for k in DISABLED):
        return "documented-disabled"
    if "INVALID" in pkg.name:
        return "marked-INVALID"
    return "UNREGISTERED"


def main() -> int:
    for root, label in ((SHIP, "MAIN"), (NESTED, "NESTED 'Shipping Container 1'")):
        if not root.is_dir():
            continue
        print("=== " + label + " ===")
        for pkg in sorted(root.glob("*")):
            if not pkg.is_dir():
                continue
            tflites = sorted(pkg.rglob("*.tflite"))
            markers = [m.name for m in pkg.glob("*.md")
                       if m.name in ("INVALID.md", "NO_TFLITE_REASON.md", "HANDOFF.md")]
            status = folder_status(pkg)
            if not tflites and not markers:
                continue
            print("  " + pkg.name[:56].ljust(56)
                  + " tflite=" + str(len(tflites)).rjust(2)
                  + " " + status
                  + ("  [" + ",".join(markers) + "]" if markers else ""))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
