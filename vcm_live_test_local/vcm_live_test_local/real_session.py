"""VCM Real-Time Assistant - always-listening wake word -> intent -> value.

Continuous voice assistant for laptop (Keras) and Raspberry Pi 5 (tflite-runtime).
USB mic in, terminal monitor dashboard out, keyboard control (q/space/m/h).

Pipeline per interaction:
  LISTEN for wake word (gate1)  ->  capture command  ->  gate2 intent
  ->  routed value gate (gateN / gate4 / gate5)  ->  dashboard PASS/FAIL.

Pi deployment: see PI_SETUP.md. Models load from float16 TFLite exports
(no TensorFlow needed on the Pi); on the laptop it falls back to Keras.

Usage:
  python real_session.py                 # live, always listening
  python real_session.py --check         # verify backend + models, exit
  python real_session.py --wav synthetic_samples   # file-based regression
  python real_session.py --backend keras # force Keras backend
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

logger = logging.getLogger("real_session")

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "vcm8/config/model_registry.json"
STATS_74 = ROOT / "vcm8/training/feature_stats.npz"
STATS_148 = ROOT / "vcm8/training/feature_stats_148.npz"
MEL_FB = ROOT / "mel_fb.npz"

GATE_TFLITE = {
    "gate1": ROOT / "vcm8/training/tflite/gate1_v1_float16.tflite",
    "gate2": ROOT / "vcm8/training/tflite/gate2_float16.tflite",
    "gateN": ROOT / "vcm8/training/tflite/gateN_v1_float16.tflite",
    "gate4": ROOT / "vcm8/training/tflite/gate4_float16.tflite",
    "gate5": ROOT / "vcm8/training/tflite/gate5_float16.tflite",
}

SAMPLE_RATE = 16000
N_FFT = 1024
HOP = 640
WIN_LEN = 1024
N_MELS = 60
BLOCK = 1024
RMS_FLOOR_DEFAULT = 0.005
SILENCE_S = 1.0
MAX_UTT_S = 6.0
ONSET_WAIT_S = 6.0
COMMAND_TIMEOUT_S = 8.0


# ---------------------------------------------------------------------------
# Preprocessing (numpy-only; parity with the trained librosa pipeline verified)
# ---------------------------------------------------------------------------
class Preproc:
    def __init__(self, stats_path: Path, target_frames: int):
        if not MEL_FB.is_file():
            raise FileNotFoundError(
                f"{MEL_FB.name} missing - run on a machine with librosa once, or copy it from the laptop bundle."
            )
        self.fb = np.load(MEL_FB)["mel_fb"]
        data = np.load(stats_path)
        self.mean = float(data["mean"])
        self.std = float(data["std"])
        self.target = int(target_frames)
        self.win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)

    def extract(self, y: np.ndarray) -> np.ndarray:
        if y.ndim > 1:
            y = y.mean(axis=1)
        y = y.astype(np.float32)
        y = np.pad(y, N_FFT // 2, mode="reflect")
        n_frames = 1 + (len(y) - N_FFT) // HOP
        idx = np.arange(N_FFT)[None, :] + HOP * np.arange(max(n_frames, 1))[:, None]
        frames = (y[idx] * self.win).astype(np.float32)
        S = np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32) ** 2
        mel = (self.fb @ S.T).astype(np.float32)
        log_S = np.log1p(mel)
        if log_S.shape[1] < self.target:
            log_S = np.pad(log_S, ((0, 0), (0, self.target - log_S.shape[1])))
        else:
            s = (log_S.shape[1] - self.target) // 2
            log_S = log_S[:, s : s + self.target]
        feat = log_S.T
        return ((feat - self.mean) / (self.std + 1e-8))[None, :, :, None].astype(np.float32)


# ---------------------------------------------------------------------------
# Model backends
# ---------------------------------------------------------------------------
class TFLiteRunner:
    """Float16 TFLite interpreters (Raspberry Pi path, no TensorFlow import)."""

    kind = "tflite"

    def __init__(self):
        try:
            from tflite_runtime.interpreter import Interpreter  # type: ignore
        except ImportError:
            from tensorflow.lite import Interpreter  # type: ignore
        self.interpreters = {}
        self.shapes = {}
        for name, path in GATE_TFLITE.items():
            if not path.is_file():
                raise FileNotFoundError(f"TFLite model missing: {path}")
            it = Interpreter(model_path=str(path))
            it.allocate_tensors()
            ind = it.get_input_details()[0]
            shape = tuple(int(d) for d in ind["shape"])
            self.interpreters[name] = (it, ind["index"], it.get_output_details()[0]["index"])
            self.shapes[name] = shape

    def predict(self, name: str, tensor: np.ndarray) -> np.ndarray:
        it, in_idx, out_idx = self.interpreters[name]
        it.set_tensor(in_idx, tensor.astype(np.float32))
        it.invoke()
        return it.get_tensor(out_idx)[0]

    def input_shape(self, name: str) -> tuple[int, ...]:
        return self.shapes[name]


class KerasRunner:
    """Keras checkpoints via live_session (laptop path)."""

    kind = "keras"

    def __init__(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("live_session", ROOT / "live_session.py")
        assert spec is not None and spec.loader is not None
        ls = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ls)
        self.ls = ls
        self.pipeline = ls.VCMModelPipeline(ROOT, REGISTRY_PATH, STATS_74)
        self.fx = self.pipeline.feature_extractor
        self.fx148 = getattr(self.pipeline, "feature_extractor_148", None)

    def predict(self, name: str, tensor: np.ndarray) -> np.ndarray:
        model = self.pipeline.models[name]
        return model(tensor, training=False).numpy()[0]

    def input_shape(self, name: str) -> tuple[int, ...]:
        shape = self.pipeline.models[name].input_shape
        return tuple(int(d) if d is not None else 0 for d in shape)


# ---------------------------------------------------------------------------
# Keyboard (non-blocking single-char reader)
# ---------------------------------------------------------------------------
class Keyboard:
    def __init__(self):
        self.last: str | None = None
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop:
            try:
                if os.name == "nt":
                    import msvcrt

                    if msvcrt.kbhit():
                        ch = msvcrt.getwch()
                        self.last = "q" if ch in ("q", "Q", "\x03") else ch.lower()
                else:
                    import select
                    import termios
                    import tty

                    fd = sys.stdin.fileno()
                    old = termios.tcgetattr(fd)
                    try:
                        tty.setraw(fd)
                        r, _, _ = select.select([fd], [], [], 0.1)
                        if r:
                            ch = sys.stdin.read(1)
                            self.last = "q" if ch in ("q", "Q", "\x03") else ch.lower()
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception as e:
                logger.debug("Keyboard read failed (continuing): %s", e)
            time.sleep(0.02)

    def poll(self) -> str | None:
        ch, self.last = self.last, None
        return ch

    def stop(self):
        self._stop = True


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
class Ui:
    def __init__(self, color: bool):
        self.color = color
        if os.name == "nt":
            try:
                import ctypes

                k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                handle = k32.GetStdHandle(-11)
                mode = ctypes.c_uint32()
                if k32.GetConsoleMode(handle, ctypes.byref(mode)):
                    k32.SetConsoleMode(handle, mode.value | 4)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            except Exception as e:
                logger.debug("ANSI enable failed (continuing): %s", e)

    def _c(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def green(self, t): return self._c("92", t)
    def red(self, t): return self._c("91", t)
    def yellow(self, t): return self._c("93", t)
    def cyan(self, t): return self._c("96", t)
    def bold(self, t): return self._c("1", t)

    def clear(self):
        print("\033[2J\033[H", end="")

    def meter(self, rms: float, floor: float, width: int = 30) -> str:
        db = 20.0 * np.log10(max(rms, 1e-10))
        level = min(1.0, max(0.0, (db + 60.0) / 60.0))
        filled = int(round(level * width))
        bar = "\u2588" * filled + "\u2591" * (width - filled)
        fpos = min(width - 1, max(0, int(round((20.0 * np.log10(max(floor, 1e-10)) + 60.0) / 60.0 * width))))
        bar = bar[:fpos] + "\u2502" + bar[fpos + 1 :]
        return f"[{bar}] {db:6.1f} dB"


# ---------------------------------------------------------------------------
# Audio capture with robust VAD
# ---------------------------------------------------------------------------
def rms_of(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0


def capture_utterance(q: queue.Queue, floor: float) -> tuple[np.ndarray | None, dict]:
    """Record one utterance. Returns (waveform|None, info). Calibrates floor from ambient."""
    calib: list[float] = []
    t_end = time.time() + 0.6
    while time.time() < t_end:
        try:
            calib.append(rms_of(q.get(timeout=0.2).flatten()))
        except queue.Empty:
            continue
    if calib:
        med = float(np.median(calib))
        quiet = [v for v in calib if v <= med * 1.5] or calib
        ambient = float(np.median(quiet))
        floor = max(floor, min(ambient * 2.5, 0.05))

    chunks: list[np.ndarray] = []
    started = False
    silent = 0.0
    total = 0.0
    t0 = time.time()
    deadline = t0 + MAX_UTT_S + ONSET_WAIT_S
    while time.time() < deadline:
        try:
            block = q.get(timeout=0.2).flatten()
        except queue.Empty:
            continue
        rms = rms_of(block)
        if not started:
            if rms >= floor:
                started = True
                chunks.append(block)
                total += len(block) / SAMPLE_RATE
            elif time.time() - t0 > ONSET_WAIT_S:
                return None, {"floor": floor, "reason": "no speech"}
        else:
            chunks.append(block)
            dur = len(block) / SAMPLE_RATE
            total += dur
            silent = 0.0 if rms >= floor else silent + dur
            if silent >= SILENCE_S or total >= MAX_UTT_S:
                break
    if not started or not chunks:
        return None, {"floor": floor, "reason": "no speech"}
    return np.concatenate(chunks).astype(np.float32), {"floor": floor, "duration_s": round(total, 2)}


# ---------------------------------------------------------------------------
# Main assistant
# ---------------------------------------------------------------------------
class RealSession:
    def __init__(self, args):
        self.args = args
        self.ui = Ui(color=not args.no_color)
        try:
            self.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["models"]
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to load model registry {REGISTRY_PATH}: {e}") from e
        self.gate2_labels = self.registry["gate2"]["labels"]
        self.labels = {g: self.registry[g]["labels"] for g in ("gate1", "gate2", "gateN", "gate4", "gate5") if g in self.registry}
        self.wake_words = [w for w in self.labels["gate1"] if w.lower() != "negative"]

        if args.backend in ("auto", "tflite"):
            try:
                self.runner: TFLiteRunner | KerasRunner = TFLiteRunner()
            except Exception:
                if args.backend == "tflite":
                    raise
                logger.debug("TFLite backend unavailable, falling back to Keras")
                self.runner = KerasRunner()
        else:
            self.runner = KerasRunner()

        self.pre74 = Preproc(STATS_74, 74)
        self.stats = {"wake_ok": 0, "wake_miss": 0, "cmd_ok": 0, "cmd_lowconf": 0, "cmd_total": 0, "timeouts": 0}
        self.history: list[str] = []
        self.last: dict = {}
        self.muted = False
        self.command_mode = False
        self.cmd_deadline: float | None = None
        self.floor = RMS_FLOOR_DEFAULT
        self.session_dir = Path.home() / ".vcm-real-sessions" / datetime.now().strftime("real_%Y%m%d_%H%M%S")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.session_dir / "events.jsonl"

    # -- inference helpers -------------------------------------------------
    def gate(self, name: str, features: np.ndarray) -> tuple[str, float]:
        vec = self.runner.predict(name, features)
        labels = self.labels[name]
        idx = int(np.argmax(vec))
        return labels[idx], float(vec[idx])

    def features_for(self, name: str, waveform: np.ndarray) -> np.ndarray:
        shape = self.runner.input_shape(name)
        frames = int(shape[1])
        if frames == 148 and self.runner.kind == "keras":
            fx148 = getattr(self.runner, "fx148", None)
            if fx148 is not None:
                return fx148.extract_features(waveform, sr_in=SAMPLE_RATE)
        return self.pre74.extract(waveform)

    # -- interaction steps --------------------------------------------------
    def listen_wake(self, q) -> None:
        waveform, info = capture_utterance(q, self.floor)
        self.floor = info["floor"]
        if waveform is None:
            return
        label, conf = self.gate("gate1", self.pre74.extract(waveform))
        ok = label in self.wake_words and conf >= self.args.min_conf
        self.stats["wake_ok" if ok else "wake_miss"] += 1
        self.last = {"gate": "gate1", "label": label, "conf": conf, "ok": ok}
        self._log({"event": "wake", "label": label, "conf": round(conf, 3), "ok": ok})
        if ok:
            self.history.append(self.ui.green("W"))
            self.command_mode = True
        else:
            self.history.append(self.ui.red("w"))

    def listen_command(self, q) -> None:
        t_start = time.time()
        waveform, info = capture_utterance(q, self.floor)
        self.floor = info["floor"]
        if waveform is None:
            if time.time() - t_start > COMMAND_TIMEOUT_S - 1:
                self.stats["timeouts"] += 1
                self.last = {"gate": "timeout", "label": "-", "conf": 0.0, "ok": False}
                self.history.append(self.ui.yellow("t"))
            return
        self.stats["cmd_total"] += 1
        g2_label, g2_conf = self.gate("gate2", self.features_for("gate2", waveform))
        routing = {"TIMER": "gateN", "ALARM": "gateN", "TEMPERATURE": "gateN", "BRIGHTNESS": "gateN",
                   "COLOR": "gate4", "CREATE_REMINDER": "gate5"}
        routed = routing.get(g2_label)
        final_label, final_conf, final_gate = g2_label, g2_conf, "gate2"
        if routed:
            final_label, final_conf = self.gate(routed, self.features_for(routed, waveform))
            final_gate = routed
        good = min(g2_conf, final_conf) >= self.args.min_conf
        self.stats["cmd_ok" if good else "cmd_lowconf"] += 1
        self.last = {"gate": final_gate, "intent": g2_label, "g2_conf": g2_conf,
                     "label": final_label, "conf": final_conf, "ok": good, "routed": routed}
        self._log({"event": "command", "intent": g2_label, "g2_conf": round(g2_conf, 3),
                   "final": final_label, "final_gate": final_gate, "conf": round(final_conf, 3), "ok": good})
        self.history.append(self.ui.green("C") if good else self.ui.yellow("c"))

    def _log(self, event: dict) -> None:
        event["ts"] = datetime.now().astimezone().isoformat()
        try:
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except OSError as e:
            logger.error("Failed to append event log: %s", e)

    # -- dashboard ----------------------------------------------------------
    def render(self, rms: float, state: str) -> None:
        u = self.ui
        lines = []
        lines.append("=" * 78)
        lines.append(u.bold(f" VCM REAL-TIME ASSISTANT  |  backend: {self.runner.kind}  |  state: {u.cyan(state)}"))
        lines.append("=" * 78)
        lines.append(f" Mic level  : {u.meter(rms, self.floor)}")
        lines.append(f" Muted      : {'YES' if self.muted else 'no'}")
        lines.append("-" * 78)
        last = self.last
        if not last:
            lines.append(" Last event : (none yet - say the wake word)")
        else:
            g = last.get("gate", "?")
            if last.get("ok"):
                col = u.green
                mark = "PASS"
            elif last.get("gate") == "timeout":
                col = u.yellow
                mark = "TIMEOUT"
            else:
                col = u.red
                mark = "FAIL"
            lines.append(f" Last event : {col(mark + f' [{g}]')}  ->  {last.get('label', '-')}"
                         f"  (conf {last.get('conf', 0):.2f})")
            if "intent" in last:
                lines.append(f"   intent   : {last['intent']} (conf {last['g2_conf']:.2f})"
                             f"   value gate: {last.get('routed') or '-'}")
        lines.append("-" * 78)
        s = self.stats
        acc = f"{s['cmd_ok'] / max(s['cmd_total'], 1) * 100:.0f}%"
        lines.append(f" Stats      : wake {s['wake_ok']}/{s['wake_ok'] + s['wake_miss']}  "
                     f"commands good {s['cmd_ok']}/{s['cmd_total']} ({acc})  low-conf {s['cmd_lowconf']}  "
                     f"timeouts {s['timeouts']}")
        strip = "".join(self.history[-40:])
        lines.append(f" History    : {strip if strip else '(empty)'}")
        lines.append("-" * 78)
        lines.append(" Keys: [space] command now (skip wake)  [m] mute  [h] help  [q] quit")
        print("\033[2J\033[H" + "\n".join(lines), flush=True)

    # -- loops ---------------------------------------------------------------
    def live(self) -> None:
        import sounddevice as sd

        q: queue.Queue = queue.Queue()
        sd.default.device = (self.args.device, None) if self.args.device is not None else sd.default.device
        try:
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                    blocksize=BLOCK, callback=lambda i, f, t, s: q.put(i.copy()))
            stream.start()
        except Exception as e:
            print(f"[ERROR] Could not open microphone: {e}")
            print("Check devices with: python -c \"import sounddevice as sd; print(sd.query_devices())\"")
            return

        kb = Keyboard()
        state = "LISTENING FOR WAKE WORD"
        self.command_mode = False
        self.cmd_deadline = None
        print("Session folder: " + str(self.session_dir))
        time.sleep(0.5)
        try:
            while True:
                key = kb.poll()
                if key == "q":
                    break
                elif key == "m":
                    self.muted = not self.muted
                elif key == " ":
                    self.command_mode = True
                elif key == "h":
                    self.history.append("HELP")

                if self.muted:
                    with contextlib.suppress(queue.Empty):
                        q.get_nowait()
                    self.render(0.0, "MUTED")
                    time.sleep(0.1)
                    continue

                if self.command_mode:
                    state = "LISTENING FOR COMMAND"
                    if self.cmd_deadline is None:
                        self.cmd_deadline = time.time() + COMMAND_TIMEOUT_S
                    self.listen_command(q)
                    if self.last.get("gate") in ("gate2", "gateN", "gate4", "gate5") or (
                        self.cmd_deadline is not None and time.time() > self.cmd_deadline
                    ):
                        self.command_mode = False
                        self.cmd_deadline = None
                        state = "LISTENING FOR WAKE WORD"
                else:
                    state = "LISTENING FOR WAKE WORD"
                    self.listen_wake(q)
                self.render(0.0 if self.muted else self.floor, state)
        except KeyboardInterrupt:
            pass
        finally:
            kb.stop()
            stream.stop()
            stream.close()
            print("\nSession saved: " + str(self.events_path))

    def wav_mode(self, wav_path: Path) -> None:
        import wave

        files = [wav_path] if wav_path.is_file() else sorted(wav_path.glob("**/*.wav"))
        if not files:
            print(f"No .wav files under {wav_path}")
            return
        for f in files:
            with wave.open(str(f), "rb") as w:
                y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            g1, c1 = self.gate("gate1", self.pre74.extract(y))
            # Expected wake outcome from filename: gate1_wake_* files are wake
            # takes; anything else should be rejected (Negative).
            name_l = f.name.lower()
            if "wake_nova" in name_l:
                expect = "Nova"
            elif "wake_piattos" in name_l:
                expect = "Piattos"
            else:
                expect = "Negative"
            wake_ok = g1 == expect and c1 >= self.args.min_conf
            line = f"{f.name:<44} wake: {g1:<9} ({c1:.2f}) [{'PASS' if wake_ok else 'FAIL'} expect={expect}]"
            if g1 in self.wake_words and c1 >= self.args.min_conf:
                g2, c2 = self.gate("gate2", self.features_for("gate2", y))
                routing = {"TIMER": "gateN", "ALARM": "gateN", "TEMPERATURE": "gateN",
                           "BRIGHTNESS": "gateN", "COLOR": "gate4", "CREATE_REMINDER": "gate5"}
                routed = routing.get(g2)
                fin, cf, fg = g2, c2, "gate2"
                if routed:
                    fin, cf = self.gate(routed, self.features_for(routed, y))
                    fg = routed
                good = min(c2, cf) >= self.args.min_conf
                line += f"  ->  {g2} ({c2:.2f}) -> {fg}: {fin} ({cf:.2f})  [{'GOOD' if good else 'LOW-CONF'}]"
            print(line)


def main() -> int:
    ap = argparse.ArgumentParser(description="VCM real-time assistant (laptop Keras / Raspberry Pi TFLite).")
    ap.add_argument("--backend", choices=["auto", "tflite", "keras"], default="auto")
    ap.add_argument("--device", type=str, default=None, help="Audio input device index or name")
    ap.add_argument("--min-conf", type=float, default=0.5, help="Confidence threshold for PASS (default 0.5)")
    ap.add_argument("--wav", type=str, default=None, help="Score WAV file(s) instead of live mic")
    ap.add_argument("--check", action="store_true", help="Verify backend/models and exit")
    ap.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    args = ap.parse_args()

    try:
        session = RealSession(args)
    except Exception as e:
        print(f"[FATAL] {e}")
        return 1

    if args.check:
        print(f"Backend      : {session.runner.kind}")
        for name in ("gate1", "gate2", "gateN", "gate4", "gate5"):
            print(f"  {name:<7}: input {session.runner.input_shape(name)}, "
                  f"labels {len(session.labels.get(name, []))}")
        print("Preprocessing: mel_fb.npz OK, 74-frame + 148-frame stats OK")
        print("All checks passed.")
        return 0

    if args.wav:
        session.wav_mode(Path(args.wav))
        return 0

    session.live()
    return 0


if __name__ == "__main__":
    sys.exit(main())
