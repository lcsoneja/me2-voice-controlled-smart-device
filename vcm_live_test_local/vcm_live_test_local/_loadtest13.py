"""Load-test every candidate through the real Gate2PackageRunner logic."""

import json

import gate1_server as gs

SHIP = gs.SHIP_DIR
NESTED = SHIP / "Shipping Container 1"
V64D = SHIP / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022"
V69 = SHIP / "Gate2V69_ship_EXPERIMENTAL_20261022"

CANDIDATES = [
    ("gate2v120_timewarp", SHIP / "Gate2V120_TimeWarp_ship_EXPERIMENTAL_20261027",
     "tflite/gate2v120_timewarp_float16.tflite", None),
    ("gate2v121b_specaugonly", SHIP / "Gate2V121B_SpecAugOnly_ship_EXPERIMENTAL_20261027",
     "tflite/gate2v121b_specaug_only_float16.tflite", None),
    ("gate2v126_mels180", SHIP / "Gate2V126_Mels180_ship_EXPERIMENTAL_20261027",
     "tflite/gate2v126_mels180_float16.tflite", None),
    ("gate2v129_kw", SHIP / "Gate2V129_KW_ship_EXPERIMENTAL_20261029",
     "tflite/gate2v129_kw_float16.tflite", None),
    ("gate2v131_multiscaleauxkw", SHIP / "Gate2V131_MultiScaleAuxKW_ship_EXPERIMENTAL_20261027",
     "tflite/gate2v131_multiscale_aux_kw_float16.tflite", None),
    ("gate2v132_singlewordmassive", SHIP / "Gate2V132_SingleWordMassive_ship_EXPERIMENTAL_20261027",
     "tflite/gate2v132_single_word_massive_float16.tflite", None),
    ("gate2v19p2_owner_vc", NESTED / "Gate2V19P2_OwnerVC_ship_EXPERIMENTAL_20261029",
     "tflite/gate2v19p2_owner_vc_finetune_float16.tflite", V69),
    ("gate2v21p2_owner_vc", NESTED / "Gate2V21P2_OwnerVC_ship_EXPERIMENTAL_20261029",
     "tflite/gate2v21p2_owner_vc_finetune_float16.tflite", V64D),
    ("gate2v142_121b_ownerft", NESTED / "Gate2v142_121b_specaug_only_OwnerFT_ship_EXPERIMENTAL_20261028",
     "tflite/gate2v142_121b_specaug_only_ownerft_float16.tflite", V64D),
    ("gate2v142_129_kw_ownerft", NESTED / "Gate2v142_129_kw_OwnerFT_ship_EXPERIMENTAL_20261028",
     "tflite/gate2v142_129_kw_ownerft_float16.tflite", V64D),
    ("gate2v142_132_singleword_ownerft", NESTED / "Gate2v142_132_singleword_OwnerFT_ship_EXPERIMENTAL_20261028",
     "tflite/gate2v142_132_singleword_ownerft_float16.tflite", V64D),
    ("gate2v142_135_distilled_ownerft", NESTED / "Gate2v142_135_distilled_OwnerFT_ship_EXPERIMENTAL_20261028",
     "tflite/gate2v142_135_distilled_ownerft_float16.tflite", V64D),
]


def own_labels(pkg):
    path = pkg / "labels.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("labels")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def main() -> int:
    for key, pkg, rel, fallback in CANDIDATES:
        if not (pkg / rel).is_file():
            print("MISSING   " + key + "  (" + rel + ")")
            continue
        labels = own_labels(pkg)
        gs.GATE2_PACKAGE_RUNNERS[key] = (pkg, rel, fallback)
        try:
            runner = gs.Gate2PackageRunner(key)
            print("LOAD_OK   " + key.ljust(32)
                  + " labels=" + str(len(runner.labels))
                  + " ch=" + str(runner.channels)
                  + " mels=" + str(runner.n_mels)
                  + " own_labels=" + str(len(labels) if labels else 0))
        except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print("LOAD_FAIL " + key.ljust(32) + " " + type(exc).__name__ + ": " + str(exc)[:150])
        finally:
            gs.GATE2_PACKAGE_RUNNERS.pop(key, None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
