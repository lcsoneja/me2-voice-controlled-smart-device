# B2 training - next steps tracker

Updated: 2026-10-02 — **Round-2 weak-class retrains done**: `gate2_v2` (0.9712) and `gate3d_v2` (0.9167) promoted, `gate4_v2` neutral (v1 kept); **stage 9 DONE**. All 9 models trained (7 MEX2 + gate1 + unified gateN); registry `gate2`/`gate3d` point at the v2 checkpoints. Open items now: **6b int8** (BLOCKED, TF converter bug). Next verification: live-mic false-wake testing (`vcm8/live_test/live_session.py`).

Updated: 2026-10-03 — **FINAL DELIVERABLE = a PDF mini-paper (short-paper format) covering the full VCM journey** end to end: Gate 1 audit/rebuild → frozen preprocessing → the 9 promoted models → tuning variants and negative results (`gate3b` collapse, `gate4_v2` neutral) → the int8 blocker → the 148-frame study → real-time/on-device constraints.
All `.md` documentation is the source material that feeds that paper, so every **accuracy, epoch count/curve, confusion matrix, per-class metric and hash must be present, structured (verbatim raw floats + explicit tables) and complete** in: `vcm8/training/TRAINING_RESULTS.md` (canonical results + `## Epoch-curve summaries — all 9 promoted models`), `vcm8/training/MODEL_PERFORMANCE.md` (per-model per-class tables + full confusion matrices), this stage board, and `vcm8/training/RUNS.md`.
Known gaps to close before the paper (state, not hidden): (a) `MODEL_PERFORMANCE.md` still documents 23 runs while 28 `vcm8/training/runs/*/report.json` exist — missing there: `gate2_v2_148`, `gateN_v2_148`, `gateN_v3_lr5e4`, `gate2_v3`, `gateN_scratch`; (b) `gateN_v2_148` has no prose report (only `report.json`/`history.csv`); (c) conflict flags still open — `gateN_v3_fil_report.md` vs `gateN_v3/report.json`, `gate3b_v5` unregistered, `gate3b` variant unnamed, gate4 v1/vs v2 wording. Also: 148-frame runs (see `TRAINING_RESULTS.md`) change `input_shape` to `(148, 60, 1)`, so an on-device buffer-length decision belongs in the paper.

## Stage board

