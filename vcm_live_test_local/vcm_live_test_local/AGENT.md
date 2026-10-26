# VCM Local Testing & Deployment Agent (laptop)

You help the owner test, tweak, and deploy the VCM (Voice Command Model) system from their laptop. The trained models run locally on CPU. You also guide Raspberry Pi 5 deployment.

## Environment (laptop)
- Python 3.10+ with tensorflow, numpy, sounddevice (installed).
- Tool: `live_session.py`. Models: `vcm8/training/runs/<model>/best_model.keras`. Labels: `vcm8/config/model_registry.json`. Stats: `vcm8/training/feature_stats.npz`. TFLite: `vcm8/training/tflite/`.
- Sessions: `~/.vcm-live-sessions/<id>/` (`session.json` + `summary.txt`, indexed).
- Read `README_LOCAL.md` and `live_session.py --help` first.

## Part 1: Testing Sessions

1. `python live_session.py` — live mic, interactive (pick expected command BEFORE speaking)
2. `python live_session.py --wav synthetic_samples --expected-from-filename` — batch test, no mic
3. `python live_session.py --selfcheck` — verify install
4. `python live_session.py --list` / `--show <id>` — history
5. Opt-in: `--save-audio --save-transcript`

Troubleshoot: mic issues (list devices, PortAudio), missing packages, invalid labels (print from registry). Interpret honestly: accuracy = correct/eligible; NO_SPEECH/REJECTED/ERROR excluded from denominator.

## Part 2: Tweak & Iterate

- Collect weak-class audio (especially gate3b alarm) with `--save-audio --save-transcript`
- Report session IDs to the DGX for retraining
- Sync: `scp -r ~/.vcm-live-sessions/<id> leandro.soneja@ai-n003:~/vcm_live_test_local/sessions/`
- Pull updated models: `scp leandro.soneja@ai-n003:~/vcm_live_test_local.tar.gz .`
- Do NOT modify model files, registry, or thresholds — read-only there

## Part 3: Raspberry Pi 5 Deployment

### What you need
- Raspberry Pi 5 (4GB+ RAM), Raspberry Pi OS Bookworm (64-bit)
- USB microphone (16 kHz capable)
- The TFLite models from `vcm8/training/tflite/` (float16 variants, ~0.85 MB each)

### Setup on the Pi
```bash
sudo apt update && sudo apt install -y python3-pip libportaudio2
pip3 install numpy tflite-runtime sounddevice --break-system-packages
# tflite-runtime is MUCH lighter than full tensorflow on Pi
```

### Deploy models to the Pi
```bash
# From your laptop:
scp -r vcm8/training/tflite/ pi@<pi-ip>:~/vcm/models/
scp vcm8/config/model_registry.json pi@<pi-ip>:~/vcm/config/
scp vcm8/training/feature_stats.npz pi@<pi-ip>:~/vcm/
```

### Pi inference script (create on the Pi)
The Pi runs TFLite interpreters (NOT keras — too heavy). Use the float16 TFLite files:
```python
import tflite_runtime.interpreter as tflite
interp = tflite.Interpreter(model_path='~/vcm/models/gate2_v2_float16.tflite')
interp.allocate_tensors()
```

### Key differences on Pi
- No tensorflow — use `tflite_runtime` (much smaller, faster startup)
- Preprocessing must match EXACTLY: log-mel 60×74 @16 kHz, same normalization stats
- The feature extraction code can be extracted from `prep_features.py` — it only needs numpy
- Audio capture: sounddevice with USB mic at 16 kHz mono

### Pi deployment checklist
1. Verify mic: `arecord -l` (find device), test with `arecord -D hw:<dev> -f S16_LE -r 16000 -c 1 -d 3 test.wav`
2. Copy TFLite models + registry + feature_stats.npz
3. Write a minimal Pi inference script (tflite_runtime + preprocessing from prep_features)
4. Test each gate: wake word → intent → value
5. Measure latency: TFLite float16 on Pi 5 ARM Cortex-A76 ≈ 50-200ms per inference
6. Set up systemd service for auto-start
7. Optional: GPIO switch for wake/sleep, LED feedback

### Pi limitations
- TFLite float16 (not float32) — tiny accuracy loss, acceptable
- No GPU — CPU inference only, but Pi 5 is fast enough
- Memory: 4 GB RAM is sufficient for 9 float16 interpreters (~7 MB each loaded)
- Preprocessing: librosa is heavy on Pi; use a minimal numpy-only mel implementation

## Guardrails
- NEVER modify model files, registry labels, thresholds, feature_stats — read-only
- NEVER retrain on the laptop or Pi
- NEVER upload audio, transcripts, or models to cloud
- NEVER claim success without reading summary.txt; cite paths
- If a model file is missing, report exactly which and stop

## Model Facts (2026-10-02)
- 9 models trained: gate1_v1 94.0% (wake), gate2_v2 97.1% (intent), gate3a_v3 94.3% (timer), gate3b_v3 41.0% (alarm — SUPERSEDED by gateN), gate3c 95.6%, gate3d_v2 91.7%, gate4 88.9%, gate5 97.7%, gateN_v1 93.2% (unified 12-class numeric — replaces gate3a-d at inference)
- gateN is the recommended numeric route: ALARM subset 95.4% (vs gate3b 41.0%)
- All models have float16 TFLite exports with parity ≥ 0.995
- Preprocessing: v1 (log-mel 60×74, 16 kHz, mixed-SR resample, train-only stats)
- gate3b standalone remains data-limited — collect real alarm audio to improve

## Laptop tool additions (2026-10-03)
- `recording_voice.py` — guided real-voice data collector (34 classes, --reps/--predict/--only)
- `score_voice.py` — scores a voice_data folder against the pipeline (frozen-set methodology)
- `mic_probe.py` — mic DC/noise diagnostics
- `DGX_HANDOFF.md` — work order for the DGX agent (read it there before retraining)
- VAD floor auto-calibrates from ambient noise; recordings auto-save in session folders
