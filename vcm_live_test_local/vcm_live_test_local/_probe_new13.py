"""Probe every remaining unregistered candidate in both Shipping locations."""

import json
import pathlib

import numpy as np
import tensorflow as tf

import gate1_server as gs

SHIP = gs.SHIP_DIR
NESTED = SHIP / "Shipping Container 1"
MAIN_TARGETS = [
    "Gate2V120_TimeWarp_ship_EXPERIMENTAL_20261027",
    "Gate2V121B_SpecAugOnly_ship_EXPERIMENTAL_20261027",
    "Gate2V126_Mels180_ship_EXPERIMENTAL_20261027",
    "Gate2V129_KW_ship_EXPERIMENTAL_20261029",
    "Gate2V130_GroupMultiHot_ship_EXPERIMENTAL_20261027",
    "Gate2V131_MultiScaleAuxKW_ship_EXPERIMENTAL_20261027",
    "Gate2V132_SingleWordMassive_ship_EXPERIMENTAL_20261027",
]
CHANNELS_OK = {1, 5, 9, 17}
BASES = {
    20: SHIP / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    19: SHIP / "Gate2V69_ship_EXPERIMENTAL_20261022",
}


def labels_of(folder: pathlib.Path):
    path = folder / "labels.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    labels = data.get("labels") if isinstance(data, dict) else None
    return labels if isinstance(labels, list) else None


def main() -> int:
    base = {}
    for count, folder in BASES.items():
        labels = labels_of(folder)
        base[count] = labels
        print("base " + str(count) + " from " + folder.name[:30]
              + " -> " + (str(labels[:3]) + "..." if labels else "MISSING"))
    print()
    for name in MAIN_TARGETS:
        pkg = SHIP / name
        if not pkg.is_dir():
            print("MISSING   " + name)
            continue
        tflites = sorted(pkg.rglob("*.tflite"))
        if not tflites:
            print("NO_TFLITE " + name)
            continue
        tflite = next((t for t in tflites if "intent" in t.name), tflites[0])
        try:
            interp = tf.lite.Interpreter(model_path=str(tflite))
            interp.allocate_tensors()
            ins = interp.get_input_details()
            outs = interp.get_output_details()
        except Exception as exc:  # report every interpreter failure
            print("LOAD_FAIL " + name + "  " + type(exc).__name__)
            continue
        shape = tuple(int(d) for d in ins[0]["shape"])
        out_n = int(np.prod(outs[0]["shape"]))
        own = labels_of(pkg)
        own_spec = (pkg / "preprocessing_spec.json").is_file()
        base_labels = base.get(out_n)
        ok = (len(ins) == 1 and len(outs) == 1 and len(shape) == 4
              and shape[3] in CHANNELS_OK and base_labels is not None)
        print(("PASS " if ok else "SKIP ") + name[:50].ljust(50)
              + " " + str(shape) + " out=" + str(out_n)
              + " own_labels=" + str(len(own) if own else 0)
              + " spec=" + str(own_spec)
              + " fb=" + str(out_n if base_labels else None))
        print("        " + tflite.relative_to(pkg).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
