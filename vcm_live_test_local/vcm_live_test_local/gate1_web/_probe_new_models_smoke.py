"""Smoke-test newly registered Gate2 adapters on silence (plumbing only, not accuracy)."""
import gate1_server as server
import numpy as np

SILENCE = np.zeros(96000, dtype=np.float32)
NEW_MODELS = sorted(
    name for name in server.GATE2_PACKAGE_RUNNERS
    if name not in {
        "gate2v16", "gate2v18", "gate2v19", "gate2v19p",
        "gate2v21", "gate2v21p", "gate2v22", "gate2v22s",
    }
)

results = []
for name in NEW_MODELS:
    try:
        runner = server.Gate2PackageRunner(name)
        scores = runner.predict(SILENCE)
        ok = len(scores) == len(runner.labels) and bool(np.isfinite(scores).all())
        results.append({"model": name, "outputs": len(scores), "labels": len(runner.labels), "ok": ok, "error": None})
    except (OSError, RuntimeError, ValueError) as exc:
        results.append({"model": name, "outputs": None, "labels": None, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    print(results[-1])

try:
    v56 = server.Gate2PackageRunner("gate2v56_v54")
    clip = v56.predict_pid_clip(SILENCE, "gate2v56_v54")
    clip_ok = len(clip) == len(v56.labels) + 1
except (OSError, RuntimeError, ValueError) as exc:
    clip = []
    clip_ok = False
    print({"pid_clip": f"{type(exc).__name__}: {exc}"})
print({"pid_clip_outputs": len(clip), "pid_clip_ok": clip_ok})
failed = [item for item in results if not item["ok"]] + ([] if clip_ok else [{"model": "gate2v56_v54_pid_clip"}])
print({"summary": f"{len(results) - len([i for i in results if not i['ok']])}/{len(results)} adapter checks passed; pid_clip_ok={clip_ok}", "failed": failed})
if failed:
    raise SystemExit(1)
