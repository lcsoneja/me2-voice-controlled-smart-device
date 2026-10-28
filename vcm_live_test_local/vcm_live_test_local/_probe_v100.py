"""Probe every unregistered v100+ package for Gate2PackageRunner loadability."""

import json

import numpy as np
import tensorflow as tf

import gate1_server as gs

CANDIDATES = [
    (
        "gate2v102_distance",
        "Gate2V102_DistanceChannels_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v102_distance_float16.tflite",
    ),
    (
        "gate2v107_distcompact",
        "Gate2V107_DistCompact_ship_EXPERIMENTAL_20261026",
        "tflite/gate2v102_distance_float16.tflite",
    ),
    (
        "gate2v111c_bcresnet",
        "Gate2V111C_BCResNet_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v111c_bcresnet_softmax_float16.tflite",
    ),
    (
        "gate2v112c_gmlp",
        "Gate2V112C_GMLP_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v112c_gmlp_softmax_float16.tflite",
    ),
    (
        "gate2v113c_matchbox",
        "Gate2V113C_Matchbox_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v113c_matchbox_softmax_float16.tflite",
    ),
    (
        "gate2v114_phonemeslots",
        "Gate2V114_PhonemeSlots_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v114_phoneme_slots_float16.tflite",
    ),
    (
        "gate2v116_groupdistance",
        "Gate2V116_GroupDistance_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v116_group_distance_float16.tflite",
    ),
    (
        "gate2v117a_miniecho",
        "Gate2V117A_MiniEcho_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v117a_mini_echo_float16.tflite",
    ),
    (
        "gate2v118_ambienttail",
        "Gate2V118_AmbientTail_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v118_ambient_tail_float16.tflite",
    ),
    (
        "gate2v119a_speedwide",
        "Gate2V119A_SpeedWide_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v119a_speed_wide_float16.tflite",
    ),
    (
        "gate2v119b_speedbounded",
        "Gate2V119B_SpeedBounded_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v119b_speed_bounded_float16.tflite",
    ),
]
BASE20 = gs.SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022"
BASE19 = gs.SHIP_DIR / "Gate2V69_ship_EXPERIMENTAL_20261022"
CHANNELS_OK = {1, 5, 9, 17}


def label_count(folder) -> int:
    path = folder / "labels.json"
    if not path.is_file():
        return -1
    try:
        return len(json.loads(path.read_text(encoding="utf-8"))["labels"])
    except (OSError, json.JSONDecodeError, KeyError):
        return -1


def main() -> int:
    base20 = label_count(BASE20)
    base19 = label_count(BASE19)
    print("fallbacks: V64D=" + str(base20) + " labels, V69=" + str(base19) + " labels")
    for key, folder, rel in CANDIDATES:
        pkg = gs.SHIP_DIR / folder
        tflite = pkg / rel
        if not tflite.is_file():
            print("MISSING   " + key)
            continue
        try:
            interp = tf.lite.Interpreter(model_path=str(tflite))
            interp.allocate_tensors()
            ins = interp.get_input_details()
            outs = interp.get_output_details()
        except Exception as exc:  # probe reports every interpreter load failure
            print("LOAD_FAIL " + key + " " + type(exc).__name__)
            continue
        shape = tuple(int(d) for d in ins[0]["shape"])
        out_n = int(np.prod(outs[0]["shape"]))
        own_labels = label_count(pkg)
        own_spec = (pkg / "preprocessing_spec.json").is_file()
        base_ok = (out_n == base20 and base20 > 0) or (out_n == base19 and base19 > 0)
        ok = (
            len(ins) == 1
            and len(outs) == 1
            and len(shape) == 4
            and shape[3] in CHANNELS_OK
            and base_ok
        )
        print(
            ("PASS " if ok else "SKIP ")
            + key.ljust(24)
            + " in="
            + str(shape)
            + " out="
            + str(out_n)
            + " own_labels="
            + str(own_labels)
            + " own_spec="
            + str(own_spec)
            + " fallback="
            + ("V64D" if out_n == base20 else "V69" if out_n == base19 else "none")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
