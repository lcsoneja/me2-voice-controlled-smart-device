"""Mic capture diagnostic: measures DC offset, noise floor, and tests captured audio through the VCM pipeline."""

import importlib.util
import sys
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("live_session", HERE / "live_session.py")
assert spec is not None and spec.loader is not None, "failed to load live_session.py spec"
ls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ls)

SR = ls.DEFAULT_SAMPLE_RATE
DUR = 4.0


def main():
    device = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Recording {DUR:.0f}s from mic (device={device}). Speak a command like 'play some music' now...")
    buf = sd.rec(int(DUR * SR), samplerate=SR, channels=1, dtype="float32", device=device)
    sd.wait()
    y = buf.flatten().astype(np.float32)

    dc = float(np.mean(y))
    ac = y - dc
    rms_all = float(np.sqrt(np.mean(y**2)))
    rms_ac = float(np.sqrt(np.mean(ac**2)))
    peak = float(np.max(np.abs(y)))

    print(f"DC offset       : {dc:+.5f}   <-- anything beyond ~0.005 is a problem")
    print(f"RMS (raw)       : {rms_all:.5f}")
    print(f"RMS (DC-removed): {rms_ac:.5f}")
    print(f"Peak            : {peak:.3f} (clipping if ~1.0)")
    print(f"Speech-floor test: raw VAD would trigger on ambient? {'YES (bad)' if rms_all >= ls.DEFAULT_RMS_SPEECH_FLOOR else 'no'}")

    out = HERE / "mic_probe.wav"
    pcm = (np.clip(y, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    print(f"Saved capture   : {out}")

    audio, sr_in = ls.read_audio_file(out)
    fx = ls.FeatureExtractor(ls.DEFAULT_FEATURE_STATS_PATH)
    feats = fx.extract_features(audio, sr_in=sr_in)
    print(f"Feature shape   : {feats.shape} (OK if (1, 74, 60, 1))")

    vp = ls.VCMModelPipeline(HERE, HERE / ls.DEFAULT_REGISTRY_PATH, HERE / ls.DEFAULT_FEATURE_STATS_PATH)
    out2 = vp.run_pipeline(audio, sr=sr_in, min_confidence=0.0)
    g2 = out2["gate2"]
    print(f"Gate2 (live-captured file) predicted: {g2['predicted_label']} (conf {g2['confidence']:.3f})")


if __name__ == "__main__":
    main()
