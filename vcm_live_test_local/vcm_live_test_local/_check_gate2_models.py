"""Load-check every registered Gate 2 package and report the ones that cannot be built.

The runner raises RuntimeError for packages whose frontend recipe has no adapter, so a plain
registry listing is not enough to know what is actually usable. Run from the app directory:

    py -3.12 _check_gate2_models.py
"""

import traceback

import gate1_server as gs


def main() -> int:
    names = sorted(gs.GATE2_PACKAGE_RUNNERS)
    ok = 0
    fails = []
    for name in names:
        try:
            runner = gs.Gate2PackageRunner(name)
            ok += 1
            print("OK   " + name.ljust(28) + " labels=" + str(len(runner.labels)))
        except Exception as exc:  # report whatever the loader raised
            fails.append(name)
            tail = traceback.format_exc().strip().splitlines()[-3:-1]
            print("FAIL " + name.ljust(28) + type(exc).__name__ + ": " + str(exc)[:130])
            print("     " + " | ".join(line.strip() for line in tail))
    print(
        "TOTAL "
        + str(len(names))
        + " loaded="
        + str(ok)
        + " failed="
        + str(len(fails))
        + " -> "
        + ", ".join(fails)
    )
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
