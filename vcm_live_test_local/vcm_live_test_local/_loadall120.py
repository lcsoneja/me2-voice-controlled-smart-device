"""Load every registered Gate2 model through the real runner. Read-only."""

import importlib
import sys
import time

sys.path.insert(0, r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local")

gs = importlib.import_module("gate1_server")


def main() -> int:
    names = sorted(gs.GATE2_PACKAGE_RUNNERS)
    print("registered=" + str(len(names)))
    failed = []
    started = time.time()
    for name in names:
        try:
            gs.Gate2PackageRunner(name)
        except Exception as err:  # every failure shape matters here
            failed.append(name)
            print("FAIL " + name + ": " + type(err).__name__ + " " + str(err)[:100])
    print("loaded_ok=" + str(len(names) - len(failed)) + " failed=" + str(len(failed))
          + " in " + str(round(time.time() - started, 1)) + "s")
    for name in failed:
        print("  failed: " + name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
