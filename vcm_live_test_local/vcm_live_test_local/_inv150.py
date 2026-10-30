"""Inventory of newest Shipping packages (v143+) vs the app registry."""

import json
import pathlib
import re
import sys

sys.path.insert(
    0,
    r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local",
)

import gate1_server as gs

SHIP = pathlib.Path(
    r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/Shipping"
)
registered = {
    pathlib.Path(v[0]).resolve(): k for k, v in gs.GATE2_PACKAGE_RUNNERS.items()
}

rows = []
for base in (SHIP, SHIP / "Shipping Container 1"):
    if not base.is_dir():
        continue
    for pkg in sorted(base.glob("Gate2V*")):
        m = re.match(r"Gate2V(\d+)([a-zA-Z]*)", pkg.name)
        if not m:
            continue
        ver = int(m.group(1))
        if ver < 143:
            continue
        tflites = sorted(pkg.rglob("*.tflite"))
        spec = pkg / "preprocessing_spec.json"
        labels = pkg / "labels.json"
        has = {"t": len(tflites), "s": spec.is_file(), "l": labels.is_file()}
        n_mels = n_frames = None
        if has["s"]:
            try:
                sp = json.loads(spec.read_text(encoding="utf-8"))
                n_mels = sp.get("n_mels")
                n_frames = sp.get("input_frames") or sp.get("frames")
            except (OSError, json.JSONDecodeError) as err:
                print("  spec unreadable in " + pkg.name + ": " + str(err))
        reg = registered.get(pkg.resolve())
        rows.append((ver, pkg.name, has, n_mels, n_frames, reg, str(pkg.parent.name)))

rows.sort(key=lambda r: (r[0], r[1]))
print("packages v143+: " + str(len(rows)))
for ver, name, has, n_mels, n_frames, reg, parent in rows:
    tag = "REG=" + str(reg) if reg else "unregistered"
    extra = ""
    if has["t"] and reg is None:
        extra = "  <-- candidate"
    print(
        "v"
        + str(ver).ljust(4)
        + " "
        + name[:52].ljust(52)
        + " tflite="
        + str(has["t"])
        + " spec="
        + str(has["s"])
        + " mel="
        + str(n_mels)
        + " frames="
        + str(n_frames)
        + " "
        + tag
        + extra
    )
