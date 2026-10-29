"""Load all 92 registry models after the labels-fix; v87 must now work."""

import gate1_server as gs


def main() -> int:
    names = sorted(gs.GATE2_PACKAGE_RUNNERS)
    ok = 0
    fails = []
    for name in names:
        try:
            runner = (
                gs.Gate2V124EnsembleRunner(name)
                if name == "gate2v124_ensemble4way"
                else gs.Gate2PackageRunner(name)
            )
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, ImportError) as exc:
            fails.append(name + " (" + type(exc).__name__ + ": " + str(exc)[:80] + ")")
            continue
        ok += 1
        del runner
    print("LOADED=" + str(ok) + "/" + str(len(names)))
    v87 = gs.Gate2PackageRunner("gate2v87_combo_intent")
    print("v87 labels=" + str(len(v87.labels)) + " last=" + v87.labels[-1])
    for line in fails:
        print("FAIL " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
