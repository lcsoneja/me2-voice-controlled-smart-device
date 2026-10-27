"""Focused check of the confirmed-new candidate tflites."""

import json

import numpy as np
import tensorflow as tf

import gate1_server as gs

CANDIDATES = [
    (
        "gate2v69",
        "Gate2V69_ship_EXPERIMENTAL_20261022",
        "tflite/v69_float16.tflite",
        None,
    ),
    (
        "gate2v70",
        "Gate2V70_ship_EXPERIMENTAL_20261022",
        "tflite/v70_float16.tflite",
        None,
    ),
    (
        "gate2v71",
        "Gate2V71_ship_EXPERIMENTAL_20261022",
        "tflite/v71_float16.tflite",
        None,
    ),
    (
        "gate2v86_speechoos_mid",
        "Gate2V86_SpeechOOSMid_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v86_speechoos_mid_float16.tflite",
        "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    (
        "gate2v86b_v77mix",
        "Gate2V86B_V77mix_from_V64d_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v86b_v77mix_from_v64d_float16.tflite",
        "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    (
        "gate2v87_combo_intent",
        "Gate2V87_Combo_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v87_combo_intent_float16.tflite",
        "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    (
        "gate2v93b_depthdetail",
        "Gate2V124_Ensemble4way_ship_DEPLOY_20261027",
        "tflite/gate2v93b_depth_detail_float16.tflite",
        "Gate2V124_Ensemble4way_ship_DEPLOY_20261027",
    ),
]


def counts(path) -> tuple[int, bool]:
    labels = path / "labels.json"
    spec = path / "preprocessing_spec.json"
    count = -1
    if labels.is_file():
        try:
            count = len(json.loads(labels.read_text(encoding="utf-8"))["labels"])
        except (OSError, json.JSONDecodeError, KeyError):
            count = -1
    return count, spec.is_file()


def main() -> int:
    for name, folder, rel, fallback in CANDIDATES:
        pkg = gs.SHIP_DIR / folder
        tflite = pkg / rel
        if not tflite.is_file():
            print("MISSING " + name)
            continue
        try:
            interp = tf.lite.Interpreter(model_path=str(tflite))
            interp.allocate_tensors()
            out_count = int(np.prod(interp.get_output_details()[0]["shape"]))
            shape = tuple(int(d) for d in interp.get_input_details()[0]["shape"])
        except Exception as exc:
            print("LOAD_FAIL " + name + " " + type(exc).__name__)
            continue
        label_count, spec_ok = counts(pkg)
        source = "in-pkg"
        if label_count != out_count or not spec_ok:
            base = gs.SHIP_DIR / (fallback or "")
            label_count, spec_ok = counts(base)
            source = "fallback:" + (fallback or "")
        ok = out_count == label_count and spec_ok
        print(
            ("PASS " if ok else "SKIP ")
            + name
            + " out="
            + str(out_count)
            + " labels="
            + str(label_count)
            + " spec="
            + source
            + " in="
            + str(shape)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
