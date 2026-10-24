# DGX Agent Prompt — ME2 VCM dataset location + training brief

> Copy everything inside the block below and paste it to the DGX agent on `ai-n003`.

---

```text
You are the DGX training agent for AI 231 ME2 "Voice Controlled Smart Device" (on-device VCM).
Host ai-n003, working dir ~/vcm_live_test_local/. No cloud upload of audio, ever.

GOAL
1) Confirm you can load the class gold dataset from its canonical DGX location.
2) Inventory the supplemental datasets and report a compatibility verdict per dataset.
3) Only then start the retraining briefs (Gate 2 real-voice fine-tune; Gate 1 wake-word program).

=== DATASET LOCATIONS (authoritative — use these, not older handoff paths) ===

A. PRIMARY / GOLD DATASET (baseline for everything)
   Path:      /data/ai231
   Contents:  the 4 MAIN SPLITS of the class gold dataset (Sir Mark's data, balanced by Ailene
              with real-voice data).
   Loader:    /data/ai231/load.py   <-- use load.py, NOT gold_dataset.py
   First step: copy load.py into your home dir and run it from YOUR account. Do not proceed
              until you have printed actual split sizes and a few sample rows.
   Note:      /data/ai231 is permission-restricted for direct writes. Read-only for you.

B. SUPPLEMENTAL (optional on top of the gold baseline)
   Path:      /data/ai231-fil-supplemental
   What:      Anthony's Filipino-voice supplemental (zero-shot cloned Filipino speakers,
              transcription QA pass). Same schema family: audio path, transcript, command,
              slot_value, is_synthetic, duration_s, whisper_check.
   Mirror:    https://huggingface.co/datasets/martinnavs/ai231-fil-supplemental-data
              (Anthony is still updating it — re-pull before training; record the revision hash.)
             If the DGX copy is stale or missing, pull the HF mirror instead and say so.

C. SECOND SUPPLEMENTAL (peer dataset, HuggingFace)
   URL:       https://huggingface.co/datasets/airimonda/ai231-me2-voice-commands
   What:      ~81.8k rows across 4 subsets. Columns: command, variation, slot_value,
              out_of_scope, bucket, speaker_id, source, is_synthetic, accent_group,
              numerals, duration_s, whisper_transcript. Includes NUMERAL rows and
              OUT_OF_SCOPE buckets. Sources include SpeechCommands v2.
   Download:  hf download airimonda/ai231-me2-voice-commands  (pin the revision hash).

=== LABELS (frozen, do not rename or reorder) ===
20 intents/slots from labels.json:
music_play, search, lights_on, lights_off, lights_dim, lights_bright, timer_set, alarm_set,
temp_up, temp_down, media_play, media_pause, media_next, media_prev, volume_up, volume_down,
reminder_set, reminder_check, call, silence
Wake words are NOT in any dataset: Nova and Piattos are Leandro's own custom schema.
Do not attempt to source them from A/B/C; they come only from the T2 recording program.

=== SPLIT HYGIENE (hard rule) ===
- The frozen test split is locked by SPLIT_LOCK.json (sha256 of the sorted test paths, seed 42).
  Never add, remove, or re-derive it. All new data goes to TRAIN only.
- The laptop's frozen real-voice set is also never trained on.
- Dedupe anything new against existing data by audio hash + (speaker_id, transcript).

=== STEP 1 — LOAD + INVENTORY (do this first, report before training) ===
For /data/ai231, /data/ai231-fil-supplemental, and the HF me2 dataset, report per subset:
row count; command-label distribution mapped into our 20 labels; sample rate; audio format;
speaker count; is_synthetic ratio; duration distribution; license; dataset revision/hash.
Flag any label that does not map 1:1 to our registry. Do NOT silently remap — report first.
Verify preprocessing compatibility: 16 kHz mono (resample via the mixed-SR path if needed),
clip or drop >6 s the way the existing pipeline does.

=== STEP 2 — COMPATIBILITY VERDICT (required before any training) ===
Post one verdict per dataset: USE AS-IS / USE WITH MAPPING / SKIP, with the reason.
Intended usage if accepted:
- fil-supplemental -> Gate 2 intent + Gate N numeric diversity (mix into train, never val/test).
- me2-voice-commands -> (a) NUMERAL rows for Gate N numerals; (b) OUT_OF_SCOPE rows as
  negatives for Gate 1 / Gate 2 rejection behavior; (c) remaining in-scope rows as a Gate 2
  supplement after dedupe against existing MEX2-derived data.

=== STEP 3 — RETRAINING BRIEFS (only after the verdict) ===
T1 Gate 2 real-voice fine-tune (highest impact): add real-voice training folders to the Gate 2
   set with the synthetic data; upsample/weight real samples (2-4x or loss weighting).
   Keep the architecture DS-CNN and preprocessing v1 (log-mel 148x60, 16 kHz, train-only stats).
   If you recompute feature stats, re-validate EVERY gate and say so explicitly.
   Target: >= 80% Gate 2 real-voice accuracy on the frozen real-voice set.
T2 Gate 1 wake words: training data from the T2 recording program only (~50 real seeds per
   word x ~100 augmented variants). Augment TRAIN split only: pitch -3..+3 semitones; time
   stretch 0.85-1.15x; additive noise SNR 15-30 dB; gain jitter +/-3 dB; mild small-room
   reverb; SpecAugment (time mask <=10% frames, freq mask <=4 mel bands); compose 2-3
   factors per variant. Keep negatives the dominant class. Target: >= 90% on real wake takes.
T3 Do NOT invest in standalone gate3b; it is superseded by Gate N.

=== STEP 4 — EVALUATION + DELIVERABLES ===
- Report per-gate val accuracy AND real-voice frozen-set accuracy using the score_voice.py
  methodology (full pipeline per file; wake rows vs Gate 1; value rows vs routed specialist).
- Regression gates that must hold: synthetic batch >= 17/17; frozen real-voice set must not regress.
- Run Ailene's class-standard benchmarks.py and report BOTH 93-class (command: action+value) and
  19-class (intent) accuracy. Make our eval/training logs emit the line format benchmark.py expects
  (check its README and variations.csv first).
- Ship: updated best_model.keras checkpoints + TRAINING_RESULTS.md notes, with registry format
  unchanged (same model list, same label orders) and float16 TFLite exports with parity >= 0.995
  (the Pi depends on them). Record per-source row counts and dataset revisions for attribution.
- Housekeeping: never rename run dirs without updating CHECKPOINT_PATHS in live_session.py.
  When shipping a bundle, extract into a temp dir and copy only vcm8/ over — a previous full
  extraction wiped laptop tools and recorded data.

=== STEP 5 — PUBLISH DIRECTLY TO GITHUB (only when the owner gives you a repo + token) ===
Auth:    export GH_TOKEN=<fine-grained PAT with Contents: read/write on the target repo>
         Never hardcode the token, never commit it, never print it. Verify first:
           gh auth status
         or: curl -sS -H "Authorization: Bearer $GH_TOKEN" https://api.github.com/user
Target:  Leandro supplies <OWNER>/<REPO>. Do NOT invent or guess a repo name, and do NOT
         create a repo under an account you were not given.
Branch:  never push straight to main. Use dgx/<topic>-<YYYYMMDD>, then open a PR.

What goes WHERE (GitHub is not a data lake):
  - plain git:        training/eval code, configs, labels.json, preprocessing specs, manifests,
                      TRAINING_RESULTS.md, benchmark logs, small JSON/CSV.
  - git-lfs:          checkpoints (.keras) and TFLite exports, i.e. anything ~5-100 MB. Run
                      git lfs track "*.keras" "*.tflite" BEFORE the first commit of those files.
  - GitHub Releases:  bundle tarballs. Do not commit tarballs into git.
  - HuggingFace / Zenodo: the dataset itself, including audio. GitHub rejects audio corpora
                      (hard 100 MB per-file limit plus repo size limits), so publish the dataset
                      repo on HF or Zenodo and link it from the GitHub README instead.

Data release boundary: publish ONLY data cleared for release (class gold dataset, peer and
  synthetic supplementals). NEVER publish Leandro's private owner-voice recordings or the
  frozen test split unless he explicitly authorizes it in writing.

Procedure per publish:
  1) confirm the working tree is clean;  2) confirm the remote URL matches <OWNER>/<REPO>;
  3) commit with a message naming the dataset revision/hash;  4) push the branch;
  5) report back the exact commit SHA and PR URL.

If the token, repo, or remote is missing: STOP and say exactly what is missing. Do not
substitute another host or account.

=== GUARDRAILS ===
- No cloud upload of private audio, transcripts, or weights, EXCEPT the deliberate,
  owner-authorized release path in STEP 5 (public dataset/artifact publishing).
- Do not edit the label registry or inference thresholds.
- Do not retrain on the laptop or the Pi.
- If the gold loader or a dataset path is unavailable, STOP and report the exact path and error
  instead of substituting a different dataset.

=== REPORT FORMAT ===
1) Load status of /data/ai231 (loader used, split sizes, sample rows)
2) Per-dataset inventory table + label-mapping exceptions
3) Per-dataset verdict
4) Then, and only then, T1/T2 results with the regression gates
5) Publish status: repo, branch, commit SHA, PR URL (or the exact blocker)
State clearly which claims are measured and which are not.
```
