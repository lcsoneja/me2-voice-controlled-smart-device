# DGX HANDOFF — Laptop VCM Testing Results (2026-10-02/03)

**From:** laptop testing agent (Leandro's machine)
**To:** DGX pi-agent (ai-n003, ~/vcm_live_test_local/)
**Status:** local testing infrastructure fixed and validated; real-voice accuracy gap identified and quantified. Data collection started. Retraining request follows.

---

## 1. What happened on the laptop

### 1.1 Tool fixes (live_session.py, v1.0.0 locally patched)
- Fixed stale checkpoint paths: gate2 -> runs/gate2_v2, gate3d -> runs/gate3d_v2 (selfcheck previously FAILED on these).
- Fixed run_pipeline bug: self.pipeline -> self.models_meta (all live/batch inference errored before this).
- Wake-word attempts now scored against gate1 (previously forced to ERROR).
- UI: command menu printed once at start (reopen with 'm'), one-line PASS/FAIL result per attempt, live VU meter during recording (--no-meter disables).
- **VAD auto-calibration:** the default speech floor (RMS 0.005) sat far below the laptop room-noise floor (~0.019 measured), so live recordings triggered on ambient noise and the model only ever saw pre-speech noise -> 0/23 live. The recorder now measures ~0.8s of ambient per attempt and raises the floor to max(0.005, 2.5 x robust-ambient, capped at 0.05). This was the root cause of the 0/23 live session; do not interpret the low numbers without this context.
- Session folders now carry the quit time in the name (session_START_ended-END), always collect per-attempt WAVs in audio/, and write session_log.txt + summary.txt + session.json.
- New tools: recording_voice.py (guided data collector), score_voice.py (scores a collection folder against the pipeline), mic_probe.py (mic DC/noise diagnostics).

### 1.2 gateN promoted to inference routing (laptop-side)
- TIMER / ALARM / TEMPERATURE / BRIGHTNESS now route to **gateN** (unified 12-class) instead of gate3a/3b/3c/3d. Registry file untouched; override lives in the tool. COLOR -> gate4, CREATE_REMINDER -> gate5 unchanged.
- **Checkpoint selection:** gateN_v2_compound (148-frame preprocessing, feature_stats_148.npz) is used automatically when present; otherwise falls back to gateN_v1 (74-frame). Both verified.
- Verified: synthetic batch regression 17/17 with 0 errors (previously 16/16 with 1 rejection on gate3b); the 6 AM alarm sample is CORRECT at conf 1.00. Selfcheck passes for all 9 checkpoints.

### 1.3 Real-voice baseline (the actionable finding)
First real-voice pass (Leandro, laptop mic, 34 utterances, one per class), scored against the 9-model pipeline with gateN_v1:

- **Overall: 18 / 34 (52.9%)**
- **Slot values (timer/alarm/temp/brightness/color/reminder): 11/12 (92%)** — gateN + specialists handle real voice well. Only miss: "20 percent" -> "60 percent" (slot-level; gate2 intent was correct).
- **gate2 direct intents: ~5/13** — misses scattered and mid-confidence (PLAY_MUSIC->CREATE_REMINDER, WEATHER->COLOR, LIGHT_ON->CREATE_REMINDER, CALL->PAUSE, MESSAGE->VOLUME_UP, TIME->LIST_REMINDERS, LIST_REMINDERS->TEMPERATURE...). Classic real-voice vs TTS domain shift: gate2 has 97% val on synthetic data but is out-of-distribution on real mic speech.
- **gate1 wake words: 0/2 on Nova/Piattos** — gate1 confidently predicts "Negative" (conf 1.00) for real-voice wake words. It only passed the Negative sample. gate1 also needs real-voice wake data.

**Conclusion: the accuracy ceiling is real-voice training data for gate2 and gate1, not architecture. Slots are solved by gateN.**

NOTE: the frozen voice test folder (voice_data/voice_20261003_000023) was accidentally deleted during the tarball overwrite on the laptop; Leandro will re-record it. Treat any re-recorded set as the new frozen set.

---

## 2. Data inventory (this folder is self-contained)

| Path | What it is | Status |
|---|---|---|
| voice_data/ | real-voice collections + manifest.csv | FROZEN TEST SET + future train_pass folders — never train on the frozen one |
| laptop_sessions/ | 10 recorded laptop sessions (43 WAVs) incl. live-mic attempts (expected labels in session.json) | usable as training data after label audit (early sessions are noise-triggered, pre-VAD-fix) |
| mic_probe.wav | 4s laptop mic capture (diagnostic) | reference for mic channel character |
| live_session.py / recording_voice.py / score_voice.py / mic_probe.py | updated laptop tools | sync back if you change interfaces |

Manifest schema (recording_voice.py): filename, category (wake/intent/value), intent, value, suggested phrase, duration_s, recorded_at. Labels: category=wake -> value is the wake label (score vs gate1); category=intent -> intent; category=value -> pair (intent routed to gateN/gate4/gate5, value must match specialist prediction).

---

## 3. Retraining tasks for the DGX agent

### T1 — gate2 real-voice fine-tune (highest impact)
- Add the real-voice training folders (NOT the frozen test set) to the gate2 training set, mixed with the existing synthetic data.
- Upsample/balance the real-voice subset (it is small relative to synthetic); consider 2-4x duplication or loss weighting on real samples.
- Target: gate2 real-voice accuracy (frozen test set) >= 80% (baseline 5/13 direct intents).
- Keep architecture DS-CNN and preprocessing v1 (log-mel 60x74, 16 kHz, train-only stats). If you must recompute feature stats, re-validate ALL gates and say so explicitly.

### T2 — gate1 wake-word data program (plan: ~50 real voices x ~100 augmented variants)
Leandro will record ~50 real samples per wake word (Nova, Piattos) from multiple speakers/distances/speeds. Recommended recording recipe per speaker: 10 takes Nova + 10 takes Piattos varying: distance (20/50/100 cm), loudness, speed (normal/slow), intonation (flat/calling), background (quiet/normal room). Also record ~100 negatives per session ("Negative" items + natural speech).

Augmentation on top of the ~50 real seeds (TRAINING SPLIT ONLY — never augment the frozen test set):
- pitch shift: -3..+3 semitones (uniform, per variant)
- time stretch / speed: 0.85x..1.15x
- additive noise: SNR 15-30 dB (laptop ambient RMS ~0.019 measured via mic_probe.py)
- gain jitter: +/-3 dB
- mild reverb (small-room IR approximations)
- SpecAugment: time-mask up to 10% of frames, freq-mask up to 4 mel bands
- Compose 2-3 factors randomly per variant -> ~100 variants per seed is reasonable; keep original seeds in training too.
- Keep class balance: negatives must remain the dominant class in the wake training set.

Target: gate1 >= 90% on real-voice wake-word test takes (baseline 0/2).

### T3 — gate3b/gateN alarm slot
- gateN already fixed the inference route (ALARM subset 95.4% val; v2_compound verified on the laptop batch). Do NOT invest in standalone gate3b; it stays superseded.
- Optional: if alarm slot errors persist on real voice, add more real "6 AM/8 AM/9 PM" utterances to gateN's training set rather than reviving gate3b.

### T4 — Evaluation protocol (mandatory)
1. Report per-gate val accuracy AND real-voice frozen-set accuracy (methodology = score_voice.py: run full pipeline per file, wake rows scored vs gate1, value rows vs routed specialist).
2. Regression gates before shipping: synthetic batch (in repo synthetic_samples/) must stay >= 17/17; frozen real-voice set must not regress.
3. Deliverables: updated bundle with new best_model.keras checkpoints + TRAINING_RESULTS.md notes; keep registry format identical (9 models, same label orders); keep float16 TFLite exports with parity >= 0.995 (Pi deployment depends on them). If gateN_v2_compound is promoted, update model_registry.json status AND ship gateN_v2 float16 TFLite (missing today).
4. After pulling new models, the laptop will run: live_session.py --selfcheck, synthetic batch, and score_voice.py on the frozen set. Results get reported back.

### T5 — Housekeeping
- Do not renumber/rename model run dirs without updating CHECKPOINT_PATHS in live_session.py.
- When shipping a new bundle, DO NOT delete laptop-side files that are not part of the bundle (the last extraction wiped the laptop tools, handoff doc, and recorded data — see note in 1.3). Prefer extracting into a temp dir and copying only vcm8/ over.
- Guardrails from AGENT.md remain: no cloud upload of audio, no registry/threshold edits by the laptop side, no retraining on laptop/Pi.

### T6 — Preprocessing ablation for gateN (is 148x60x1 actually optimal?)
gateN_v2_compound doubled the time window (74 -> 148 frames, hop 640) without evidence it is the best shape. Before locking it in, run a small ablation (cheap: gateN is a small model) over:
- **frames x hop grid:** 74/148 frames @ hop 640 (current), 148/297 frames @ hop 320 (finer 20 ms time resolution, same ~5.9 s window), 74 @ hop 320 (1.5 s fine window)
- **mel bands:** 60 (current) vs 80
- **extra channels (stretch):** delta-mel as channel 2 (1, F, 60, 2) — only if trivially supported by the DS-CNN input layer

Evaluate every variant with the SAME protocol:
1. Per-class val accuracy (alarm subset especially).
2. Synthetic batch regression >= 17/17 via the laptop tool.
3. Real-voice frozen-set scoring (score_voice.py methodology) once Leandro re-records it.
4. **Measured Pi 5 inference latency** per variant (tflite_runtime, ARM Cortex-A76) — the TFLite export must exist for each candidate; report ms/inference and RAM.

Promotion rule: a variant wins only if it beats the incumbent on (2) and (3) AND its Pi latency stays within the real-time budget (< ~300 ms with all 5 interpreters loaded). Ship the winner as gateN_v3 with updated registry entry, feature stats npz, preprocessing json, AND float16 TFLite export. Document the ablation table in TRAINING_RESULTS.md.

Note for tooling: the laptop tools already support per-model input shapes generically (live_session.py FeatureExtractor takes target_frames; real_session.py reads each model's input_shape), so any new frame count works without laptop-side changes as long as the stats npz and preprocessing json ship alongside.

---

## 4. How Leandro will feed you more data
- recording_voice.py --reps 3 --predict (all 34 classes, ~100/pass) into voice_data/train_pass*/
- recording_voice.py --only ALARM / --only "Nova" style focused runs for weak classes
- Wake-word multi-speaker sessions per T2 above (different people's voices, 50 seeds/word target)
- Each folder has manifest.csv with labels; session.json in laptop_sessions/ has per-attempt expected labels for the live recordings.

---

## 5. NEW external datasets (recently added by classmates) — DGX agent to download and review

**IMPORTANT: DGX_AGENT will download BOTH HuggingFace datasets on the DGX server (online) and review them CONCURRENTLY using subagents (one per dataset), then report compatibility before any training integration.**

| Dataset | Observed content (laptop-side preview) |
|---|---|
| https://huggingface.co/datasets/martinnavs/ai231-fil-supplemental-data | Filipino-accented SYNTHETIC TTS ("fil50 persona": zero-shot voice clones from reference speakers, e.g. ilonggo1, with transcription QA pass). Schema matches our class format: audio path, transcript, command, slot_value, is_synthetic, duration_s, whisper_check. Commands observed: STOP, TIMER, TEMPERATURE, CREATE_REMINDER, VOLUME_DOWN, WEATHER, ... |
| https://huggingface.co/datasets/airimonda/ai231-me2-voice-commands | ~81.8k rows, 4 subsets, same schema family (command, variation, slot_value, out_of_scope, bucket, speaker_id, source, is_synthetic, accent_group, numerals, duration_s, whisper_transcript). Sources include SpeechCommands v2. Contains NUMERAL rows and OUT_OF_SCOPE buckets. |

### Integration instructions for DGX_AGENT (run these checks with subagents, in parallel)
1. **Download & inventory (both datasets, concurrent):** hf download / datasets.load; report per subset: row count, command label distribution, sample rate, audio format, speaker count, is_synthetic ratio, license.
2. **Label mapping check:** map every observed command label to our 20-label registry (labels.json). Flag any label that does not map 1:1 (e.g. casing, extra intents). Do NOT silently remap — report first.
3. **Wake words — NOT COVERED:** Nova and Piattos are Leandro's OWN custom schema and do NOT appear in either dataset. Wake-word data still comes exclusively from the T2 recording program. Do not try to source Nova/Piattos from these datasets.
4. **Usage per dataset:**
   - fil-supplemental: additional synthetic Filipino-voice data for gate2 (intent) and gateN (numeric values) — directly increases accent/voice diversity. Treat like existing TTS gap-fill data (mix into training, keep val/test untouched).
   - me2-voice-commands: (a) NUMERAL rows -> gateN numeral robustness; (b) OUT_OF_SCOPE rows -> negatives for gate1/gate2 rejection behavior; (c) remaining in-scope rows -> gate2 supplement. Watch for overlap with the existing MEX2-derived data on the DGX — dedupe by audio hash + (speaker_id, transcript) before adding.
5. **Splits hygiene:** new data goes to TRAIN split only (or train+val if volume is large and dedup-verified); the frozen test split (SPLIT_LOCK.json) and the laptop frozen voice test set are NEVER modified.
6. **Preprocessing compatibility:** verify 16 kHz mono (resample if needed per preprocessing v1 mixed-SR path) and duration distribution; drop or clip >6 s like the existing pipeline.
7. **Provenance:** record dataset revision/hash + per-source row counts in TRAINING_RESULTS.md so the final report can attribute gains to each source.
8. **Report back:** after the concurrent subagent reviews, post a compatibility verdict per dataset (USE AS-IS / USE WITH MAPPING / SKIP + reason) before retraining T1/T2.

---

## 6. CLASS INFRA UPDATE (group chat 2026-10-02/03) — supersedes parts of the plan above

### 6.1 Gold dataset is now on the DGX cluster (USE THIS, it supersedes the old local vcm8 dataset assumption)
- Location: **/data/ai231** — contains the 4 MAIN SPLITS of the class gold dataset (Sir Mark's data, balanced by Ailene with real-voice data).
- Loader: **load.py** (NOT gold_dataset.py) in /data/ai231. Copy load.py to your home directory and run it to verify the dataset loads from your account before anything else.
- Supplemental data: **/data/ai231-fil-supplemental** (Anthony's Filipino-voice supplemental, same as HF martinnavs/ai231-fil-supplemental-data which he is still updating — re-pull before training). The main /data/ai231 folder is permission-restricted for direct writes; supplemental lives in its own folder.
- Baseline stays the gold dataset; supplemental data is optional on top, per model architecture.

### 6.2 Documented class-wide accent gap (validates our T1/T2 priority)
- Anthony Navarez measured: real Filipino speech is only 5.6% of train command clips (590/10,463), 4.3% of test (189/4,367), and 45% of the holdout (84/186) — from a single speaker per split.
- Models trained on the public train split score **17-27% on that Filipino speaker's clips vs 88-96% on the holdout's synthetic voices**.
- This independently confirms our laptop finding (real-voice baseline 52.9% vs 100% synthetic batch). Our real-voice data plan (T1/T2) targets exactly this gap.

### 6.3 Class-standard benchmark (Ailene's vcm-benchmarks) — REQUIRED for our deliverable
- The benchmark validator now accepts BOTH schemas: **93-class** (command accuracy = correct action AND correct value; 19 intents with variants, 6 slotted) and **19-class** (intent accuracy). Both are reported and comparable.
- benchmarks.py also includes mic tests + sound checks, and parses our logs: our training/eval log format must match the lines benchmark.py expects (there is a variations.csv in the benchmark repo).
- Holdout: 218 trials / 186 command clips. Sir prefers LIVE RPi listening sessions over feeding the holdout file (the honest always-listening + wake-word test).
- Class reality check: peers report high benchmark scores (e.g. 86.8%) with poor actual inference — the benchmark-vs-real-world gap is class-wide. Our frozen real-voice set + score_voice.py is our internal honesty metric; benchmark.py is the class-standard metric. Report BOTH.

### 6.4 Required additions to our T4 evaluation protocol
1. After retraining, run our model through Ailene's benchmarks.py and report: command accuracy (93), intent accuracy (19), and the synth-vs-human split from its log files.
2. Make our eval/training logs emit the exact line formats benchmark.py expects (check the benchmark repo README + variations.csv before finalizing log format).
3. Plan a live RPi listening benchmark session (218 trials) for the final demo; the non-live holdout-feed method is at-own-risk per Ailene and under-reports wake-word/always-listening behavior.
4. Keep reporting our two internal metrics alongside: frozen real-voice set (score_voice.py) and synthetic batch regression (>= 17/17).
5. Wake words differing per group is accepted class-wide (defense: avoid all VCMs waking simultaneously) — no schema change needed for Nova/Piattos.
6. Open class question to watch: whether non-exact-match utterances belong in the collated test set (Kio's question, unresolved). If resolved, re-check our label mapping against the final test manifest.
