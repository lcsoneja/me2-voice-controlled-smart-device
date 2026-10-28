"""Top-accuracy of every session over its own recordings, across all models."""

import json
import pathlib
import time

import numpy as np

import _bench_gate2_holdout as bench
import gate1_server as gs
from oneshot_pipeline import _load_clip
from recording_lab import RecordingStore

APP = pathlib.Path(__file__).resolve().parent
store = RecordingStore(APP / "recordings")


def runner_for(name: str):
    if name == "gate2v124_ensemble4way":
        return gs.Gate2V124EnsembleRunner(name)
    return gs.Gate2PackageRunner(name)


def probs_for(name: str, runner, clip: np.ndarray) -> list[float]:
    if name in gs.GATE2_PID_CONFIGS:
        return list(runner.predict_pid_clip(clip, name))
    probs = list(runner.predict(clip))
    if name in gs.GATE2_TR_CONFIGS:
        return list(gs._gate2_tr_scores(name, probs))
    return probs


def main() -> int:
    rows = [
        entry for entry in store.list()
        if not str(entry.get("id") or "").startswith("me2h")
    ]
    with_action = [entry for entry in rows if str(entry.get("action") or "").strip()]
    free = len(rows) - len(with_action)
    groups: dict[str, list[dict]] = {}
    for entry in with_action:
        session = str(entry.get("session") or "(no session)")
        groups.setdefault(session, []).append(entry)

    models = sorted(gs.GATE2_PACKAGE_RUNNERS)
    loaded: dict[str, object] = {}

    print("SESSIONS=" + str(len(groups)) + " scored_takes=" + str(len(with_action))
          + " free_takes_skipped=" + str(free))
    for session, takes in sorted(groups.items(), key=lambda item: -len(item[1])):
        label = session
        meta = store.session(session)
        if meta:
            label = str(meta.get("label") or session)
        best_acc = 0.0
        best_model = ""
        best_correct = 0
        for name in models:
            runner = loaded.get(name)
            if runner is None:
                runner = runner_for(name)
                loaded[name] = runner
            correct = 0
            for entry in takes:
                path = store.path_of(entry)
                if not path.is_file():
                    continue
                try:
                    clip = _load_clip(path)
                except (OSError, ValueError):
                    continue
                try:
                    probs = probs_for(name, runner, clip)
                except (RuntimeError, ValueError):
                    continue
                got = bench.top_intent(list(runner.labels), probs)
                if got and bench.same_command(got, entry.get("action")):
                    correct += 1
            acc = correct / len(takes) if takes else 0.0
            if acc > best_acc or (acc == best_acc and name < best_model):
                best_acc = acc
                best_model = name
                best_correct = correct
        print(str(len(takes)).rjust(4) + " takes | " + label[:38].ljust(38)
              + " best=" + str(round(best_acc * 100, 1)) + "% (" + str(best_correct)
              + "/" + str(len(takes)) + ") via " + best_model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
