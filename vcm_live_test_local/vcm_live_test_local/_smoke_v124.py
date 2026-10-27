"""Smoke: the V124 ensemble runner on three real holdout clips."""

import json
import pathlib
import wave

import numpy as np

import gate1_server as gs

HERE = pathlib.Path(__file__).resolve().parent


def load_wav(path: pathlib.Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def main() -> int:
    index = json.loads((HERE / "recordings" / "index.json").read_text(encoding="utf-8"))
    recs = index["recordings"] if isinstance(index, dict) else index
    real = [r for r in recs if "me2h" in str(r.get("id")) and "(real)" in str(r.get("label") or "").lower()]
    runner = gs.Gate2V124EnsembleRunner("gate2v124_ensemble4way")
    print("RUNNER labels=" + str(len(runner.labels)) + " last=" + str(runner.labels[-1]))
    for rec in real[:4]:
        clip = load_wav(HERE / "recordings" / str(rec["file"]))
        probs = runner.predict(clip)
        top = int(np.argmax(probs))
        print(str(rec["id"]) + " expected=" + str(rec.get("action"))
              + " got=" + str(runner.labels[top])
              + " p=" + str(round(float(probs[top]), 3))
              + " n=" + str(len(probs)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
