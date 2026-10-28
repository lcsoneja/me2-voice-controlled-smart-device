"""TASK 2: noise-canceller A/B on 20 session takes.

Scores each take twice through the same models: raw mic vs NC-cleaned, and
reports per-model match rates plus per-take flips.
"""

import pathlib

import numpy as np

import _bench_gate2_holdout as bench
import gate1_server as gs
from oneshot_pipeline import _load_clip
from recording_lab import RecordingStore

APP = pathlib.Path(__file__).resolve().parent
store = RecordingStore(APP / "recordings")
MODELS = [
    "gate2v21p",
    "gate2v110_ownerft_aggr",
    "gate2v56_v54",
    "gate2v108_ownerft_v93b",
]
NC = {"enabled": True}


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


def hit(name: str, runner, clip: np.ndarray, expected: str) -> bool:
    try:
        probs = probs_for(name, runner, clip)
    except (RuntimeError, ValueError):
        return False
    got = bench.top_intent(list(runner.labels), probs)
    return bool(got and bench.same_command(got, expected))


def select_takes() -> list[dict]:
    rows = [
        entry
        for entry in store.list()
        if not str(entry.get("id") or "").startswith("me2h")
        and str(entry.get("action") or "").strip()
        and str(entry.get("session") or "").startswith("20261027_1")
        and str(entry.get("session") or "")
        in ("20261027_163214_6775", "20261027_111121_e383")
    ]
    by_session: dict[str, list] = {}
    for entry in rows:
        by_session.setdefault(str(entry.get("session")), []).append(entry)
    picked: list[dict] = []
    for items in by_session.values():
        picked.extend(items[:10])
    return picked[:20]


def main() -> int:
    takes = select_takes()
    print("TAKES=" + str(len(takes)))
    runners = {name: runner_for(name) for name in MODELS}
    raw_hits = {name: 0 for name in MODELS}
    nc_hits = {name: 0 for name in MODELS}
    scored = {name: 0 for name in MODELS}
    flips = {name: [0, 0, 0] for name in MODELS}  # nc-wins, raw-wins, tie
    for entry in takes:
        path = store.path_of(entry)
        if not path.is_file():
            continue
        clip = _load_clip(path)
        nc = dict(NC)
        gs._nc_noise_update(clip, nc)
        cleaned = gs._nc_apply(clip, nc)
        expected = str(entry.get("action") or "")
        for name in MODELS:
            runner = runners[name]
            raw_ok = hit(name, runner, clip, expected)
            nc_ok = hit(name, runner, cleaned, expected)
            scored[name] += 1
            if raw_ok:
                raw_hits[name] += 1
            if nc_ok:
                nc_hits[name] += 1
            if nc_ok and not raw_ok:
                flips[name][0] += 1
            elif raw_ok and not nc_ok:
                flips[name][1] += 1
            else:
                flips[name][2] += 1
    print("MODEL RAW% NC%  NC_WINS RAW_WINS TIE")
    for name in MODELS:
        n = scored[name]
        raw_pct = round(100 * raw_hits[name] / n, 1)
        nc_pct = round(100 * nc_hits[name] / n, 1)
        diff = round(nc_pct - raw_pct, 1)
        print(
            name
            + ": "
            + str(raw_pct)
            + "%/"
            + str(nc_pct)
            + "%  diff="
            + str(diff)
            + "  "
            + str(flips[name][0])
            + "/"
            + str(flips[name][1])
            + "/"
            + str(flips[name][2])
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
