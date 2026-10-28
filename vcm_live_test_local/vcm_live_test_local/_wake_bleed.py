"""Wake-bleed: how long is the quiet lead-in of each capture?"""

import pathlib
import wave

import numpy as np

from recording_lab import RecordingStore

APP = pathlib.Path(__file__).resolve().parent
store = RecordingStore(APP / "recordings")


def onset_of(path: pathlib.Path) -> float:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    env = np.abs(data)
    window = int(rate * 0.02)
    kernel = np.ones(window) / window
    rms = np.sqrt(np.convolve(env * env, kernel, mode="same") + 1e-9)
    gate = max(float(rms.max()) * 0.10, 0.01)
    idx = int(np.argmax(rms > gate))
    return idx / rate


def main() -> int:
    rows = [entry for entry in store.list()
            if not str(entry.get("id") or "").startswith("me2h")]
    onsets: list[float] = []
    by_session: dict[str, list[float]] = {}
    for entry in rows:
        path = store.path_of(entry)
        if not path.is_file():
            continue
        value = onset_of(path)
        onsets.append(value)
        by_session.setdefault(str(entry.get("session") or "?"), []).append(value)
    if onsets:
        early = sum(1 for value in onsets if value < 0.05)
        peaky = sum(1 for value in onsets if value < 0.3)
        print("TAKES=" + str(len(onsets)) + " median=" + str(round(float(np.median(onsets)), 2))
              + " start<50ms=" + str(early) + " start<0.3s=" + str(peaky)
              + " quiet>0.5s=" + str(sum(1 for value in onsets if value > 0.5)))
    for session, values in by_session.items():
        print(str(session)[:22] + " median=" + str(round(float(np.median(values)), 2))
              + " n=" + str(len(values)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
