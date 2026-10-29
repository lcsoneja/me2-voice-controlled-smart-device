"""Why does v126 (180-mel) score near chance? Try mel-filterbank variants.

Hypothesis: the shipped spec records n_mels=180 but not the mel filterbank
parameters (fmin/fmax/htk/norm), and the runner uses librosa defaults. If the
training recipe used different settings the features mismatch and accuracy
collapses. Score 20 real holdout clips per variant.
"""

import json
import pathlib
import wave

import librosa
import numpy as np

import gate1_server as gs
import _bench_gate2_holdout as bench

HERE = pathlib.Path(__file__).resolve().parent
VARIANTS = (
    ("librosa default (fmin=0, fmax=8000, slaney)", {}),
    ("fmin=20 fmax=7600", {"fmin": 20.0, "fmax": 7600.0}),
    ("fmax=7900", {"fmax": 7900.0}),
    ("htk=True", {"htk": True}),
)


class VariantRunner(gs.Gate2PackageRunner):
    def __init__(self, name: str, mel_kwargs: dict):
        super().__init__(name)
        self.mel_kwargs = mel_kwargs

    def _extract_features(self, waveform):
        span = self.source_frames * self.hop_length + self.n_fft
        y = np.asarray(waveform, dtype=np.float32).reshape(-1)[-span:]
        mel = librosa.feature.melspectrogram(
            y=y, sr=self.sample_rate, n_fft=self.n_fft,
            hop_length=self.hop_length, win_length=self.win_length,
            n_mels=self.source_mels, center=self.center, power=self.power,
            **self.mel_kwargs,
        )
        features = np.log1p(mel).T.astype(np.float32)
        if len(features) < self.source_frames:
            features = np.pad(features, ((0, self.source_frames - len(features)), (0, 0)))
        elif len(features) > self.source_frames:
            start = (len(features) - self.source_frames) // 2
            features = features[start:start + self.source_frames]
        features = ((features - self.mean) / (self.std + 1e-8)).astype(np.float32)
        if features.shape != (self.frames, self.n_mels):
            features = gs._resize_area(features, self.frames, self.n_mels)
        return features


def main() -> int:
    index = json.loads((HERE / "recordings" / "index.json").read_text(encoding="utf-8"))
    recs = index["recordings"] if isinstance(index, dict) else index
    real = [r for r in recs if "me2h" in str(r.get("id"))
            and "(real)" in str(r.get("label") or "").lower()
            and str(r.get("action") or "").strip()]
    clips = []
    for rec in real[:20]:
        path = HERE / "recordings" / str(rec["file"])
        if path.is_file():
            clips.append((rec, bench.load_wav(path)))
    print("clips=" + str(len(clips)))
    for label, kwargs in VARIANTS:
        runner = VariantRunner("gate2v126_mels180", kwargs)
        hits = 0
        for rec, clip in clips:
            probs = runner.predict(clip)
            if bench.same_command(bench.top_intent(list(runner.labels), probs), rec.get("action")):
                hits += 1
        print(label.ljust(44) + " -> " + str(hits) + "/" + str(len(clips)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
