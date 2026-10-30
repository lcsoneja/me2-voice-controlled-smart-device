import pathlib
import re

SHIP = pathlib.Path(r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/Shipping")
out = []
for pkg in sorted(SHIP.glob("Gate2V*")):
    m = re.match(r"Gate2V(\d+)([a-zA-Z]*)", pkg.name)
    if not m or int(m.group(1)) < 143:
        continue
    tfl = min(pkg.rglob("*.tflite"))
    rel = tfl.relative_to(pkg).as_posix()
    name = re.sub(r"_ship_.*$", "", pkg.name).lower()
    out.append('    "' + name + '": (\n        SHIP_DIR / "' + pkg.name + '",\n        "' + rel + '",\n        None,\n    ),')
print("\n".join(out))