| # | Stage | Status | Evidence to check |
|---|-------|--------|-------------------|
| 1 | Fetch MEX2 train/val (16,062 files, commit 5b23a950) | DONE - CHECKPOINT1 PASS | data/mex2/FETCH_MANIFEST.json; 0 missing; speakers s1-s90 only; 160/160 sample SHA-256 match |
| 2 | Preprocessing (features.bin, stats, row_indices) | DONE | artifacts: features.bin, feature_stats.npz, row_indices.csv, gate2_labels.npy, slot_labels.npy; preprocessing_v1_hash df881e28... |
| 3 | Smoke gate (gate2, 200 rows, 2 epochs, GPU1) | DONE | bash vcm8/training/smoke_test.sh -> exit 0 + runs/gate2/report.json |
| 4 | Full wave launch (gate2 GPU1; gate3a/b GPU3; gate3c/d GPU4; gate4/5 GPU5-7) | DONE | bash vcm8/training/launch_wave.sh -> RUNS.md PIDs, per-model logs |
| 5 | Monitor and verify reports | DONE - all 7 models | runs/{gate2,gate3a,gate3b,gate3c,gate3d,gate4,gate5}/report.json + history.csv; results table in vcm8/training/TRAINING_RESULTS.md |
| 6 | gate3a / gate3b re-tuning (3 variants each) | DONE | gate3a SOLVED by v3 (`runs/gate3a_v3/report.json` 0.9432, promoted); gate3b exhausted v1/v2/v3 all 0.4104 (`runs/gate3b_v{1,2,3}/report.json`), root cause in TRAINING_RESULTS.md "gate3b deep diagnosis" |
| 6c | gate3b mitigation (threshold routing + TTS retrain) | DONE - both NEGATIVE | Threshold route **NOT VIABLE**: 0.55 -> accuracy 0.6667 at 3.5% acceptance, single-class collapse (`vcm8/training/reports/gate3b_threshold_sweep.json`, `gate3b_threshold.md`); `vcm8/config/routing_thresholds.json` records `viable`=false. TTS-augmented `gate3b_v4` 0.3642 < v3 0.4104 (`vcm8/training/runs/gate3b_v4/report.json`). Remaining option: more real ALARM training data, or accept known-weak |
| 6a | TFLite export (float32 + float16, 5 models: gate2, gate3c, gate3d, gate4, gate5) | DONE | `vcm8/training/tflite/*.tflite` + `*.json`; float32 1.676-1.684 MB parity 1.000; float16 0.852-0.857 MB parity 1.000 (gate4 0.995) |
| 6b | int8 quantization | BLOCKED - TF 2.21 converter bug (GRU-general) | Bidirectional gate2 AND unidirectional `gate2_uni` both exit rc=139 (SIGSEGV); repro log `vcm8/training/reports/export_int8_segfault.log`; `gate2_uni` trained to 0.9059 (`vcm8/training/runs/gate2_uni/report.json`). TF 2.21.0 is the latest stable (no upgrade path) and the crash is GRU-general (`vcm8/training/reports/int8_resolver_report.md`). Options in TRAINING_RESULTS.md int8 recommendations: TCN/1D-Conv replacement (recommended) or float16 fallback |
| 7 | Gate 1 data rebuild + training (wake word) | DONE - rebuilt + trained, val_acc 0.9400 | Rebuild: `vcm8/training/data_gate1/rebuild_evidence.json` (4,426 -> 3,788 rows; 633 quarantined, 5 neg-dup dropped, 0 overlap) + `vcm8/training/reports/gate1_rebuild_report.md`. Training: `vcm8/training/runs/gate1_v1/report.json` val_accuracy 0.9400 / val_loss 0.1581 (3,738 train / 50 val); checkpoint `runs/gate1_v1/best_model.keras`; curves `history.csv`. Provenance in `vcm8/training/reports/gate1_resolver_report.md`. Next: live-mic false-wake test `vcm8/live_test/live_session.py` |
| 8 | Unified numerical model `gateN` (12-class: timer+alarm+temp+brightness) | DONE - trained, val_acc 0.9323 | `vcm8/training/runs/gateN_v1/report.json` val_accuracy 0.932299017906189 (661/709 val), val_loss 0.1954, param_count 414,732; per-class recall >= 0.8333; ALARM subset 0.9538 (vs gate3b_v3 0.4104); checkpoint `runs/gateN_v1/best_model.keras`; registry `trained_val_acc_0.9323_recommended_promotion`. Replaces gate3a-d at inference |
| 9 | Round-2 weak-class retrains (`gate4_v2`, `gate3d_v2`, `gate2_v2`) | DONE - 2 of 3 promoted | `vcm8/training/runs/{gate2_v2,gate3d_v2,gate4_v2}/report.json`; `gate2_v2` 0.9712 (promoted), `gate3d_v2` 0.9167 (promoted), `gate4_v2` 0.8833 (neutral, v1 kept); report `vcm8/training/reports/weak_class_v2_results.md` |
| 10 | **Final deliverable: PDF mini-paper (short paper)** covering the full VCM journey (data audit → preprocessing → models → variants/negatives → int8 blocker → 148-frame study → deployment) | PENDING | Source of every number/table: `vcm8/training/TRAINING_RESULTS.md` (canonical results + `## Epoch-curve summaries — all 9 promoted models` + `## 148-frame window experiments`), `vcm8/training/MODEL_PERFORMANCE.md` (per-class tables + full confusion matrices), this stage board, `vcm8/training/RUNS.md`, `vcm8/config/model_registry.json`, `vcm8/status.json`, per-run `runs/*/report.json` + `history.csv`. Requirement: accuracies, epochs and confusion matrices structured and **complete** (no placeholders); close the runs-documented gap listed in the header note (`MODEL_PERFORMANCE.md` 23 runs vs 28 `report.json` files: missing `gate2_v2_148`, `gateN_v2_148`, `gateN_v3_lr5e4`, `gate2_v3`, `gateN_scratch`) |

## Verified results (stage 5) - from vcm8/training/runs/*/report.json

