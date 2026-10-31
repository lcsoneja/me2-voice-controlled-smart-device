"""Probe v169-v174 through the real app runner (read-only, in memory)."""

import importlib
import pathlib
import sys

sys.path.insert(0, r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local")
gs = importlib.import_module("gate1_server")

SHIP = pathlib.Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/Shipping")
DATE = "2026103"

def main() -> int:
    found = 0
    for pkg in sorted(SHIP.glob("Gate2V17*")):
        if not pkg.is_dir():
            continue
        tflites = sorted(pkg.rglob("*.tflite"))
        if not tflites:
            print("SKIP  " + pkg.name + " (no tflite)")
            continue
        found += 1
        rel = tflites[0].relative_to(pkg).as_posix()
        slug = pkg.name.split("_ship_")[0].lower()
        gs.GATE2_PACKAGE_RUNNERS[slug] = (pkg, rel, None)
        try:
            runner = gs.Gate2PackageRunner(slug)
            print("PASS  " + slug.ljust(30) + " channels=" + str(runner.channels)
                  + " mel=" + str(runner.n_mels) + " labels=" + str(len(runner.labels)))
            print('    entry: ("' + slug + '", "' + pkg.name + '", "' + rel + '")')
        except Exception as err:
            print("FAIL  " + slug + " :: " + type(err).__name__ + " " + str(err)[:120])
    print("probed=" + str(found))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
