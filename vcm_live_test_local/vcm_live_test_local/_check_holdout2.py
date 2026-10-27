import json, pathlib
OUT = pathlib.Path(r"C:\Users\Leandro\Desktop\Leandro\AI 222 and AI 231\Exercise 2\Exercise 2b\vcm_live_test_local\vcm_live_test_local") / "gate1_web" / "data" / "gate2_holdout.json"
data = json.loads(OUT.read_text(encoding="utf-8"))
models = data["models"]
print("MODELS=" + str(len(models)))
for name in ("gate2v69", "gate2v70", "gate2v71", "gate2v86_speechoos_mid", "gate2v86b_v77mix", "gate2v87_combo_intent"):
    row = next((m for m in models if m["model"] == name), None)
    print(name + " real=" + str(row.get("acc_real")) + " oos=" + str(row.get("oos_reject")) if row else name + " MISSING")
print("TOP5 " + ", ".join(m["model"] + ":" + str(m.get("acc_real")) for m in models[:5]))