- gate2 0.9635 (14,256/1,806 rows) | gate3a 0.4659 (1,389/176) | gate3b 0.4566 (1,402/173) | gate3c 0.9556 (1,435/180) | gate3d 0.9000 (1,427/180) | gate4 0.8889 (1,429/180) | gate5 0.9771 (1,406/175).
- gate2 passes the >=90% val-acc target; gate3c/d/4/5 are strong (0.89-0.98).
- After tuning: gate3a 0.9432 (`runs/gate3a_v3/report.json`, **SOLVED**); gate3b 0.4104 (`runs/gate3b_v{1,2,3}/report.json`, **data-limited**).
- Unified `gateN` 0.9323 (5,743 train / 709 val rows, 12 classes) — `vcm8/training/runs/gateN_v1/report.json`; **supersedes gate3a-d at inference** (ALARM subset 0.9538, +0.5434 vs gate3b_v3). Standalone gate3b specialist v5 0.4509 (`vcm8/training/runs/gate3b_v5/report.json`) still weak.
- Full table and Known issues: vcm8/training/TRAINING_RESULTS.md.

## Re-tuning gate3a/gate3b (DONE - see TRAINING_RESULTS.md)

Three variants ran for each (v1 dropout 0.5 + val_loss monitor; v2 GRU32 + lr 3e-4; v3 dropout 0.5 + GRU32 + label_smoothing 0.1); launches in `RUNS.md` 2026-10-02T16:48:15.
- gate3a: **SOLVED** - `runs/gate3a_v3/report.json` val_accuracy 0.9432; promote `runs/gate3a_v3/best_model.keras`.
- gate3b: v1/v2/v3 all 0.4104 (`runs/gate3b_v{1,2,3}/report.json`); root cause (undertrained restore + confusable unseen-speaker audio, data clean) in TRAINING_RESULTS.md "gate3b deep diagnosis". Mitigations both NEGATIVE: threshold route NOT VIABLE (0.55 -> 0.6667 acc at 3.5% acceptance, single-class collapse; `reports/gate3b_threshold_sweep.json`; `config/routing_thresholds.json` `viable`=false) and TTS-retrain `gate3b_v4` 0.3642 < v3 0.4104 (`runs/gate3b_v4/report.json`). Remaining option: more real ALARM training data, or accept known-weak.
- Unified `gateN` (stage 8) supersedes the four numeric specialists: one 414,732-param model, val_acc 0.9323, ALARM subset 0.9538 (`vcm8/training/runs/gateN_v1/report.json`). gate3b specialist CosyVoice3 Round-2 retrain `gate3b_v5` 0.4509 (`vcm8/training/runs/gate3b_v5/report.json`) — still weak, no longer needed at inference.
- Registry statuses: gateN added as `trained_val_acc_0.9323_recommended_promotion` (`vcm8/config/model_registry.json`) — agrees with report.

## Round-2 weak-class retrains (DONE - see TRAINING_RESULTS.md)

Targeted TTS-augmented retrains (`vcm8/training/data_aug_round2/`; synthetic rows train-only, validation unaugmented); narrative `vcm8/training/reports/weak_class_v2_results.md`.
- `gate2_v2` 0.9635 -> 0.9712 (TIME recall 0.7778 -> 0.8519). Promoted checkpoint `vcm8/training/runs/gate2_v2/best_model.keras`; registry `trained_val_acc_0.9712_v2_promoted`.
- `gate3d_v2` 0.9000 -> 0.9167 ("20 percent" recall 0.9000 -> 0.9833; "60 percent" 0.8667 -> 0.9000). Promoted checkpoint `vcm8/training/runs/gate3d_v2/best_model.keras`; registry `trained_val_acc_0.9167_v2_promoted`.
- `gate4_v2` 0.8889 -> 0.8833 (neutral, -1 sample; Green recall 0.7333 -> 0.7667). NOT promoted; keep v1 `vcm8/training/runs/gate4/best_model.keras`.
- Standalone gate3b remains unsolved by augmentation; the ALARM route is handled by `gateN` at inference (ALARM subset 0.9538) - see stage 8.

**Integration note (live tool):** `vcm8/live_test/live_session.py` should point gate2 and gate3d at the v2 checkpoints going forward - `vcm8/training/runs/gate2_v2/best_model.keras` and `vcm8/training/runs/gate3d_v2/best_model.keras`; gate4 keeps `vcm8/training/runs/gate4/best_model.keras`. Confirm the live tool's actual checkpoint paths before the next live run.

