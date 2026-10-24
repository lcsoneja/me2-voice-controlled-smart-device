"""Read-only audit of float16 TFLite shapes/contracts in Shipping Gate2 packages."""
import json
from pathlib import Path

import gate1_server as server

ROOT = Path(__file__).resolve().parents[3]
SHIPPING = ROOT / "Shipping"
for package in sorted(SHIPPING.glob("Gate2V*")):
    model_dir = package / "tflite"
    if not model_dir.is_dir():
        continue
    labels_path = package / "labels.json"
    labels = []
    if labels_path.is_file():
        try:
            labels = json.loads(labels_path.read_text(encoding="utf-8")).get("labels", [])
        except (OSError, json.JSONDecodeError):
            pass
    spec_path = package / "preprocessing_spec.json"
    spec = {}
    if spec_path.is_file():
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    for model_path in sorted(model_dir.glob("*float16.tflite")):
        try:
            interpreter = server._make_interpreter(model_path)
            inputs = [list(map(int, x["shape"])) for x in interpreter.get_input_details()]
            outputs = [list(map(int, x["shape"])) for x in interpreter.get_output_details()]
            result = {"package": package.name, "model": model_path.name, "inputs": inputs, "outputs": outputs, "label_count": len(labels), "spec_keys": sorted(spec.keys()), "n_fft": spec.get("n_fft"), "hop": spec.get("hop_length"), "frames": spec.get("input_frames", spec.get("target_frames", spec.get("frames"))), "mels": spec.get("n_mels"), "input_dims": spec.get("input_dims"), "channel_semantics": spec.get("channel_semantics"), "window_coverage": spec.get("window_coverage"), "derived_normalization": spec.get("derived_normalization"), "stats_mean": spec.get("stats_mean"), "stats_std": spec.get("stats_std"), "pipeline": spec.get("pipeline")}
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            result = {"package": package.name, "model": model_path.name, "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(result, separators=(",", ":")))
