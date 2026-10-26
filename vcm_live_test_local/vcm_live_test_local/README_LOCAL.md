# VCM Live Voice-Command Testing Tool — Local Laptop Package

Test the trained VCM (7-model pipeline) with your own voice from your laptop. Everything runs **locally on your CPU** — no cloud, no GPU needed.

## What's in this package

```text
vcm_live_test_local/
├── live_session.py                  ← the tool (this is all you run)
├── README_LOCAL.md                  ← this file
├── BUILDER_REPORT.md                ← how the tool was built (reference)
├── SYNTH_REPORT.md                  ← how the synthetic samples were made (reference)
├── generate_synthetic_test_set.py   ← (reference) CosyVoice generator used on the DGX
├── vcm8/
│   ├── config/model_registry.json   ← label orders + routing
│   └── training/
│       ├── feature_stats.npz        ← frozen normalization (train-only stats)
│       └── runs/
│           ├── gate2/best_model.keras      (19 intents, 96.4% val)
│           ├── gate3a_v3/best_model.keras  (timer values, 94.3%)
│           ├── gate3b_v3/best_model.keras  (alarm values, 41.0% — known weak)
│           ├── gate3c/best_model.keras     (temperature, 95.6%)
│           ├── gate3d/best_model.keras     (brightness, 90.0%)
│           ├── gate4/best_model.keras      (color, 88.9%)
│           └── gate5/best_model.keras      (reminder, 97.7%)
└── synthetic_samples/               ← 20 TTS voices for quick testing (16 kHz mono WAVs)
```bash

## 1. Requirements (one-time)

Python 3.10+ and three packages:

```bash
pip install tensorflow numpy sounddevice
```bash

- `sounddevice` needs PortAudio. Ubuntu/Debian: `sudo apt install libportaudio2`. macOS: `brew install portaudio`. Windows: pip wheel usually suffices.
- No GPU required — the tool forces CPU inference.

## 2. Start a live session (microphone)

From inside `vcm_live_test_local/`:

```bash
python live_session.py
```bash

That's it. Per attempt it will:
1. Ask you to pick the **expected command first** (numbered menu of all intents/specialist values, or free text) — before you speak, so results can't be biased
2. Record from your mic (stops after ~1.2 s silence or 6 s max)
3. Show **Gate 2's prediction + confidence**, then the routed specialist's result
4. Classify the attempt: CORRECT / WRONG_PREDICTION / NO_SPEECH / REJECTED / ERROR
5. Accumulate running accuracy (correct/eligible) with per-command stats

Quit with `q` or **Ctrl+C** — completed attempts are saved cleanly.

Gate 1 (wake word) shows as **UNAVAILABLE** — no trained wake-word model exists yet; testing starts at Gate 2.

Useful flags:

```bash
python live_session.py --device 2        # pick a specific mic (see --selfcheck output)
python live_session.py --min-confidence 0.6
python live_session.py --silence-s 1.5   # longer trailing-silence window
python live_session.py --save-audio --save-transcript   # opt-in; saved per-session only
```bash

## 3. Batch-test the 20 synthetic samples (no microphone needed)

```bash
python live_session.py --wav synthetic_samples --expected-from-filename
```bash

Filenames encode the intended label (e.g. `gate2_PLAY_MUSIC_f02_...` → `PLAY_MUSIC`), so accuracy, per-command stats, and the confusion matrix are computed automatically.

## 4. Session history

Every session gets a unique ID + timestamp and is saved to:

```bash
~/.vcm-live-sessions/<session_id>/session.json   (machine-readable, per-attempt + per-gate)
~/.vcm-live-sessions/<session_id>/summary.txt    (human-readable)
~/.vcm-live-sessions/sessions_index.json         (index of all sessions)
```bash

Browse history:

```bash
python live_session.py --list
python live_session.py --show <session_id>
```bash

## 5. Sanity-check your install

```bash
python live_session.py --selfcheck
```bash

Verifies all 7 model files load, the registry matches, features preprocess to the right shape. No mic needed.

## Known limitations

- **gate3b (alarm 6AM/8AM/9PM) is weak (~41%)** — expect frequent misclassification there; it's a known data limitation, not a bug.
- Gate 1 wake word is not trained yet (shows UNAVAILABLE).
- Results reflect *this session's samples* — not a substitute for evaluation on a separate authorized dataset.
- Audio/transcripts are NOT saved unless you pass the opt-in flags.

## Where the models came from

Trained on the DGX (ai-n003) on the class MEX2 dataset (train 14,256 / val 1,806, commit `5b23a950`), preprocessing v1 (log-mel 60×74, 16 kHz). Full training evidence: `vcm8/training/TRAINING_RESULTS.md` in the project repo.
