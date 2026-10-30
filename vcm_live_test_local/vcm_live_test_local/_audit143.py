"""Thorough Shipping audit: every dir whose name contains any version >= 143,
regardless of prefix case, vs what the registry actually points at."""

import importlib
import pathlib
import re
import sys

sys.path.insert(
    0,
    r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local",
)
gs = importlib.import_module("gate1_server")

SHIP = pathlib.Path(
    r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/Shipping"
)
registered_dirs = {
    pathlib.Path(entry[0]).resolve().name for entry in gs.GATE2_PACKAGE_RUNNERS.values()
}

missing = []
total = 0
for base in (SHIP, SHIP / "Shipping Container 1"):
    if not base.is_dir():
        continue
    for pkg in sorted(base.iterdir()):
        if not pkg.is_dir():
            continue
        m = re.search(r"[Gg]ate2[Vv](\d+)", pkg.name)
        if not m or int(m.group(1)) < 143:
            continue
        total += 1
        if pkg.name not in registered_dirs:
            tfl = sorted(pkg.rglob("*.tflite"))
            missing.append((pkg.name, len(tfl)))
print(
    "dirs_with_version_ge_143="
    + str(total)
    + " registered="
    + str(total - len(missing))
    + " missing_from_registry="
    + str(len(missing))
)
for name, n in missing:
    print("  MISSING " + name + " tflite=" + str(n))

reg_ge_143 = sorted(
    k for k in gs.GATE2_PACKAGE_RUNNERS if re.search(r"v(1[4-9][0-9]|[2-9]\d\d)", k)
)
print("registry_keys_ge_v143=" + str(len(reg_ge_143)))
