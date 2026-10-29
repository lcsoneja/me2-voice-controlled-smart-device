"""Load every newly registered model through the real registry."""

import gate1_server as gs

NEW = [
    "gate2v120_timewarp",
    "gate2v121b_specaugonly",
    "gate2v126_mels180",
    "gate2v129_kw",
    "gate2v131_multiscaleauxkw",
    "gate2v132_singlewordmassive",
    "gate2v19p2_owner_vc",
    "gate2v21p2_owner_vc",
    "gate2v142_121b_ownerft",
    "gate2v142_129_kw_ownerft",
    "gate2v142_132_singleword_ownerft",
    "gate2v142_135_distilled_ownerft",
]


def main() -> int:
    ok = 0
    for key in NEW:
        if key not in gs.GATE2_PACKAGE_RUNNERS:
            print("NOT_REGISTERED " + key)
            continue
        try:
            runner = gs.Gate2PackageRunner(key)
        except (OSError, RuntimeError, ValueError, KeyError, ImportError) as exc:
            print(
                "FAIL "
                + key.ljust(32)
                + " "
                + type(exc).__name__
                + ": "
                + str(exc)[:110]
            )
            continue
        print(
            "OK   "
            + key.ljust(32)
            + " labels="
            + str(len(runner.labels))
            + " last="
            + str(runner.labels[-1])
            + " ch="
            + str(runner.channels)
            + " mels="
            + str(runner.n_mels)
            + " frames="
            + str(runner.frames)
        )
        ok += 1
        del runner
    print(
        "LOADED "
        + str(ok)
        + "/"
        + str(len(NEW))
        + "  registry_total="
        + str(len(gs.GATE2_PACKAGE_RUNNERS))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
