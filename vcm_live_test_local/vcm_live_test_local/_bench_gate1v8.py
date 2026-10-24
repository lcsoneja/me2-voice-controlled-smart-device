import sys
import time

import numpy as np

sys.path.insert(0, ".")
import gate1_server as gs

rng = np.random.default_rng(7)
win = (rng.standard_normal(gs.WIN_SAMPLES) * 0.03).astype(np.float32)
gates = gs.Gates()

def full_latency(key: str, runs: int = 30) -> float:
    for _ in range(3):
        gates.infer_g1_variant(key, win)
    t0 = time.perf_counter()
    for _ in range(runs):
        gates.infer_g1_variant(key, win)
    return (time.perf_counter() - t0) / runs * 1000.0

for key in ("gate1v8_f32", "gate1v8_f16"):
    print(f"{key} preprocess+inference: {full_latency(key):.2f} ms")

# inference-only for f32: features extracted once, interpreter invoked repeatedly
g = gates.g1_variants["gate1v8_f32"]
feats = g["pre"].extract(win).astype(g["in_dtype"])
g["interp"].set_tensor(g["in_idx"], feats)
for _ in range(3):
    g["interp"].invoke()
t0 = time.perf_counter()
for _ in range(50):
    g["interp"].invoke()
print(f"gate1v8_f32 inference-only: {(time.perf_counter() - t0) / 50 * 1000.0:.2f} ms")

feats16 = gates.g1_variants["gate1v8_f16"]
feats16["interp"].set_tensor(feats16["in_idx"], feats16["pre"].extract(win).astype(feats16["in_dtype"]))
for _ in range(3):
    feats16["interp"].invoke()
t0 = time.perf_counter()
for _ in range(50):
    feats16["interp"].invoke()
print(f"gate1v8_f16 inference-only: {(time.perf_counter() - t0) / 50 * 1000.0:.2f} ms")
print(f"window: {gs.WIN_SAMPLES / gs.SR:.2f} s | params ~413.6k")
