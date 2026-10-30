"""Load every v143+ package tflite and report its interface.

Read-only: nothing is registered or modified. A package is a candidate for the
app registry when the input is (1, 148, 60, 9) float32 and the output is
(1, 20) or (1, 19) - matching the shared frontend and the intent labels.
"""

import json
import pathlib
import re

import numpy as np
import tensorflow as tf

SHIP = pathlib.Path(
    r"C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/Shipping"
)


def main() -> int:
    rows = []
    for base in (SHIP, SHIP / "Shipping Container 1"):
        if not base.is_dir():
            continue
        for pkg in sorted(base.glob("Gate2V*")):
            m = re.match(r"Gate2V(\d+)([a-zA-Z]*)", pkg.name)
            if not m or int(m.group(1)) < 143:
                continue
            tflites = sorted(pkg.rglob("*.tflite"))
            if not tflites:
                rows.append((pkg.name, "no-tflite", "", "", ""))
                continue
            tfl = tflites[0]
            try:
                interp = tf.lite.Interpreter(model_path=str(tfl))
                interp.allocate_tensors()
                inp = interp.get_input_details()[0]
                outp = interp.get_output_details()[0]
                ins = "x".join(str(d) for d in inp["shape"])
                outs = "x".join(str(d) for d in outp["shape"])
                n_out = int(np.prod(outp["shape"]))
                labels = pkg / "labels.json"
                n_lab = 0
                if labels.is_file():
                    try:
                        data = json.loads(labels.read_text(encoding="utf-8"))
                        if isinstance(data, list):
                            n_lab = len(data)
                    except json.JSONDecodeError as err:
                        n_lab = "bad-json " + str(err)[:30]
                verdict = (
                    "OK"
                    if (
                        ins == "1x148x60x9"
                        and int(np.prod(inp["shape"])) == 1 * 148 * 60 * 9
                        and n_out in (19, 20)
                    )
                    else "CHECK"
                )
                rows.append(
                    (
                        pkg.name,
                        verdict,
                        ins + " " + str(inp["dtype"].__name__),
                        outs,
                        "labels=" + str(n_lab),
                    )
                )
            except (ValueError, OSError, RuntimeError) as err:
                rows.append((pkg.name, "LOAD-FAIL", str(err)[:60], "", ""))
    ok = sum(1 for r in rows if r[1] == "OK")
    print("probed=" + str(len(rows)) + " OK=" + str(ok))
    for name, verdict, ins, outs, labs in rows:
        print(
            "  "
            + verdict.ljust(9)
            + " "
            + name[:50].ljust(50)
            + " in["
            + ins
            + "] out["
            + outs
            + "] "
            + labs
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
