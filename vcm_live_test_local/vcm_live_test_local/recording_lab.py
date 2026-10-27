"""Recording lab: saved voice recordings plus whole-Gate-2 test runs.

Two jobs live here. First, a store for minute-long 16 kHz mono recordings
(record -> save -> list -> rename/trim -> export -> delete). Second, a replay
test that walks one recording through EVERY shipped Gate 2 model the way the
live pipeline hears it: a 5.92 s window stepping 1 s at a time, Gate 1 wake
scoring on the same windows, per-class thresholds, the 2-of-3 wake vote with
its 5 s cooldown, and the same 12 s / 8 s latch and 6 s ordering grace as
PipelineActivationWindows on the live server.

Results are per-tick events (what the trigger Gantt draws) plus a per-model
summary. Jobs run in a worker thread, so the live dashboard keeps serving its
WebSocket while a test walks a multi-minute recording. Replays can also run
the shared noise canceller (nc=True) — byte-identical to the live pipeline's
preprocessing, so lab results match what the live server would have heard.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

# Shared DSP: the noise canceller is byte-identical to the live pipeline's,
# so a replay with NC on is bit-for-bit the same preprocessing as live.
import nc_dsp

SR = 16000
WIN_SAMPLES = 94720  # 5.92 s at 16 kHz: the live pipeline's scoring window
HOP_SAMPLES = SR  # 1 s evaluation cadence

# These mirror PipelineActivationWindows on the live server so an offline test
# reads like a live run: 12 s wake latch, 8 s command latch, 6 s ordering grace,
# 2-of-3 wake votes and a 5 s wake cooldown.
G1_SECONDS = 12.0
G2_SECONDS = 8.0
G2_WAKE_GRACE = 6.0
WAKE_VOTES = 2
WAKE_COOLDOWN_S = 5.0
INDEX_NAME = "index.json"
SESSIONS_DIR = "sessions"


# The replay runner is duck-typed: gate1_server.RecordingLabRunner provides
# models(), wake_probs(window), wake_thresholds(), score_gate2(model, window)
# -> (probs, labels, infer_ms) and gate2_threshold(intent). Protocol classes
# with ellipsis bodies are style-flagged here, so the contract lives in docs.


def _read_wav(path: Path) -> np.ndarray:
    """Load a WAV as float32 mono at 16 kHz (linear resample, channel mean)."""
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise ValueError(f"{path.name}: expected 16-bit PCM, got {width * 8}-bit")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SR and audio.size:
        count = max(1, round(audio.size * SR / rate))
        audio = np.interp(
            np.linspace(0.0, audio.size - 1, count), np.arange(audio.size), audio
        ).astype(np.float32)
    return audio.astype(np.float32)


def write_wav(path: Path, audio: np.ndarray) -> None:
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())


def decode_wav_bytes(raw: bytes) -> np.ndarray:
    """Decode an uploaded WAV blob into the lab's canonical float32 mono 16 kHz buffer."""
    import io

    try:
        with wave.open(io.BytesIO(raw), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except wave.Error as exc:
        raise ValueError(f"not a readable WAV: {exc}") from exc
    if width != 2:
        raise ValueError(f"expected 16-bit PCM, got {width * 8}-bit")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SR and audio.size:
        count = max(1, round(audio.size * SR / rate))
        audio = np.interp(
            np.linspace(0.0, audio.size - 1, count), np.arange(audio.size), audio
        ).astype(np.float32)
    return audio.astype(np.float32)


def _nc_variant(
    state: dict[str, Any], raw: np.ndarray, clean: np.ndarray | None
) -> np.ndarray:
    """This combo's window for the current tick: raw or cleaned, per its NC axis.

    clean is None when the replay has no noise-canceller lane at all, so every
    combo falls back to raw and the run is byte-identical to a plain replay.
    """
    return clean if (state["nc"] and clean is not None) else raw


def _clean_tag(value: Any) -> str:
    """Structured take tag (wake word / action): short, printable, no path chars."""
    text = str(value or "").strip()
    text = "".join(ch for ch in text if ch.isprintable() and ch not in '\\/:*?"<>|')
    return text[:48]


class RecordingStore:
    """Saved recordings on disk plus their metadata index."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_NAME

    def _read(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _write(self, entries: list[dict[str, Any]]) -> None:
        self.index_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                self._read(), key=lambda e: str(e.get("created", "")), reverse=True
            )

    def get(self, rec_id: str) -> dict[str, Any] | None:
        with self._lock:
            for entry in self._read():
                if entry.get("id") == rec_id:
                    return entry
        return None

    def path_of(self, entry: dict[str, Any]) -> Path:
        return self.root / str(entry["file"])

    @property
    def sessions_dir(self) -> Path:
        return self.root / SESSIONS_DIR

    # ---- session folders: one folder per recording session, each with its own ----
    # ---- session.json (label, created, phrase progress) and its takes' audio. ----

    def list_sessions(self) -> list[dict[str, Any]]:
        """Every session folder on disk with its current take count."""
        folder = self.root / SESSIONS_DIR
        out: list[dict[str, Any]] = []
        if not folder.is_dir():
            return out
        for child in sorted(folder.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            meta_path = child / "session.json"
            if not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            meta = dict(meta)
            meta["folder"] = child.name
            meta["takes"] = len(list(child.glob("*.wav")))
            out.append(meta)
        return out

    def session(self, session_id: str) -> dict[str, Any] | None:
        folder = self.root / SESSIONS_DIR / str(session_id or "")
        if not (folder / "session.json").is_file():
            return None
        try:
            meta = json.loads((folder / "session.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return meta if isinstance(meta, dict) else None

    def create_session(self, label: str = "") -> dict[str, Any]:
        stamp = datetime.now(UTC)
        slug = label.strip() or ("session " + stamp.strftime("%Y-%m-%d %H:%M:%S"))
        sid = stamp.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
        folder = self.root / SESSIONS_DIR / sid
        folder.mkdir(parents=True, exist_ok=True)
        meta = {
            "id": sid,
            "label": slug,
            "created": stamp.isoformat(),
            "phrase_pointer": 0,
        }
        try:
            (folder / "session.json").write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
        return meta

    def set_session_phrases(self, session_id: str, pointer: int) -> None:
        folder = self.root / SESSIONS_DIR / str(session_id or "")
        meta_path = folder / "session.json"
        if not meta_path.is_file():
            return
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(meta, dict):
            return
        try:
            meta["phrase_pointer"] = max(0, int(pointer))
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except (OSError, ValueError, TypeError):
            pass

    def save(
        self,
        audio: np.ndarray,
        label: str = "recording",
        meta: dict[str, Any] | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        """Persist an audio buffer as a new recording entry.

        meta may carry structured tags the UI filters on: wake_word (which wake
        word the take speaks) and action (the main command spoken). When a session
        id is given the clip lives inside recordings/sessions/<id>/ so every
        session has its own folder; the entry keeps a relative file path so the
        flat index keeps working unchanged."""
        stamp = datetime.now(UTC)
        rec_id = stamp.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        clean = (
            "".join(
                ch for ch in label.strip().lower() if ch.isalnum() or ch in " _-"
            ).strip()
            or "recording"
        )
        clean = clean.replace(" ", "_")[:48]
        fname = f"{rec_id}_{clean}.wav"
        safe_session = str(session or "")
        if not safe_session or not set(safe_session) <= set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
        ):
            safe_session = ""
        if safe_session:
            session_folder = self.root / SESSIONS_DIR / safe_session
            session_folder.mkdir(parents=True, exist_ok=True)
            write_wav(session_folder / fname, audio)
            rel_path = SESSIONS_DIR + "/" + safe_session + "/" + fname
        else:
            write_wav(self.root / fname, audio)
            rel_path = fname
        entry = {
            "id": rec_id,
            "file": rel_path,
            "label": label.strip() or "recording",
            "created": stamp.isoformat(),
            "duration_s": round(audio.size / SR, 2),
            "sample_rate": SR,
            "channels": 1,
            "wake_word": _clean_tag((meta or {}).get("wake_word")),
            "action": _clean_tag((meta or {}).get("action")),
        }
        if safe_session:
            entry["session"] = safe_session
        with self._lock:
            entries = self._read()
            entries.append(entry)
            self._write(entries)
        return entry

    def update(
        self,
        rec_id: str,
        *,
        label: str | None = None,
        audio: np.ndarray | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Rename a recording, re-tag it (wake word / action), replace its audio, or any mix."""
        with self._lock:
            entries = self._read()
            for entry in entries:
                if entry.get("id") != rec_id:
                    continue
                if label is not None and label.strip():
                    entry["label"] = label.strip()
                if meta:
                    if "wake_word" in meta:
                        entry["wake_word"] = _clean_tag(meta.get("wake_word"))
                    if "action" in meta:
                        entry["action"] = _clean_tag(meta.get("action"))
                    if "verdict" in meta:
                        entry["verdict"] = meta["verdict"]
                if audio is not None:
                    write_wav(self.path_of(entry), audio)
                    entry["duration_s"] = round(audio.size / SR, 2)
                    entry["edited"] = datetime.now(UTC).isoformat()
                self._write(entries)
                return entry
        return None

    def delete(self, rec_id: str) -> bool:
        with self._lock:
            entries = self._read()
            keep = [e for e in entries if e.get("id") != rec_id]
            if len(keep) == len(entries):
                return False
            for entry in entries:
                if entry.get("id") == rec_id:
                    with contextlib_suppress():
                        self.path_of(entry).unlink()
            self._write(keep)
            return True

    def trash_takes(self, rec_ids: list[str]) -> dict[str, Any]:
        """Move takes into a dated trash folder instead of deleting them.

        Nothing the user recorded is ever lost: the wav moves to
        recordings/_trash_<stamp>/, every entry is recorded in
        trash_manifest.json, and only the live index row is removed. Holdout
        clips are refused, never trashed."""
        with self._lock:
            entries = self._read()
            stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            trash_dir = self.root / ("_trash_" + stamp)
            try:
                trash_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                trash_dir = self.root / "_trash"
                trash_dir.mkdir(parents=True, exist_ok=True)
            wanted = set(rec_ids)
            seen: list[str] = []
            moved: list[str] = []
            refused: list[str] = []
            failed: list[str] = []
            manifest: list[dict[str, Any]] = []
            kept: list[dict[str, Any]] = []
            for entry in entries:
                rec_id = str(entry.get("id") or "")
                if rec_id not in wanted:
                    kept.append(entry)
                    continue
                seen.append(rec_id)
                if rec_id.startswith("me2h"):
                    refused.append(rec_id)
                    kept.append(entry)
                    continue
                path = self.path_of(entry)
                if path.is_file():
                    try:
                        shutil.move(str(path), str(trash_dir / path.name))
                    except OSError:
                        kept.append(entry)
                        failed.append(rec_id)
                        continue
                moved.append(rec_id)
                manifest.append({**entry, "trashed_at": stamp})
            self._write(kept)
            if manifest:
                manifest_path = self.root / "trash_manifest.json"
                try:
                    history: list[Any] = []
                    if manifest_path.is_file():
                        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                        if isinstance(raw, list):
                            history = raw
                    history.extend(manifest)
                    manifest_path.write_text(
                        json.dumps(history, indent=1), encoding="utf-8"
                    )
                except (OSError, json.JSONDecodeError):
                    pass
            missing = [rec_id for rec_id in rec_ids if rec_id not in seen]
            return {
                "moved": moved,
                "refused": refused,
                "missing": missing,
                "failed": failed,
                "trash_dir": trash_dir.name,
            }

    def load(self, rec_id: str) -> np.ndarray | None:
        entry = self.get(rec_id)
        if entry is None:
            return None
        path = self.path_of(entry)
        return _read_wav(path) if path.is_file() else None


def contextlib_suppress() -> Any:  # tiny helper: keep delete() readable
    import contextlib

    return contextlib.suppress(OSError)


# Per-thread CPU clock: with parallel lane scoring, time.process_time() sums
# every worker's CPU, so each lane's cpu/tick metric would be inflated.
# thread_time() measures the calling worker thread only (process_time fallback
# where the platform lacks it).
_thread_time = getattr(time, "thread_time", time.process_time)


@dataclass
class TestJob:
    """One whole-Gate-2 replay of a saved recording."""

    id: str
    recording: str
    label: str
    models: list[str]
    ticks_total: int
    status: str = "queued"
    progress: float = 0.0
    workers: int = 0
    created: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished: str = ""
    error: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    summaries: list[dict[str, Any]] = field(default_factory=list)
    elapsed_s: float = 0.0
    duration_s: float = 0.0
    g1_models: list[str] = field(default_factory=list)
    combos: list[list[Any]] = field(default_factory=list)
    nc: bool = False
    nc_modes: list[bool] = field(default_factory=list)
    gated: bool = False
    gated_modes: list[bool] = field(default_factory=list)
    arches: list[int] = field(default_factory=list)
    expected_wake: str = ""
    expected_action: str = ""
    cancel_requested: bool = False

    def as_dict(self, *, with_events: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "recording": self.recording,
            "label": self.label,
            "models": self.models,
            "ticks_total": self.ticks_total,
            "status": self.status,
            "progress": round(self.progress, 4),
            "workers": self.workers,
            "created": self.created,
            "finished": self.finished,
            "error": self.error,
            "summaries": self.summaries,
            "elapsed_s": self.elapsed_s,
            "duration_s": self.duration_s,
            "g1_models": self.g1_models,
            "combos": self.combos,
            "nc": self.nc,
            "nc_modes": self.nc_modes,
            "gated": self.gated,
            "gated_modes": self.gated_modes,
            "expected_wake": self.expected_wake,
            "expected_action": self.expected_action,
            "arches": self.arches,
            "log_file": "recordings/logs/" + self.id + ".jsonl",
        }
        if with_events:
            payload["events"] = self.events
        return payload


class RecordingLab:
    """Store + job registry. Jobs run on a worker thread so the live pipeline keeps running."""

    def __init__(self, root: Path) -> None:
        self.store = RecordingStore(root)
        self._jobs: dict[str, TestJob] = {}
        self._lock = threading.Lock()
        self._analysis_lock = threading.Lock()

    def jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.as_dict(with_events=False) for job in self._jobs.values()]

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
        return job.as_dict() if job is not None else None

    # --- saved results: every finished job lands on disk for later comparison ---

    def results_dir(self) -> Path:
        return self.store.root / "results"

    def job_log_path(self, job_id: str) -> Path:
        return self.store.root / "logs" / f"{job_id}.jsonl"

    def save_result(self, job: TestJob) -> Path:
        out_dir = self.results_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{job.id}.json"
        path.write_text(json.dumps(job.as_dict(), indent=2), encoding="utf-8")
        return path

    def append_analysis(self, job: TestJob) -> int:
        """One JSON line per (job, lane) with the take's ground truth attached.

        The consolidated log (logs/analysis.jsonl) the best-combination ranking
        and every "why did this lane win/lose" explanation are grounded in.
        """
        wake_fires: dict[str, int] = {}
        exp_wake_bag = (
            _intent_alias(_intent_bag(job.expected_wake)) if job.expected_wake else None
        )
        for ev in job.events:
            if ev.get("kind") != "g1":
                continue
            key = (
                f"{ev.get('g1_model', '')}|{ev.get('model', '')}"
                f"|{int(bool(ev.get('nc')))}|{int(bool(ev.get('gated')))}"
            )
            if (
                exp_wake_bag
                and _intent_alias(_intent_bag(str(ev.get("label", "")))) == exp_wake_bag
            ):
                wake_fires[key] = wake_fires.get(key, 0) + 1
        rows = []
        for s in job.summaries:
            key = (
                f"{s.get('g1_model', '')}|{s.get('model', '')}"
                f"|{int(bool(s.get('nc')))}|{int(bool(s.get('gated')))}"
            )
            matched = sum(
                (v or 0)
                for k, v in (s.get("intents") or {}).items()
                if _intent_matches(k, job.expected_action)
            )
            wf = wake_fires.get(key, 0)
            wake_ok = (wf > 0) if job.expected_wake else None
            intent_ok = (matched > 0) if job.expected_action else None
            if wake_ok is None and intent_ok is None:
                verdict = "na"
            elif wake_ok is False and intent_ok is False:
                verdict = "none"
            elif intent_ok is False:
                verdict = "intent_failed"
            elif wake_ok is False:
                verdict = "wake_failed"
            else:
                verdict = "ok"
            slot = ""
            if (s.get("g3_fired") or 0) > 0 and s.get("g3_top"):
                slot = str(s["g3_top"]).split(":").pop()
            rows.append(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "job": job.id,
                    "created": job.created,
                    "recording": job.recording,
                    "label": job.label,
                    "status": job.status,
                    "duration_s": job.duration_s,
                    "elapsed_s": job.elapsed_s,
                    "expected_wake": job.expected_wake,
                    "expected_action": job.expected_action,
                    "g1": s.get("g1_model"),
                    "g2": s.get("model"),
                    "nc": bool(s.get("nc")),
                    "gated": bool(s.get("gated")),
                    "arch": int(s.get("arch", 0)),
                    "trigger_ticks": s.get("trigger_ticks", 0),
                    "command_ticks": s.get("command_ticks", 0),
                    "ticks": s.get("ticks", 0),
                    "top_intent": s.get("top_intent", ""),
                    "matched_command_ticks": matched,
                    "wake_fires": wf,
                    "mean_infer_ms": s.get("mean_infer_ms"),
                    "p95_infer_ms": s.get("p95_infer_ms"),
                    "mean_cpu_ms": s.get("mean_cpu_ms"),
                    "total_cpu_s": s.get("total_cpu_s"),
                    "g3_fired": s.get("g3_fired", 0),
                    "slot": slot,
                    "verdict": verdict,
                }
            )
        if not rows:
            return 0
        path = self.job_log_path("analysis")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(row, default=str) + "\n" for row in rows)
        with self._analysis_lock, open(path, "a", encoding="utf-8") as handle:
            handle.write(payload)
        return len(rows)

    def backfill_analysis(self) -> int:
        """Re-log every saved run that predates the analysis log (idempotent)."""
        logged: set[str] = set()
        path = self.job_log_path("analysis")
        if path.is_file():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        logged.add(str(json.loads(line).get("job", "")))
                    except json.JSONDecodeError:
                        continue
            except OSError:
                pass
        added = 0
        for path_result in sorted(self.results_dir().glob("*.json")):
            try:
                data = json.loads(path_result.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or str(data.get("id", "")) in logged:
                continue
            job = TestJob(
                id=str(data.get("id", "")),
                recording=str(data.get("recording", "")),
                label=str(data.get("label", "")),
                models=list(data.get("models", [])),
                ticks_total=int(data.get("ticks_total", 0) or 0),
                status=str(data.get("status", "done")),
                created=str(data.get("created", "")),
                finished=str(data.get("finished", "")),
                error=str(data.get("error", "")),
                events=list(data.get("events", [])),
                summaries=list(data.get("summaries", [])),
                elapsed_s=float(data.get("elapsed_s", 0) or 0),
                duration_s=float(data.get("duration_s", 0) or 0),
                g1_models=list(data.get("g1_models", [])),
                combos=list(data.get("combos", [])),
                nc=bool(data.get("nc")),
                nc_modes=list(data.get("nc_modes", [])),
                gated=bool(data.get("gated")),
                gated_modes=list(data.get("gated_modes", [])),
                expected_wake=str(data.get("expected_wake", "")),
                expected_action=str(data.get("expected_action", "")),
            )
            entry = self.store.get(job.recording)
            if entry:
                job.expected_wake = str(entry.get("wake_word", ""))
                job.expected_action = str(entry.get("action", ""))
            added += self.append_analysis(job)
        return added

    def results(self) -> list[dict[str, Any]]:
        """Saved test runs, newest first (header fields only, no events)."""
        entries: list[dict[str, Any]] = []
        for path in self.results_dir().glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            entries.append(
                {
                    "id": data.get("id"),
                    "created": data.get("created", ""),
                    "label": data.get("label", ""),
                    "recording": data.get("recording", ""),
                    "models": data.get("models", []),
                    "status": data.get("status", ""),
                    "elapsed_s": data.get("elapsed_s", 0),
                    "summaries": data.get("summaries", []),
                }
            )
        return sorted(entries, key=lambda e: str(e.get("created", "")), reverse=True)

    def result(self, job_id: str) -> dict[str, Any] | None:
        try:
            data = json.loads(
                (self.results_dir() / f"{job_id}.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def delete_result(self, job_id: str) -> bool:
        path = self.results_dir() / f"{job_id}.json"
        if not path.is_file():
            return False
        with contextlib_suppress():
            path.unlink()
        return True

    def cancel(self, job_id: str) -> bool:
        """Ask a queued/running job to stop at the next tick boundary."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.status not in ("queued", "running"):
            return False
        job.cancel_requested = True
        return True

    def start_test(
        self,
        rec_id: str,
        combos: list[tuple[str, str]],
        runner_factory: Any,
        hop_s: float = 1.0,
        nc: bool = False,
        nc_modes: list[bool] | None = None,
        gated: bool = False,
        gated_modes: list[bool] | None = None,
        architectures: list[int] | None = None,
        workers: int = 0,
    ) -> dict[str, Any]:
        """Queue a replay of one recording through every (Gate 1, Gate 2) combination.

        combos is a list of (g1_model, g2_model) pairs — the benchmark matrix.
        runner_factory(g1_model) builds the replay runner for that wake variant.
        nc_modes is the noise-canceller axis: [False] raw only, [True] cleaned
        only, or [False, True] to replay EVERY pair both ways for an A/B compare.
        nc is kept for the single-mode call style, equivalent to nc_modes=[nc].
        architectures is the architecture axis as codes: [0] Architecture v1
        (the original — all gates run simultaneously, a trigger needs Gate 1
        and Gate 2), [1] Architecture v2 (Gate 1 must be triggered before the
        other gates process), [2] Architecture v3 (v2 plus a two-tick intent
        stability vote), or [0, 1, 2] to replay every pair under all three.
        gated/gated_modes are kept as the single-mode shorthands:
        gated_modes=[g] maps to architectures=[1 if g else 0].
        """
        entry = self.store.get(rec_id)
        if entry is None:
            raise KeyError(rec_id)
        audio = self.store.load(rec_id)
        if audio is None or audio.size == 0:
            raise ValueError(f"recording {rec_id} has no audio")
        if not combos:
            raise ValueError("no (Gate 1, Gate 2) combinations requested")
        hop = max(1, round(hop_s * SR))
        frames = _window_starts(audio.size, hop)
        modes = sorted({bool(m) for m in (nc_modes if nc_modes is not None else [nc])})
        arches = (
            sorted({int(a) for a in architectures})
            if architectures is not None
            else (
                sorted(
                    {
                        1 if g else 0
                        for g in (gated_modes if gated_modes is not None else [gated])
                    }
                )
            )
        )
        # Each stored combo is a 4-tuple: (Gate 1, Gate 2, NC mode, architecture).
        # Architecture codes: 0 = v1 (all gates run), 1 = v2 (G1 first),
        # 2 = v3 (G1 first + two-tick intent stability vote).
        expanded = [
            [g1, g2, mode, arch]
            for (g1, g2) in combos
            for mode in modes
            for arch in arches
        ]
        job = TestJob(
            id=uuid.uuid4().hex[:12],
            recording=rec_id,
            label=str(entry.get("label", "")),
            models=sorted({g2 for _, g2 in combos}),
            ticks_total=len(frames),
            duration_s=round(audio.size / SR, 2),
            g1_models=sorted({g1 for g1, _ in combos}),
            combos=expanded,
            nc=bool(modes[-1]),
            nc_modes=modes,
            gated=any(a >= 1 for a in arches),
            gated_modes=[a >= 1 for a in arches],
            arches=arches,
            workers=max(0, int(workers)),
            expected_wake=str(entry.get("wake_word", "")),
            expected_action=str(entry.get("action", "")),
        )
        with self._lock:
            self._jobs[job.id] = job
        thread = threading.Thread(
            target=self._run_job,
            args=(job, audio, frames, hop, runner_factory),
            name=f"recording-lab-{job.id}",
            daemon=True,
        )
        thread.start()
        return job.as_dict(with_events=False)

    def _run_job(
        self,
        job: TestJob,
        audio: np.ndarray,
        frames: list[int],
        hop: int,
        runner_factory: Any,
    ) -> None:
        job.status = "running"
        started = time.perf_counter()
        log_path = self.job_log_path(job.id)

        def jlog(event: dict) -> None:
            """Append one JSON line per pipeline stage: start/tick/end/error."""
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                entry = {"ts": datetime.now(UTC).isoformat(), **event}
                with open(log_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, default=str) + "\n")
            except OSError:
                pass

        jlog(
            {
                "event": "start",
                "recording": job.recording,
                "label": job.label,
                "combos": job.combos,
                "hop_s": round(hop / SR, 3),
                "ticks": len(frames),
                "nc": bool(job.nc),
                "nc_modes": job.nc_modes,
                "gated": bool(job.gated),
                "gated_modes": job.gated_modes,
                "arches": job.arches,
            }
        )
        # Noise-canceller state mirrors the live pipeline: one profile for the
        # whole replay, learned from raw audio, applied to inference windows only.
        # When the matrix spans both modes the profile is still learned from raw
        # audio, so the NC-on lanes hear exactly what the live server would.
        nc_any = any(job.nc_modes) if job.nc_modes else bool(job.nc)
        nc_state: dict[str, Any] = {"enabled": nc_any, "profile": None, "updates": 0}
        runners: dict[str, Any] = {}
        for g1 in job.g1_models:
            try:
                runners[g1] = runner_factory(g1)
            except Exception as exc:  # a broken wake variant fails only its combos
                print(
                    f"[recording-lab] runner {g1} failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )
                jlog(
                    {
                        "event": "runner_error",
                        "g1": g1,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        # Worker threads: lanes sharing a Gate 2 model share one TFLite
        # interpreter (the shared gates registry), so the tick parallelizes
        # ACROSS models - lanes of one model stay sequential inside their
        # worker. workers=1 reproduces the old sequential runner exactly.
        workers = job.workers or 0
        if workers <= 0:
            workers = min(8, os.cpu_count() or 4)
        pool: ThreadPoolExecutor | None = None
        if workers > 1:
            pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vcm-lab")
        job.workers = workers
        per_combo: dict[str, dict[str, Any]] = {
            f"{g1}|{g2}|{int(nc_mode)}|{int(arch)}": {
                "events": [],
                "conf_sum": 0.0,
                "hits": 0,
                "intents": {},
                "ms": [],
                "cpu_ms": [],
                "g1l": _Latch(G1_SECONDS),
                "g2l": _Latch(G2_SECONDS),
                "votes": [],
                "cooldown_until": -1.0,
                "last_wake": None,
                "last_intent": None,
                "triggered": 0,
                "armed": None,
                "g1_at": -1e9,
                "g2_at": -1e9,
                "pending_g2": None,
                "g1m": g1,
                "g2m": g2,
                "nc": bool(nc_mode),
                "gated": arch >= 1,
                "arch": int(arch),
                "streak_intent": None,
                "streak": 0,
                "pid_fresh": False,
                "error": "" if g1 in runners else f"runner {g1} failed to load",
            }
            for g1, g2, nc_mode, arch in job.combos
        }
        try:
            for index, start in enumerate(frames):
                if job.cancel_requested:
                    job.status = "cancelled"
                    break
                raw_window = _window(audio, start, hop)
                tick_s = round(start / SR, 3)
                # Live order: learn the profile from raw audio, then clean only
                # the inference inputs. Raw and cleaned lanes share one profile
                # history per tick, so the A/B differs ONLY by the cleaner.
                clean_window = None
                if nc_state["enabled"]:
                    nc_dsp._nc_noise_update(raw_window, nc_state)
                    clean_window = nc_dsp._nc_apply(raw_window, nc_state)

                # ---- Gate 2 scoring: parallel across Gate 2 models ----
                # Lanes sharing a model share one TFLite interpreter (the shared
                # gates registry), so lanes of one model stay sequential inside
                # their worker while different models score concurrently.
                tick_started = time.perf_counter()
                active = [
                    st
                    for st in per_combo.values()
                    if not st["error"]
                    and not (st["arch"] >= 1 and not st["g1l"].active(tick_s))
                ]
                for state in active:
                    if not state["pid_fresh"]:
                        # Fairness: each lane starts with a fresh PID controller —
                        # without this the state leaks across NC/gate-order lanes.
                        try:
                            runners[state["g1m"]].reset_pid(state["g2m"])
                        except Exception as exc:
                            jlog(
                                {
                                    "event": "pid_reset_error",
                                    "g1": state["g1m"],
                                    "model": state["g2m"],
                                    "error": f"{type(exc).__name__}: {exc}"[:160],
                                }
                            )
                        state["pid_fresh"] = True

                def _score_group(
                    item: tuple[str, list[dict[str, Any]]],
                    raw_window: np.ndarray = raw_window,
                    clean_window: np.ndarray | None = clean_window,
                ) -> list[dict[str, Any]]:
                    # Default args bind THIS tick's windows at definition time —
                    # no late-binding hazard across loop iterations.
                    model, states = item
                    out: list[dict[str, Any]] = []
                    for (
                        state
                    ) in states:  # same interpreter -> sequential inside the group
                        rec: dict[str, Any] = {
                            "key": f"{state['g1m']}|{model}|{int(state['nc'])}|{int(state['arch'])}"
                        }
                        try:
                            c0 = _thread_time()
                            probs, labels, infer_ms = runners[state["g1m"]].score_gate2(
                                model, _nc_variant(state, raw_window, clean_window)
                            )
                            rec.update(
                                {
                                    "probs": probs,
                                    "labels": labels,
                                    "ms": infer_ms,
                                    "cpu_ms": (_thread_time() - c0) * 1000.0,
                                }
                            )
                        except (
                            Exception
                        ) as exc:  # one broken package must not kill the whole run
                            rec["error"] = f"{type(exc).__name__}: {exc}"
                        out.append(rec)
                    return out

                grouped: dict[str, list[dict[str, Any]]] = {}
                for state in active:
                    grouped.setdefault(state["g2m"], []).append(state)
                group_items = list(grouped.items())
                if pool is not None and len(group_items) > 1:
                    scored_groups = list(pool.map(_score_group, group_items))
                else:
                    scored_groups = [_score_group(item) for item in group_items]
                outcome_by_key: dict[str, dict[str, Any]] = {}
                for recs in scored_groups:
                    for rec in recs:
                        outcome_by_key[rec["key"]] = rec
                # Deterministic apply order keeps results identical to the
                # sequential runner regardless of thread completion order.
                for rec_key in sorted(outcome_by_key):
                    rec = outcome_by_key[rec_key]
                    state = per_combo[rec_key]
                    if rec.get("error"):
                        state["error"] = rec["error"]
                        continue
                    probs, labels = rec["probs"], rec["labels"]
                    state["cpu_ms"].append(rec["cpu_ms"])
                    top = int(np.argmax(probs))
                    intent = labels[top] if top < len(labels) else ""
                    conf = float(probs[top])
                    threshold = runners[state["g1m"]].gate2_threshold(intent)
                    state["ms"].append(rec["ms"])
                    state["conf_sum"] += conf
                    qualifies = (
                        bool(intent)
                        and intent not in ("NEGATIVE", "NEG")
                        and conf >= threshold
                    )
                    if state["arch"] == 2 and qualifies:
                        # Architecture v3: an intent only counts after two
                        # consecutive agreeing ticks — single-tick blips die here.
                        if state["streak_intent"] == intent:
                            state["streak"] += 1
                        else:
                            state["streak_intent"] = intent
                            state["streak"] = 1
                        if state["streak"] < 2:
                            # First agreeing tick of this intent: hold the vote,
                            # count nothing, and leave `armed` untouched so the
                            # confirming tick can still fire the latch.
                            continue
                        qualifies = True
                    if qualifies:
                        state["hits"] += 1
                        state["intents"][intent] = state["intents"].get(intent, 0) + 1
                        if intent != state["armed"]:
                            # Live PipelineActivationWindows.observe_gate2 opens the
                            # 8 s window only when the intent CHANGES; repeats do
                            # not extend it.
                            state["g2l"].fire(tick_s)
                            state["g2_at"] = tick_s
                            state["events"].append(
                                {
                                    "kind": "g2",
                                    "t": tick_s,
                                    "label": intent,
                                    "conf": round(conf, 4),
                                }
                            )
                            state["pending_g2"] = intent
                        state["armed"] = intent
                        state["last_intent"] = intent
                    else:
                        # A non-qualifying tick (low confidence / NEGATIVE) resets
                        # the repeat-suppressor and the v3 vote streak, so the same
                        # command re-fires after a confidence dip — exactly like
                        # the live server.
                        state["streak_intent"] = None
                        state["streak"] = 0
                        state["armed"] = None
                        if (
                            intent
                            and intent not in ("NEGATIVE", "NEG")
                            and intent != state["last_intent"]
                        ):
                            state["events"].append(
                                {
                                    "kind": "g2-low",
                                    "t": tick_s,
                                    "label": intent,
                                    "conf": round(conf, 4),
                                    "threshold": round(threshold, 4),
                                }
                            )
                            state["last_intent"] = intent
                if group_items:
                    jlog(
                        {
                            "event": "tick_timing",
                            "tick": index,
                            "workers": job.workers,
                            "models": len(group_items),
                            "lanes": len(active),
                            "ms": round(
                                (time.perf_counter() - tick_started) * 1000.0, 1
                            ),
                        }
                    )
                # Gate 1 wake is scored once per wake variant, fanned to its combos.
                wake_by_g1: dict[tuple[str, bool], Any] = {}
                thr_by_g1: dict[str, dict[str, float]] = {}
                for g1, runner in runners.items():
                    try:
                        wake_by_g1[(g1, False)] = runner.wake_probs(raw_window)
                        if clean_window is not None:
                            wake_by_g1[(g1, True)] = runner.wake_probs(clean_window)
                        thr_by_g1[g1] = runner.wake_thresholds()
                    except Exception as exc:
                        print(
                            f"[recording-lab] wake {g1} failed: {type(exc).__name__}: {exc}",
                            flush=True,
                        )
                for state in per_combo.values():
                    if state["error"]:
                        continue
                    wp = wake_by_g1.get(
                        (state["g1m"], bool(state["nc"]))
                    ) or wake_by_g1.get((state["g1m"], False))
                    if not wp:
                        continue
                    wake_probs, wake_labels = wp
                    thresholds = thr_by_g1[state["g1m"]]
                    best = (
                        int(np.argmax(wake_probs[:2])) if wake_probs.size >= 2 else -1
                    )
                    wake_label = wake_labels[best] if best >= 0 else ""
                    wake_conf = float(wake_probs[best]) if best >= 0 else 0.0
                    candidate = (
                        wake_label
                        if wake_conf >= thresholds.get(wake_label, 0.5)
                        else None
                    )
                    state["votes"].append(candidate)
                    if len(state["votes"]) > 3:
                        state["votes"].pop(0)
                    votes = sum(
                        1 for v in state["votes"] if v == candidate and v is not None
                    )
                    if (
                        candidate
                        and votes >= WAKE_VOTES
                        and candidate != state["last_wake"]
                        and tick_s >= state["cooldown_until"]
                    ):
                        state["g1l"].fire(tick_s)
                        state["g1_at"] = tick_s
                        state["events"].append(
                            {
                                "kind": "g1",
                                "t": tick_s,
                                "label": candidate,
                                "conf": round(wake_conf, 4),
                            }
                        )
                        state["last_wake"] = candidate
                        state["cooldown_until"] = tick_s + WAKE_COOLDOWN_S
                    elif not candidate:
                        state["last_wake"] = None
                # Trigger pass AFTER the wake fan-out: mirrors the live action
                # gate (both latches overlap + the 6 s wake-ordering grace), and
                # fires the routed specialist once per pending command event.
                spec_raw = audio[max(0, start - 8 * SR) : start]
                spec_clean = (
                    nc_dsp._nc_apply(spec_raw, nc_state)
                    if nc_state["enabled"]
                    else None
                )
                for state in per_combo.values():
                    if state["error"]:
                        continue
                    ready = (
                        state["g1l"].active(tick_s)
                        and state["g2l"].active(tick_s)
                        and state["g2_at"] >= state["g1_at"] - G2_WAKE_GRACE
                    )
                    if not ready:
                        continue
                    state["triggered"] += 1
                    pending = state["pending_g2"]
                    state["pending_g2"] = None
                    if pending is None:
                        continue
                    try:
                        spec_window = _nc_variant(state, spec_raw, spec_clean)
                        spec = runners[state["g1m"]].specialists(spec_window, pending)
                    except (
                        Exception
                    ) as exc:  # a broken specialist must not kill the run
                        spec = {
                            "gate": "?",
                            "label": f"error: {type(exc).__name__}",
                            "conf": 0.0,
                        }
                    if spec:
                        state["events"].append(
                            {
                                "kind": "g3",
                                "t": tick_s,
                                "label": str(spec.get("label", "")),
                                "conf": round(spec.get("conf", 0.0), 4),
                                "route": pending,
                                "gate": str(spec.get("gate", "")),
                            }
                        )
                # Per-tick process log: one line with every combination's state,
                # so a dead gantt or missing trigger can be traced after the run.
                jlog(
                    {
                        "event": "tick",
                        "tick": index,
                        "t": tick_s,
                        "nc": {
                            "enabled": nc_state["enabled"],
                            "updates": nc_state["updates"],
                        },
                        "combos": {
                            key: {
                                "intent": st.get("last_intent"),
                                "armed": st.get("armed"),
                                "g1": st.get("last_wake"),
                                "g2_active": st["g2l"].active(tick_s),
                                "g1_active": st["g1l"].active(tick_s),
                                "triggered": st["triggered"],
                                "nc": bool(st["nc"]),
                                "error": st["error"] or None,
                            }
                            for key, st in per_combo.items()
                        },
                    }
                )
                job.progress = (index + 1) / max(1, len(frames))
            if job.status == "running":
                job.status = "done"
            job.summaries = [
                _summarise(state["g1m"], state["g2m"], state)
                for state in per_combo.values()
            ]
            for key, state in per_combo.items():
                g1, g2 = key.split("|")[0], key.split("|")[1]
                # Tag every event with its combination so the Gantt draws one
                # lane group per (Gate 1, Gate 2, noise-canceller) triple.
                job.events.extend(
                    dict(
                        event,
                        model=g2,
                        g1_model=g1,
                        nc=bool(state["nc"]),
                        gated=bool(state["gated"]),
                        arch=int(state["arch"]),
                    )
                    for event in state["events"]
                )
        except Exception as exc:  # a broken model must not kill the worker silently
            job.status = "error"
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            if pool is not None:
                pool.shutdown(wait=True)
            job.finished = datetime.now(UTC).isoformat()
            job.elapsed_s = round(time.perf_counter() - started, 2)
            jlog(
                {
                    "event": "end",
                    "status": job.status,
                    "elapsed_s": job.elapsed_s,
                    "error": job.error,
                }
            )
            self.save_result(job)
            try:
                self.append_analysis(job)
            except Exception as exc:  # the analysis log must never break the run
                jlog(
                    {
                        "event": "analysis_error",
                        "error": f"{type(exc).__name__}: {exc}"[:200],
                    }
                )


class _Latch:
    """Active-until timestamp latch mirroring PipelineActivationWindows."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.until = -1.0

    def fire(self, now: float) -> None:
        self.until = max(self.until, now + self.seconds)

    def active(self, now: float) -> bool:
        return now < self.until


def _window_starts(total: int, hop: int) -> list[int]:
    """Window end offsets: every hop from the first full window to the last sample."""
    if total <= 0:
        return []
    starts = list(range(WIN_SAMPLES, total + 1, hop))
    if not starts or starts[-1] != total:
        starts.append(total)
    return [max(0, s) for s in starts]


def _window(audio: np.ndarray, end: int, hop: int) -> np.ndarray:
    """Trailing 5.92 s window ending at `end`, front-padded like the live server."""
    end = min(end, audio.size)
    start = max(0, end - WIN_SAMPLES)
    chunk = audio[start:end]
    if chunk.size == WIN_SAMPLES:
        return chunk
    pad = WIN_SAMPLES - chunk.size
    return np.concatenate([np.zeros(pad, dtype=np.float32), chunk])


def _summarise(g1: str, g2: str, state: dict[str, Any]) -> dict[str, Any]:
    ms = state["ms"] or [0.0]
    ticks = len(ms)
    cpu = state.get("cpu_ms") or [0.0]
    intents = state["intents"]
    top = max(intents.items(), key=lambda kv: kv[1])[0] if intents else ""
    # Gate 3 specialist verdicts fired on the trigger pass, by routed intent.
    g3_events = [e for e in state["events"] if e.get("kind") == "g3"]
    g3_labels: dict[str, int] = {}
    for e in g3_events:
        key = f"{e.get('route', '')}:{e.get('label', '')}"
        g3_labels[key] = g3_labels.get(key, 0) + 1
    g3_top = max(g3_labels.items(), key=lambda kv: kv[1])[0] if g3_labels else ""
    return {
        "g1_model": g1,
        "model": g2,
        "ticks": ticks,
        "command_ticks": state["hits"],
        "error": state.get("error", ""),
        "trigger_ticks": state["triggered"],
        "distinct_intents": len(intents),
        "top_intent": top,
        "top_intent_ticks": intents.get(top, 0),
        "intents": intents,
        "mean_conf": round(state["conf_sum"] / ticks, 4) if ticks else 0.0,
        "mean_infer_ms": round(np.mean(ms).item(), 3),
        "p95_infer_ms": round(np.percentile(ms, 95).item(), 3),
        "mean_cpu_ms": round(np.mean(cpu).item(), 3),
        "p95_cpu_ms": round(np.percentile(cpu, 95).item(), 3),
        "total_cpu_s": round(sum(cpu) / 1000.0, 3),
        "nc": state.get("nc", False),
        "gated": state.get("gated", False),
        "arch": state.get("arch", 0),
        "g3_fired": len(g3_events),
        "g3_top": g3_top,
        "g3_labels": g3_labels,
    }


# Ground-truth matching for the analysis log: mirrors the dashboard's
# bag-of-words intent comparison plus the same synonym aliases, so the log's
# verdicts read exactly like what the UI shows.
_INTENT_ALIAS = {
    "settimer": "timer",
    "alarmset": "alarm",
    "tempup": "temperature",
    "tempdown": "temperature",
    "lightsdim": "brightness",
    "lightsbright": "brightness",
    "lightson": "lighton",
    "lightsoff": "lightoff",
    "reminderset": "createreminder",
    "remindercheck": "listreminders",
    "checkreminders": "listreminders",
    "mediaplay": "playmusic",
    "mediapause": "pause",
    "medianext": "next",
    "silence": "stop",
}


def _intent_bag(s: str) -> str:
    return "".join(sorted(t for t in re.split(r"[^a-z]+", str(s or "").lower()) if t))


def _intent_alias(bag: str) -> str:
    return _INTENT_ALIAS.get(bag, bag)


def _intent_matches(pred: str, expected: str) -> bool:
    if not expected:
        return False
    return _intent_alias(_intent_bag(pred)) == _intent_alias(_intent_bag(expected))
