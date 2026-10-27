"""Every Shipping package with weights, mapped to registry status."""

import pathlib

import gate1_server as gs

packages = sorted(gs.SHIP_DIR.glob("*"), key=lambda p: p.name)
disabled_keys = set(gs.GATE2_DISABLED_CANDIDATES)
print("=== packages with tflite and their status ===")
for pkg in packages:
    if not pkg.is_dir():
        continue
    tflites = sorted(pkg.rglob("*.tflite"))
    if not tflites:
        continue
    keys = [
        key
        for key, value in gs.GATE2_PACKAGE_RUNNERS.items()
        if pathlib.Path(value[0]).resolve() == pkg.resolve()
    ]
    if keys:
        status = "REGISTERED"
    elif any(key in pkg.name.lower() for key in disabled_keys):
        status = "DISABLED-CANDIDATE"
    else:
        status = "UNREGISTERED"
    print(pkg.name + "  tflite=" + str(len(tflites)) + "  " + status)
    for tflite in tflites[:3]:
        print("    " + tflite.parent.name + "/" + tflite.name)
