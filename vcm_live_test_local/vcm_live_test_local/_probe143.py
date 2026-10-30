"""Probe: can every v143+ shipping package run through the real app runner?

Registers each package in memory (nothing persisted), builds Gate2PackageRunner,
and prints the exact registry entry text for the ones that load. Failures carry
the exception text so they can be fixed or documented as disabled.
"""

import pathlib
import re
import sys

sys.path.insert(0, r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local")

import gate1_server as gs

SHIP = pathlib.Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/Shipping")

def slug(dirname: str) -> str:
    core = re.sub(r"_ship_.*$", "", dirname)
    return core.lower().replace(" ", "_")

def main() -> int:
    entries = []
    for pkg in sorted(SHIP.glob("Gate2V*")):
        m = re.match(r"Gate2V(\d+)([a-zA-Z]*)", pkg.name)
        if not m or int(m.group(1)) < 143:
            continue
        tflites = sorted(pkg.rglob("*.tflite"))
        if not tflites:
            print("SKIP  " + pkg.name + " (no tflite)")
            continue
        rel = tflites[0].relative_to(pkg).as_posix()
        name = slug(pkg.name)
        gs.GATE2_PACKAGE_RUNNERS[name] = (pkg, rel, None)
        try:
            runner = gs.Gate2PackageRunner(name)
            lab = len(runner.labels)
            note = ("channels=" + str(runner.channels) + " mel=" + str(runner.n_mels)
                    + " frames=" + str(runner.frames) + " labels=" + str(lab))
            print("PASS  " + name.ljust(34) + " " + note)
            entries.append((name, pkg.name, rel))
        except Exception as err:  # probe: report every failure shape
            print("FAIL  " + name.ljust(34) + " " + type(err).__name__ + ": " + str(err)[:110])
    print()
    print("== registry entries for gate1_server.py ==")
    for name, dirname, rel in entries:
        print('    "' + name + '": (')
        print('        SHIP_DIR / "' + dirname + '",')
        print('        "' + rel + '",')
        print('        None,')
        print('    ),')
    print("total_pass=" + str(len(entries)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
