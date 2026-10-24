import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local")
import gate1_server as server


def dims(shape) -> tuple[int, ...]:
    """Tensor dims as ints; a probe should fail with a message, not a traceback."""
    try:
        return tuple(int(x) for x in shape)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"probe: unexpected tensor shape {shape!r}") from exc


targets = {
 "gate1v8_f32(registered)": Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local/gate1_web/gate1v8_float32.tflite"),
 "gate1v10_f16(registered)": Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local/gate1_web/gate1v10_float16.tflite"),
 "gate1v12_f16(NEW)": Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/Shipping/Gate1V12_WarpSpecAug_ship_EXPERIMENTAL_20261020/tflite/gate1v12_float16.tflite"),
 "gate1v8c_f16(NEW)": Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/Shipping/Gate1V8C_ship_EXPERIMENTAL_20261020/tflite/gate1v8c_float16.tflite"),
}
for name, path in targets.items():
    if not path.is_file():
        print(name, "MISSING")
        continue
    it = server._make_interpreter(path)
    i = it.get_input_details()[0]
    o = it.get_output_details()[0]
    print(f"{name}: in={dims(i['shape'])} {np.dtype(i['dtype']).name} out={dims(o['shape'])} {np.dtype(o['dtype']).name} bytes={path.stat().st_size}")

for stats in ("feature_stats_v8_148.npz", "feature_stats_v10.npz", "feature_stats_148.npz"):
    for base in (Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local"), Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local/gate1_web")):
        sp = base / stats
        if sp.is_file():
            with np.load(sp) as z:
                print(f"{stats} @ {base.name}: " + " ".join(f"{k}={np.ravel(z[k])[:2]}" for k in z))
            break
    else:
        print(stats, "not found")

print("registered g1_variants:", sorted(server.Gates().g1_variants.keys()))
