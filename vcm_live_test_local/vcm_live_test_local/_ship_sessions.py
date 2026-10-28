"""Ship the 86-take and 67-take sessions: audio + metadata + 73-model results."""

import csv
import hashlib
import io
import json
import pathlib
import shutil
import time

import numpy as np

import _bench_gate2_holdout as bench
import gate1_server as gs
from oneshot_pipeline import _load_clip
from recording_lab import RecordingStore

APP = pathlib.Path(__file__).resolve().parent
STORE = RecordingStore(APP / "recordings")
SHIPPING = pathlib.Path(__file__).resolve().parents[2] / "Shipping"
WANT_COUNTS = (86, 68)


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


def sha256_digest(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 16), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def score_takes(takes, models) -> list[dict]:
    results = []
    runners = {}
    for entry in takes:
        path = STORE.path_of(entry)
        clip = _load_clip(path) if path.is_file() else None
        if clip is None:
            continue
        rows = []
        for name in models:
            runner = runners.get(name)
            if runner is None:
                runner = runner_for(name)
                runners[name] = runner
            model_labels = list(runner.labels)
            try:
                probs = probs_for(name, runner, clip)
            except (RuntimeError, ValueError):
                continue
            intent, conf = gs._g2_candidate_intent(probs, model_labels, {}, 0.0)
            rows.append(
                {
                    "model": name,
                    "intent": str(intent) if intent else "NEGATIVE",
                    "conf": round(float(conf), 4)
                    if conf is not None and np.isfinite(conf)
                    else None,
                    "match": bool(
                        intent and bench.same_command(intent, entry.get("action"))
                    ),
                }
            )
        results.append(
            {
                "take_id": entry.get("id"),
                "phrase": entry.get("label"),
                "intent": entry.get("action"),
                "created": entry.get("created"),
                "duration_s": entry.get("duration_s"),
                "session": entry.get("session"),
                "results": rows,
            }
        )
    return results


def main() -> int:
    sessions = STORE.list_sessions()
    picked = [s for s in sessions if s.get("takes") in WANT_COUNTS]
    if len(picked) != 2:
        print("FOUND=" + str(len(picked)) + " expected 2 (wav counts 86 and 68)")
        return 1
    stamp = time.strftime("%Y%m%d_%H%M%S")
    package = SHIPPING / ("VoiceSessions_ship_" + stamp)
    models = sorted(gs.GATE2_PACKAGE_RUNNERS)
    for session in sorted(picked, key=lambda s: -s.get("takes", 0)):
        sid = str(session.get("id"))
        count = int(session.get("takes", 0))
        sub = package / str(count)
        audio = sub / "audio"
        audio.mkdir(parents=True, exist_ok=True)
        takes = [
            entry for entry in STORE.list() if str(entry.get("session") or "") == sid
        ]
        copy_names: dict[str, str] = {}
        for entry in sorted(takes, key=lambda e: str(e.get("created") or "")):
            src = STORE.path_of(entry)
            if not src.is_file():
                continue
            target = audio / (str(entry.get("id") or "take") + ".wav")
            shutil.copy2(str(src), str(target))
            copy_names[str(entry.get("id"))] = target.name
        scored = score_takes(takes, models)
        for result in scored:
            result["audio"] = copy_names.get(str(result["take_id"]), "")
        (sub / "takes.json").write_text(
            json.dumps(
                [{**t, "audio": copy_names.get(str(t.get("id")), "")} for t in takes],
                indent=1,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (sub / "results.json").write_text(
            json.dumps(
                {"generated": stamp, "models_benchmarked": models, "takes": scored},
                indent=1,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "take_id",
                "phrase",
                "intent",
                "session",
                "audio",
                "model",
                "predicted_intent",
                "probability",
                "match",
                "duration_s",
            ]
        )
        for result in scored:
            for row in result["results"]:
                writer.writerow(
                    [
                        result["take_id"],
                        result["phrase"],
                        result["intent"],
                        result["session"],
                        result["audio"],
                        row["model"],
                        row["intent"],
                        row["conf"],
                        1 if row["match"] else 0,
                        result.get("duration_s", ""),
                    ]
                )
        (sub / "results.csv").write_text(buffer.getvalue(), encoding="utf-8")
        (sub / "MANIFEST.json").write_text(
            json.dumps(
                {
                    "package": "VoiceSession_" + str(count) + "_takes",
                    "created_at": stamp,
                    "source_session": sid,
                    "source_label": str(session.get("label")),
                    "takes": len(takes),
                    "scored": len(scored),
                    "models_benchmarked": len(models),
                    "provenance": "recorded locally in the VCM One-Shot app",
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        sums = []
        for path in sorted(sub.rglob("*")):
            if path.is_file():
                relative = path.relative_to(package).as_posix()
                sums.append(sha256_digest(path) + "  " + relative)
        (sub / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
        (sub / "HANDOFF.md").write_text(
            "# Voice session - " + str(count) + " takes\n\n"
            "- Source session: " + sid + " (" + str(session.get("label")) + ")\n"
            "- Recordings in audio/, metadata in takes.json\n"
            "- Full 73-model scoring matrix in results.json / results.csv "
            "(predicted intent, softmax probability, match per take x model)\n"
            "- Reproduce in the app: open this session, then Test all mine x all models\n",
            encoding="utf-8",
        )
        print(str(count) + " takes shipped -> " + str(sub.relative_to(SHIPPING)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
