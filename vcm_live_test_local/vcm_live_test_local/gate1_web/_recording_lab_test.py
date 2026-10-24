"""Recording lab: store round-trip, live-faithful replay, Gate 3, saved results.

The fake runner scripts each tick: score_gate2 is called once per model per
tick, wake_probs once per tick (after the Gate 2 loop), so a script of
(g2_probs, wake_pair) entries drives the whole run deterministically.

Run: py -3.12 -m pytest gate1_web/_recording_lab_test.py -q
"""

from __future__ import annotations

import json

import numpy as np
import recording_lab


class FakeRunner:
    """Scripted runner: one (g2_probs, wake_pair) entry per evaluation tick."""

    def __init__(self, script, labels=("NEGATIVE", "PLAY_MUSIC", "TIMER")):
        self.script = list(script)
        self.labels = list(labels)
        self.i = 0
        self.spec_calls = []

    def models(self):
        return ["gate2fake"]

    def score_gate2(self, model, window):
        g2 = self.script[min(self.i, len(self.script) - 1)][0]
        return np.asarray(list(g2.values()), dtype=np.float32), list(g2.keys()), 1.0

    def wake_probs(self, window):
        pair = self.script[min(self.i, len(self.script) - 1)][1]
        self.i += 1
        return np.asarray(pair, dtype=np.float32), ["Nova", "Piattos"]

    def wake_thresholds(self):
        return {"Nova": 0.5, "Piattos": 0.5}

    def gate2_threshold(self, intent):
        return 0.5

    def specialists(self, window, routed):
        self.spec_calls.append(routed)
        return {"gate": routed, "label": "10", "conf": 0.77}


def quiet():
    return ({"NEGATIVE": 0.9, "PLAY_MUSIC": 0.05, "TIMER": 0.05}, (0.1, 0.1))


def wake():
    return ({"NEGATIVE": 0.9, "PLAY_MUSIC": 0.05, "TIMER": 0.05}, (0.9, 0.1))


def command(intent="PLAY_MUSIC", conf=0.85):
    other = (1.0 - conf) / 2
    return ({"NEGATIVE": 0.05, intent: conf, "TIMER": other}, (0.1, 0.1))


def run_job(lab, rec_id, script, models=("m",)):
    audio = lab.store.load(rec_id)
    assert audio is not None
    frames = recording_lab._window_starts(audio.size, recording_lab.SR)
    job = recording_lab.TestJob(
        id="job1",
        recording=rec_id,
        label="test",
        models=list(models),
        ticks_total=len(frames),
        duration_s=round(audio.size / recording_lab.SR, 2),
        # combos carry (g1, g2, nc_mode, arch): recording_lab gained
        # the noise-canceller and architecture axes after this fixture was written.
        g1_models=["g1x"],
        combos=[["g1x", m, False, 0] for m in models],
    )
    lab._run_job(job, audio, frames, recording_lab.SR, lambda g1: FakeRunner(script))
    return job


def kinds(job):
    return [e["kind"] for e in job.events]


def test_store_round_trip(tmp_path):
    lab = recording_lab.RecordingLab(tmp_path / "rec")
    audio = np.zeros(int(2.5 * recording_lab.SR), dtype=np.float32)
    entry = lab.store.save(audio, "hello world")
    assert entry["duration_s"] == 2.5
    assert [e["label"] for e in lab.store.list()] == ["hello world"]
    updated = lab.store.update(entry["id"], label="renamed")
    assert updated is not None and updated["label"] == "renamed"
    assert lab.store.delete(entry["id"]) is True
    assert lab.store.list() == []
    assert lab.store.get(entry["id"]) is None


def test_wake_then_command_triggers_g1_g2_g3(tmp_path):
    lab = recording_lab.RecordingLab(tmp_path / "rec")
    rec_id = lab.store.save(
        np.zeros(int(10 * recording_lab.SR), dtype=np.float32), "flow"
    )["id"]
    # tick0 quiet, tick1-2 wake (2-of-3 vote), tick3 command, tick4 same command
    job = run_job(lab, rec_id, [quiet(), wake(), wake(), command(), command()])
    assert kinds(job) == ["g1", "g2", "g3"]
    g3 = [e for e in job.events if e["kind"] == "g3"][0]
    assert g3["route"] == "PLAY_MUSIC" and g3["label"] == "10" and g3["conf"] == 0.77
    # one g3 per pending command: the repeat tick re-arms nothing
    assert kinds(job).count("g3") == 1
    summary = job.summaries[0]
    assert summary["top_intent"] == "PLAY_MUSIC"
    assert summary["trigger_ticks"] >= 2  # latch overlap on ticks 3 and 4
    # results persist automatically
    saved = lab.result(job.id)
    assert saved is not None and saved["id"] == job.id
    assert [r["id"] for r in lab.results()] == [job.id]


