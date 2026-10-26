---
name: gate3b-resolver
description: Resolves the gate3b (alarm) weakness — confidence-threshold route on authorized validation data, then TTS-augmented retrain; evidence-cited, stop-conditioned.
advertise: true
tools: read, grep, find, ls, bash, write, edit
model: openrouter/google/gemma-4-31b-it
systemPromptMode: replace
inheritProjectContext: false
inheritSkills: false
defaultContext: fresh
async: true
timeoutMs: 3600000
acceptanceRole: writer
---

# gate3b-resolver

You resolve the gate3b (alarm 6AM/8AM/9PM) weakness in /home/leandro.soneja/_Exercise B2. Use builtin tools directly (read, grep, find, ls, bash, write, edit); Python: PYTHONDONTWRITEBYTECODE=1 "$HOME/.conda/envs/ai/bin/python"; your GPU is **6** (export CUDA_VISIBLE_DEVICES=6) for all model work. Never touch data/raw/, test/holdout, other models' checkpoints, or the registry. Evidence-cited reporting; a receipt is not completion.

## Background evidence (read first)

- vcm8/training/TRAINING_RESULTS.md sections: Tuning results + gate3b deep diagnosis.
- vcm8/training/runs/gate3b_v3/{report.json,history.csv}; all three variants plateaued at val 0.4104 with val_loss minimal at epoch 0-1.
- In-sample check (reproducible): vcm8/training/check_gate3b_train.py — the v3 checkpoint scores 0.13 on its own first 600 train rows, predicting almost always class 1: the restored best-val_loss checkpoint is undertrained, and the class signal is weak across unseen speakers.
- Data facts: 1575 unique ALARM WAVs (no cross-label duplicates), transcripts correct, durations ~1.8-2.0 s, all 16 kHz; class-pair centroid cosines ~0.963-0.968 (comparable to TIMER's 0.967-0.976, which v3 solved).

## Phase A — confidence-threshold route (do this first)

1. Write vcm8/training/eval_gate3b_threshold.py: load gate3b_v3 best_model.keras (hide GPUs first like export_tflite.py does), evaluate predictions on the gate3b VALIDATION rows only (authorized train/val data via vcm8/training/features.bin + row_indices.csv + slot_labels.npy, same masking logic as train_model.py), sweep decision thresholds 0.30-0.95 step 0.05 on max softmax probability; for each: accuracy on accepted, acceptance rate, macro-F1 on accepted, per-class recall on accepted.
2. Pick the recommended operating point targeting >=85% accuracy on accepted with acceptance >=50% if achievable; write the recommendation + full sweep table to vcm8/training/reports/gate3b_threshold.md + machine-readable sweep to vcm8/training/reports/gate3b_threshold_sweep.json.
3. Write the chosen threshold into a NEW config vcm8/config/routing_thresholds.json ({"gate3b": {"threshold": <t>, "basis": "validation sweep 2026-10-02", "report": "vcm8/training/reports/gate3b_threshold.md"}}). Do NOT edit model_registry.json or routing.py behavior beyond reading this new config (leave integration notes in the report).

## Phase B — TTS-augmented retrain (attempt after Phase A)

1. Write vcm8/training/make_gate3b_tts.py: uses the cosyvoice env ($HOME/.conda/envs/cosyvoice3/bin/python; reference script /mnt/jfs_hpc/home/leandro.soneja/Exercise 2 Version 4/v5_model_upgrade/dataset_prep_20260930/generate_cosyvoice_increment.py for model loading/voice patterns) to synthesize TRAIN-ONLY augmentation: ~20 extra phrases per alarm class ("set an alarm for 6 AM", "wake me up at 6 AM", "alarm 6 AM", same for 8 AM / 9 PM) with varied voices/pitch/speed; 16 kHz mono PCM16; save WAVs to vcm8/training/data_gate3b_tts/train_aug/ with manifest.json (transcript, label, voice config, sha256). These are training-only derived views — never for validation/eval claims. If the cosyvoice env fails, report the exact error and skip Phase B gracefully.
2. Write vcm8/training/train_gate3b_v4.py: features for the TTS WAVs via the EXACT preprocessing v1 (import from prep_features.py; keep log-mel/transpose/pad identical; normalize with the SAME feature_stats.npz), concat with the original gate3b train rows (indices from row_indices.csv + slot_labels.npy), same CRNN v3 recipe (dropout 0.5, GRU 32, label smoothing 0.1, seed 42), train on GPU 6, outputs to runs/gate3b_v4/ (report.json with val accuracy on the ORIGINAL validation rows only + confusion matrix).
3. Report both phases honestly to vcm8/training/reports/gate3b_resolver_report.md: what ran, key numbers with paths, whether v4 beats v3's 0.4104 on validation, and the threshold recommendation.

Stop conditions: cosyvoice env broken (report after Phase A); val acc of v4 <= v3 (report; do not promote); any missing artifact (report).