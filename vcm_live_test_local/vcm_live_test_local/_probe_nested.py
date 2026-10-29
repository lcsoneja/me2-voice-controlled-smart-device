"""Probe the 9 nested-only packages (the new v1xx/v142 batch)."""

import json
import pathlib

import numpy as np
import tensorflow as tf

import gate1_server as gs

NESTED = gs.SHIP_DIR / "Shipping Container 1"
TARGETS = [
    "Gate2V19P2_OwnerVC_ship_EXPERIMENTAL_20261029",
    "Gate2V21P2_OwnerVC_ship_EXPERIMENTAL_20261029",
    "Gate2V66b_18extra_ship_EXPERIMENTAL_20261022",
    "Gate2V121_SpecAugMixup_ship_EXPERIMENTAL_20261027",
    "Gate2V122_V20paModern_ship_EXPERIMENTAL_20261027",
    "Gate2v142_121b_specaug_only_OwnerFT_ship_EXPERIMENTAL_20261028",
    "Gate2v142_129_kw_OwnerFT_ship_EXPERIMENTAL_20261028",
    "Gate2v142_132_singleword_OwnerFT_ship_EXPERIMENTAL_20261028",
    "Gate2v142_135_distilled_OwnerFT_ship_EXPERIMENTAL_20261028",
]
CHANNELS_OK = {1, 5, 9, 17}
BASES = {
    20: gs.SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    19: gs.SHIP_DIR / "Gate2V69_ship_EXPERIMENTAL_20261022",
}


def label_count(folder: pathlib.Path) -> int:
    path = folder / "labels.json"
    if not path.is_file():
        return -1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return -1
    labels = data.get("labels") if isinstance(data, dict) else None
    return len(labels) if isinstance(labels, list) else -1


def main() -> int:
    base = {n: label_count(p) for n, p in BASES.items()}
    for name in TARGETS:
        pkg = NESTED / name
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
        own_labels = label_count(pkg)
        own_spec = (pkg / "preprocessing_spec.json").is_file()
        fallback = next((n for n, c in base.items() if c == out_n and c > 0), None)
        ok = (len(ins) == 1 and len(outs) == 1 and len(shape) == 4
              and shape[3] in CHANNELS_OK and fallback is not None)
        print(("PASS " if ok else "SKIP ") + name[:50].ljust(50)
              + " " + str(shape) + " out=" + str(out_n)
              + " labels=" + str(own_labels) + " spec=" + str(own_spec)
              + " fb=" + str(fallback))
        print("        tflite=" + tflite.relative_to(pkg).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