def test_stale_command_is_blocked_by_wake_ordering(tmp_path):
    lab = recording_lab.RecordingLab(tmp_path / "rec")
    rec_id = lab.store.save(
        np.zeros(int(15 * recording_lab.SR), dtype=np.float32), "stale"
    )["id"]
    script = [command()] + [quiet()] * 5 + [wake(), wake(), wake()] + [quiet()]
    job = run_job(lab, rec_id, script)
    assert "g2" in kinds(job) and "g1" in kinds(job)
    assert "g3" not in kinds(job)  # command fired >6 s before the wake: no trigger


def test_command_inside_wake_grace_still_fires(tmp_path):
    lab = recording_lab.RecordingLab(tmp_path / "rec")
    rec_id = lab.store.save(
        np.zeros(int(12 * recording_lab.SR), dtype=np.float32), "grace"
    )["id"]
    # command first, wake 2 ticks later — inside the 6 s wake-ordering grace
    job = run_job(lab, rec_id, [command(), wake(), wake(), quiet(), quiet()])
    assert "g3" in kinds(job)


def test_confidence_dip_rearms_the_same_command(tmp_path):
    lab = recording_lab.RecordingLab(tmp_path / "rec")
    rec_id = lab.store.save(
        np.zeros(int(12 * recording_lab.SR), dtype=np.float32), "rearm"
    )["id"]
    # wake first, then command / dip / command again: the second command re-fires
    script = [wake(), wake(), command(), command(conf=0.3), command(), quiet()]
    job = run_job(lab, rec_id, script)
    g2s = [e for e in job.events if e["kind"] == "g2"]
    assert len(g2s) == 2  # the dip reset the repeat-suppressor like the live server


def test_run_writes_jsonl_process_log(tmp_path):
    lab = recording_lab.RecordingLab(tmp_path / "rec")
    rec_id = lab.store.save(
        np.zeros(int(10 * recording_lab.SR), dtype=np.float32), "logged"
    )["id"]
    job = run_job(lab, rec_id, [quiet(), wake(), wake(), command(), quiet()])
    log_path = lab.job_log_path(job.id)
    assert log_path.is_file()
    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert entries[0]["event"] == "start" and entries[0]["combos"] == [
        ["g1x", "m", False, 0]
    ]
    assert entries[-1]["event"] == "end" and entries[-1]["status"] == "done"
    tick_entries = [e for e in entries if e["event"] == "tick"]
    assert tick_entries, "expected per-tick process entries"
    first_combo = list(tick_entries[0]["combos"].values())[0]
    assert "intent" in first_combo and "g1_active" in first_combo


def test_results_listing_and_delete(tmp_path):
    lab = recording_lab.RecordingLab(tmp_path / "rec")
    rec_id = lab.store.save(np.zeros(int(8 * recording_lab.SR), dtype=np.float32), "x")[
        "id"
    ]
    job = run_job(lab, rec_id, [quiet(), wake(), wake(), command(), quiet()])
    assert lab.delete_result(job.id) is True
    assert lab.result(job.id) is None
    assert lab.delete_result(job.id) is False


def test_specialist_errors_do_not_kill_the_run(tmp_path):
    class BadSpecRunner(FakeRunner):
        def specialists(self, window, routed):
            raise RuntimeError("boom")

    lab = recording_lab.RecordingLab(tmp_path / "rec")
    rec_id = lab.store.save(
        np.zeros(int(10 * recording_lab.SR), dtype=np.float32), "bad"
    )["id"]
    audio = lab.store.load(rec_id)
    assert audio is not None
    frames = recording_lab._window_starts(audio.size, recording_lab.SR)
    job = recording_lab.TestJob(
        id="job2",
        recording=rec_id,
        label="bad",
        models=["m"],
        ticks_total=len(frames),
        duration_s=round(audio.size / recording_lab.SR, 2),
        g1_models=["g1x"],
        combos=[["g1x", "m", False, 0]],
    )
    script = [quiet(), wake(), wake(), command(), quiet()]
    lab._run_job(job, audio, frames, recording_lab.SR, lambda g1: BadSpecRunner(script))
    assert job.status == "done"
    g3 = [e for e in job.events if e["kind"] == "g3"]
    assert g3 and "error" in g3[0]["label"]
