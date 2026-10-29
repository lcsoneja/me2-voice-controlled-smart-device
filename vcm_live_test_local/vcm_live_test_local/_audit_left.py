"""Final Shipping audit: any tflite-bearing package neither registered nor documented?"""

import pathlib

import gate1_server as gs

SHIP = gs.SHIP_DIR

def main() -> int:
    registered_dirs = {pathlib.Path(v[0]).resolve() for v in gs.GATE2_PACKAGE_RUNNERS.values()}
    leftovers = []
    for pkg in sorted(SHIP.glob("*")):
        if not pkg.is_dir() or pkg.name == "Shipping Container 1":
            continue
        tflites = sorted(pkg.rglob("*.tflite"))
        if not tflites:
            continue
        if pkg.resolve() in registered_dirs:
            continue
        low = pkg.name.lower()
        doc = next((k for k in gs.GATE2_DISABLED_CANDIDATES if k in low), None)
        leftovers.append((pkg.name, len(tflites), doc))
    print("tflite-bearing packages NOT registered: " + str(len(leftovers)))
    for name, count, doc in leftovers:
        print("  " + name[:58].ljust(58) + " tflite=" + str(count)
              + "  documented_as=" + str(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