## TFLite export (stage 6a) - DONE

- Artifacts `vcm8/training/tflite/`: gate2, gate3c, gate3d, gate4, gate5 as float32 + float16.
- float32 1,684,032 (gate2) / 1,675,776 bytes, parity 1.000 all.
- float16 856,500 (gate2) / 852,372 bytes, parity 1.000 (gate4 0.995).
- int8 BLOCKED - TF 2.21 converter segfault (repro rc=139; `vcm8/training/reports/export_int8_segfault.log`). Phase A: TF 2.21.0 is the latest stable (no upgrade path). Phase B: unidirectional `gate2_uni` (0.9059, `vcm8/training/runs/gate2_uni/report.json`) STILL segfaults -> crash is GRU-general, not bidirectional-specific (`vcm8/training/reports/int8_resolver_report.md`). Recommendations: replace GRU with TCN/1D-Conv (Conv1D quantizes stably) - retrain + re-export, val acc may dip; float16 remains the shipping fallback (parity 0.995-1.000).


## gateN Filipino-augmentation variants (2026-10-03) — NOT promoted

- `gateN_v3` and `gateN_v3_lr1e4` were run with supplemental synthetic data (2,400 `numerals` rows; total train 8,143), initialised from `gateN_v1` (`init_checkpoint` `runs/gateN_v1/best_model.keras`). Val_accuracy: v3 `0.932299017906189` (0.9323 — **tie**, no synthetic-val gain), lr1e4 `0.9153737425804138` (0.9154 — **below** v1). **`gateN_v1` (0.9323) remains the promoted unified checkpoint.** Evidence: `vcm8/training/runs/gateN_v3/report.json`, `vcm8/training/runs/gateN_v3_lr1e4/report.json`.
- **Recommendation:** do not promote either variant on synthetic-val numbers. The supplemental data's intended benefit is real-voice accent robustness, which the synthetic MEX2 val split cannot measure — evaluate `gateN_v1` vs `gateN_v3` on real sessions (`vcm8/live_test/score_voice.py`) before any promotion; the lr1e4 fine-tune is below baseline and is not a promotion candidate.
- **CONFLICT FLAG:** `vcm8/training/reports/gateN_v3_fil_report.md` states gateN_v3 = 0.9027 (regression), which does not match the on-disk `gateN_v3/report.json` (0.9323). Full flag in `vcm8/training/TRAINING_RESULTS.md`.
- **Inventory gap:** `gateN_scratch` 0.9224 (`runs/gateN_scratch/report.json`), `gateN_v3_lr5e4` 0.8984 (`runs/gateN_v3_lr5e4/report.json`), `gate2_v3` 0.9773 (`runs/gate2_v3/report.json`; Filipino synthetic, 42,496 train rows) are untracked in the stage board — flagged for the registry owner.

## Related documents
- Results table: `vcm8/training/TRAINING_RESULTS.md`.
- Per-model metrics + confusion matrices: `vcm8/training/MODEL_PERFORMANCE.md`.
- Model/dataset contract: `MODEL_DATASET_SPECIFICATIONS.md` (project root).
- Run log: `vcm8/training/RUNS.md`.

- Final deliverable: **PDF mini-paper (short paper)** over the full VCM journey — consumes the tables in `vcm8/training/TRAINING_RESULTS.md` and `vcm8/training/MODEL_PERFORMANCE.md` (see stage 10).
- 148-frame window study: `vcm8/training/TRAINING_RESULTS.md` section "148-frame window experiments"; evidence `vcm8/training/runs/{gateN_v2_148,gate2_v2_148}/report.json` + `vcm8/training/reports/gate2_148_report.md`.

## Rules in force
- Test split (s91-s100) and HF test/holdout parquet stay sealed.
- One model per GPU; gate2 gets GPU1 exclusively.
- Never claim a stage done without its artifact + exit code.
- Keep status.json updated by the process that changes state.

## If something breaks
- prep crash: read reports/prep.log tail; fix code directly (small edits, no agent round-trip).
- smoke fail: read reports/smoke.log; do NOT launch the wave.
- GPU busy: launch_wave.sh skips and reports; rerun the wave after.
