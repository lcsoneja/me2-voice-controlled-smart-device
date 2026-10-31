"""Probe v169 alone (the earlier glob skipped it) + report its interface."""

import importlib
import pathlib
import sys

sys.path.insert(0, r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local")
gs = importlib.import_module("gate1_server")

pkg = pathlib.Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/Shipping") / "Gate2V169_AttnPool_ship_EXPERIMENTAL_20261030"
tfl = min(pkg.rglob("*.tflite"))
rel = tfl.relative_to(pkg).as_posix()
gs.GATE2_PACKAGE_RUNNERS["gate2v169_attnpool"] = (pkg, rel, None)
try:
    runner = gs.Gate2PackageRunner("gate2v169_attnpool")
    print("PASS  gate2v169_attnpool channels=" + str(runner.channels) + " mel=" + str(runner.n_mels)
          + " labels=" + str(len(runner.labels)))
    print('entry: ("gate2v169_attnpool", "' + pkg.name + '", "' + rel + '")')
except Exception as err:
    print("FAIL gate2v169_attnpool :: " + type(err).__name__ + " " + str(err)[:140])
