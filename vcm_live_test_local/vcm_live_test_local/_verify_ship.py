"""Verify the shipped session package."""

import json
import pathlib

SHIPPING = pathlib.Path(__file__).resolve().parent.parent / "Shipping"
packages = sorted(SHIPPING.glob("VoiceSessions_ship_*"))
if not packages:
    print("NO_PACKAGE")
    raise SystemExit(1)
package = packages[-1]
print("PACKAGE=" + str(package.relative_to(SHIPPING)))
total = 0.0
for sub in sorted(package.iterdir()):
    if not sub.is_dir():
        continue
    wavs = list((sub / "audio").glob("*.wav"))
    results = json.loads((sub / "results.json").read_text(encoding="utf-8"))
    scored = results["takes"]
    free = sum(1 for t in scored if not (t.get("intent") or "").strip())
    with_action = len(scored) - free
    per_model = len(scored[0]["results"]) if scored else 0
    size_mb = sum(path.stat().st_size for path in sub.rglob("*")) / (1 << 20)
    total += size_mb
    print(str(sub.name) + ": wavs=" + str(len(wavs)) + " scored=" + str(len(scored))
          + " with_expected_intent=" + str(with_action) + " free=" + str(free)
          + " per_model=" + str(per_model) + " size_mb=" + str(round(size_mb, 1)))
    print("  files=" + ",".join(sorted(path.name for path in sub.iterdir())))
print("TOTAL_MB=" + str(round(total, 1)))
