# B2 Training Results

Updated: 2026-10-03 — **148-frame window experiments documented** (`gateN_v2_148` `0.9435825347900391` = +1.13 pp vs `gateN_v1` — **HELPS**; `gate2_v2_148` `0.9568106532096863` = −1.44 pp vs `gate2_v2` — **HURTS overall**, though it fixes `LIST_REMINDERS`), **epoch-curve summaries added for all 9 promoted models**, and the **final deliverable is a PDF mini-paper** (short-paper format over the whole VCM journey; all `.md` tables here feed it — see `vcm8/training/NEXT_STEPS.md` stage 10).
No promoted checkpoint changed: `vcm8/config/model_registry.json` still lists the same 9 model entries and contains **no** `_148`, `gateN_v3*` or `gateN_scratch` entry.

Updated: 2026-10-02 — **Round-2 weak-class retrains done**: `gate2_v2` 0.9635→0.9712 and `gate3d_v2` 0.9000→0.9167 **promoted**; `gate4_v2` 0.8833 **neutral** (v1 kept). Promoted checkpoints `vcm8/training/runs/gate2_v2/best_model.keras` and `vcm8/training/runs/gate3d_v2/best_model.keras`; registry `gate2` = `trained_val_acc_0.9712_v2_promoted`, `gate3d` = `trained_val_acc_0.9167_v2_promoted` (`vcm8/config/model_registry.json`), gate4 status unchanged `trained_val_acc_0.8889`. Previous: unified `gateN_v1` TRAINED to 0.9323 (ALARM subset 0.9538, +0.5434 vs `gate3b_v3` 0.4104); before that Gate 1 rebuilt + TRAINED to 0.9400 on 3,738/50 rows.
Canonical results table for the 9 trained VCM models (8 gate models + the unified `gateN`). Rows show the promoted checkpoint per model (targeted-TTS v2 where noted).
Data revision: MEX2 train/val commit `5b23a950`; preprocessing **v1**
(log-mel 60x74, mixed 12k/16k resampled to 16 kHz).
Source of every number: the per-run `report.json` and `history.csv` files cited in each row.

## Results table

| Model | Status | val_accuracy | val_loss | train rows | val rows | worst per-class recall | param_count | checkpoint |
|-------|--------|--------------|----------|-----------|----------|------------------------|-------------|------------|
| gate2 (19 intents) | **adopted** — v2 promoted (registry `trained_val_acc_0.9712_v2_promoted`); v1 baseline 0.9635 kept for provenance | 0.9712 | 0.1136 | 14,281 | 1,806 | 0.7931 (class 12 = LIST_REMINDERS) | 415,635 | `vcm8/training/runs/gate2_v2/best_model.keras` |
| gate3a (timer value) | **adopted** — SOLVED (variant v3 promoted; registry `trained_val_acc_0.9432_v3_promoted`) | 0.9432 | 0.4238 | 1,389 | 176 | 0.8621 (class 1 = "30 seconds") | 210,243 | `vcm8/training/runs/gate3a_v3/best_model.keras` |
| gate3b (alarm time) | **adopted** — standalone specialist data-limited (v1/v2/v3 = 0.4104, v4 0.3642, v5 0.4509; registry `trained_val_acc_0.4104_data_limited`) — **superseded by gateN at inference** | 0.4104 | 1.0869 | 1,402 | 173 | 0.0351 (class 0 = "6 AM") | 210,243 | `vcm8/training/runs/gate3b_v3/best_model.keras` |
| gate3c (temp value) | trained | 0.9556 | 0.1394 | 1,435 | 180 | 0.9000 (class 1 = "22 degrees") | 413,571 | `vcm8/training/runs/gate3c/best_model.keras` |
| gate3d (brightness value) | **adopted** — v2 promoted (registry `trained_val_acc_0.9167_v2_promoted`); v1 baseline 0.9000 kept for provenance | 0.9167 | 0.3811 | 1,442 | 180 | 0.8667 (class 2 = "100 percent") | 413,571 | `vcm8/training/runs/gate3d_v2/best_model.keras` |
| gate4 (color) | trained — v1 kept (v2 neutral 0.8833, NOT promoted; registry unchanged `trained_val_acc_0.8889`) | 0.8889 | 0.5037 | 1,429 | 180 | 0.7333 (class 2 = "Green") | 413,571 | `vcm8/training/runs/gate4/best_model.keras` |
| gate5 (reminder) | trained | 0.9771 | 0.0739 | 1,406 | 175 | 0.9655 (class 0 = "Drink water") | 413,571 | `vcm8/training/runs/gate5/best_model.keras` |
| gate1 (wake word, 3-class) | trained | 0.9400 | 0.1581 | 3,738 | 50 | 0.9286 (class 2 = "Negative") | 413,571 | `vcm8/training/runs/gate1_v1/best_model.keras` |
| gateN (unified numeric, 12-class) | trained — **recommended promotion** (registry `trained_val_acc_0.9323_recommended_promotion`); replaces gate3a–d at inference | 0.9323 | 0.1954 | 5,743 | 709 | 0.8333 (class 7 = "22 degrees") | 414,732 | `vcm8/training/runs/gateN_v1/best_model.keras` |

Numbers verbatim from `report.json` (`val_accuracy`, `val_loss`, `data_row_counts`, `per_class`, `param_count`, `checkpoint_path`). Worst per-class recall = minimum `recall` across `per_class` in the same report.

**gate1 row caveat** — `vcm8/training/runs/gate1_v1/report.json`: `data_rows` train 3,738 / val **50** (small validation: ~18 nova / 18 piattos / 14 negative per class — `split_counts.validation`), `class_counts_train` [810, 801, **2,127**] (negative-class dominance), `per_class` Nova (0) P 0.8947 / R 0.9444 / F1 0.9189, Piattos (1) P 1.0000 / R 0.9444 / F1 0.9714, Negative (2) P 0.9286 / R 0.9286 / F1 0.9286 (worst recall 0.9286), `param_count` 413,571, `confusion_matrix` [[17,0,1],[1,17,0],[1,0,13]]. Meets the >=90% target on the rebuilt split, but the small val set + negative dominance mean **live-session false-wake checks are the required next verification**.

## Epoch-curve summaries — all 9 promoted models (added 2026-10-03)

Derived from each promoted run's `history.csv` (`epoch` and `val_accuracy` columns). For **every** promoted run the maximum per-epoch `val_accuracy` equals that run's `report.json` `val_accuracy` exactly (the two known report-vs-history mismatches, `gate3b_v1` and `gate3b_v4`, are non-promoted variants — flagged in `vcm8/training/MODEL_PERFORMANCE.md` Notes). All runs use `epochs_max` 40 (`report.json`).

| Promoted model | history.csv | epochs run | best epoch (index) | best val_accuracy (raw) | last-epoch val_accuracy |
|---|---|---|---|---|---|
| gate1_v1 | `vcm8/training/runs/gate1_v1/history.csv` | 23 | 12 | `0.9399999976158142` | `0.9200000166893005` |
| gate2_v2 | `vcm8/training/runs/gate2_v2/history.csv` | 23 | 14 | `0.9712070822715759` | `0.9640088677406311` |
| gate3a_v3 | `vcm8/training/runs/gate3a_v3/history.csv` | 40 | 33 | `0.9431818127632141` | `0.9431818127632141` |
| gate3b_v3 | `vcm8/training/runs/gate3b_v3/history.csv` | 10 | 1 | `0.41040462255477905` | `0.3410404622554779` |
| gate3c | `vcm8/training/runs/gate3c/history.csv` | 33 | 24 | `0.9555555582046509` | `0.9444444179534912` |
| gate3d_v2 | `vcm8/training/runs/gate3d_v2/history.csv` | 40 | 31 | `0.9166666865348816` | `0.9166666865348816` |
| gate4 | `vcm8/training/runs/gate4/history.csv` | 31 | 22 | `0.8888888955116272` | `0.8888888955116272` |
| gate5 | `vcm8/training/runs/gate5/history.csv` | 28 | 19 | `0.977142870426178` | `0.977142870426178` |
| gateN_v1 | `vcm8/training/runs/gateN_v1/history.csv` | 25 | 16 | `0.932299017906189` | `0.932299017906189` |

Reading of the curves (all numbers from the `history.csv` files above):
- **Ran to the cap (no early stop):** `gate3a_v3` and `gate3d_v2` each ran all 40 configured epochs with best epoch = last epoch — the curve is still improving/flat at the cap.
- **Early-stopped before the cap:** `gate1_v1` (23), `gate2_v2` (23), `gateN_v1` (25), `gate5` (28), `gate4` (31), `gate3c` (33).
- **`gate3b_v3` peaked at epoch 1** (best `0.41040462255477905`), then sat flat at `0.3410404622554779` for epochs 2–9 — the numerical signature of the documented data-limited collapse (`TRAINING_RESULTS.md` "gate3b deep diagnosis") and the reason `gateN` supersedes it at inference.
- **Restored-best re-evaluation pattern:** the `report.json` `val_loss` for `gateN_v1` (`0.19537730515003204`) is lower than any per-epoch `history.csv` `val_loss` (min `0.20073209702968597`, epoch 8); `gate1_v1` shows the same pattern (`report` `0.15811285376548767` vs epoch-12 history `0.15811167657375336`, last-digit difference). Recorded verbatim, flagged not resolved (`vcm8/training/MODEL_PERFORMANCE.md` Notes).
- **LR schedule (plateau) observed:** `0.001` → `0.0005` → `0.00025`; e.g. `gateN_v1` switches at epochs 13 and 21 (`vcm8/training/runs/gateN_v1/history.csv` `learning_rate`).

## Round-2 weak-class retrains — targeted TTS augmentation (VERIFIED 2026-10-02)

Full report: `vcm8/training/reports/weak_class_v2_results.md`; augmentation source `vcm8/training/data_aug_round2/`. Three models retrained; synthetic rows were concatenated into train only, validation is the original unaugmented split. **2 of 3 improved and are promoted; 1 is neutral.**

| Run | Baseline | v2 | Δ (val rows) | Target-class recall | Verdict | Checkpoint |
|-----|----------|----|--------------|---------------------|---------|------------|
| `gate3d_v2` | 0.9000 | 0.9167 | +1.67pp (+3) | "20 percent" 0.9000→0.9833; "60 percent" 0.8667→0.9000 | **PROMOTED** | `vcm8/training/runs/gate3d_v2/best_model.keras` |
| `gate2_v2` | 0.9635 | 0.9712 | +0.78pp (+14) | TIME 0.7778→0.8519 | **PROMOTED** | `vcm8/training/runs/gate2_v2/best_model.keras` |
| `gate4_v2` | 0.8889 | 0.8833 | -0.56pp (-1) | Green 0.7333→0.7667 | NEUTRAL (not promoted; v1 kept) | `vcm8/training/runs/gate4/best_model.keras` (v1) |

- **gate2_v2 promoted** — `vcm8/training/runs/gate2_v2/report.json` val_accuracy `0.9712070822715759` (0.9712; 1,754/1,806), val_loss `0.113602414727211`, params 415,635, train/val rows 14,281 / 1,806; worst per-class recall 0.7931 (class 12 = LIST_REMINDERS). Registry `trained_val_acc_0.9712_v2_promoted` agrees.
- **gate3d_v2 promoted** — `vcm8/training/runs/gate3d_v2/report.json` val_accuracy `0.9166666865348816` (0.9167; 165/180), val_loss `0.38111233711242676`, params 413,571, train/val rows 1,442 / 180. Registry `trained_val_acc_0.9167_v2_promoted` agrees.
- **gate4_v2 neutral (NOT promoted)** — `vcm8/training/runs/gate4_v2/report.json` val_accuracy `0.8833333253860474` (0.8833; 159/180), val_loss `0.41009873151779175`, params 413,571, train/val rows 1,449 / 180. Green recall improved (0.7333→0.7667) but overall accuracy fell by one sample (0.8889→0.8833), so v1 `runs/gate4/best_model.keras` stays the accepted baseline. Registry `gate4` status remains `trained_val_acc_0.8889`.
- **gate3b route:** Round-2 augmentation does not fix the standalone gate3b ALARM specialist; the ALARM route is handled at inference by the unified `gateN` model (ALARM subset 0.9538) — see the gateN section above.

### gate2_uni variant (int8 experiment — NOT one of the 8 canonical gate models)

`vcm8/training/runs/gate2_uni/report.json` (`run_tag` `_uni`, `gru_units` 64, `dropout` 0.3, `param_count` **217,427**) is a documented **unidirectional-GRU** variant of gate2, retrained to test whether the int8 crash is bidirectional-specific (gate2 bidirectional `param_count` 415,635, `vcm8/training/runs/gate2/report.json`).

| Run | val_accuracy | val_loss | train/val rows | worst per-class recall | checkpoint |
|-----|--------------|----------|----------------|------------------------|------------|
| gate2_uni (unidirectional) | 0.9059 | 0.3630 | 14,256 / 1,806 | 0.63 (class 2 = TIME) | `vcm8/training/runs/gate2_uni/best_model.keras` |

- Verbatim: `val_accuracy` 0.9058693051338196, `val_loss` 0.3630006015300751 — so uni is **~5.8 points lower** than bidirectional gate2 0.9635 (`vcm8/training/runs/gate2/report.json`).
- Worst per-class recall = class 2 = TIME 0.63 (`per_class["2"].recall` 0.6296296296296297); next worst class 3 = 0.7167 (`per_class["3"].recall`).
- Same data revision/hashes: `preprocessing_v1_hash` df881e28…, `feature_stats_hash` 612cf588…; `data_row_counts` 14,256 / 1,806.

## Unified numerical model (gateN) — 12 numeric classes (VERIFIED 2026-10-02)

Status: **VERIFIED** — `vcm8/training/runs/gateN_v1/report.json` + `history.csv`. Registry status `trained_val_acc_0.9323_recommended_promotion` (`vcm8/config/model_registry.json`); `vcm8/status.json` `training_results.models.gateN` val_acc 0.9323. Data revision MEX2 commit `5b23a950`; preprocessing v1 (`preprocessing_v1_hash` `df881e28…`, `feature_stats_hash` `612cf588…`). One model replaces the four numerical specialists gate3a/b/c/d at inference.

**Headline metrics** (verbatim `vcm8/training/runs/gateN_v1/report.json`):
- `num_classes` 12; `val_accuracy` `0.932299017906189` (0.9323) = **661 / 709** val rows; `val_loss` `0.19537730515003204`; `param_count` **414,732**; seed 42, batch_size 64, epochs_max 40, Adam lr 0.001, early_stop_patience 8, dropout 0.3, gru_units 64, `run_tag` `_v1`, `gpu_visible` "3".
- `data_row_counts`: original_train 5,653 + tts_aug 90 = **total_train 5,743**; val **709**.
- Checkpoint `vcm8/training/runs/gateN_v1/best_model.keras`.

**12-class label list** (`vcm8/config/model_registry.json` gateN `labels`): 0 "10 seconds", 1 "30 seconds", 2 "1 minute", 3 "6 AM", 4 "8 AM", 5 "9 PM", 6 "18 degrees", 7 "22 degrees", 8 "26 degrees", 9 "20 percent", 10 "60 percent", 11 "100 percent".

**Per-class P / R / F1** (verbatim `report.json` `per_class`):

| # | label | precision | recall | F1 | support |
|---|-------|-----------|--------|----|---------|
| 0 | 10 seconds | 0.8823529411764706 | 1.0 | 0.9375 | 60 |
| 1 | 30 seconds | 0.9615384615384616 | 0.8620689655172413 | 0.9090909090909091 | 58 |
| 2 | 1 minute | 0.9830508474576272 | 1.0 | 0.9914529914529915 | 58 |
| 3 | 6 AM | 0.9649122807017544 | 0.9649122807017544 | 0.9649122807017544 | 57 |
| 4 | 8 AM | 0.9166666666666666 | 0.9322033898305084 | 0.9243697478991597 | 59 |
| 5 | 9 PM | 1.0 | 0.9649122807017544 | 0.9821428571428571 | 57 |
| 6 | 18 degrees | 0.8823529411764706 | 1.0 | 0.9375 | 60 |
| 7 | 22 degrees | 1.0 | 0.8333333333333334 | 0.9090909090909091 | 60 |
| 8 | 26 degrees | 0.9354838709677419 | 0.9666666666666667 | 0.9508196721311475 | 60 |
| 9 | 20 percent | 0.8181818181818182 | 0.9 | 0.8571428571428571 | 60 |
| 10 | 60 percent | 0.9310344827586207 | 0.9 | 0.9152542372881356 | 60 |
| 11 | 100 percent | 0.9629629629629629 | 0.8666666666666667 | 0.9122807017543859 | 60 |

Lowest per-class recall = **0.8333** (class 7 "22 degrees"); every class recall >= 0.83.

**Per-intent subset accuracy** (verbatim `report.json` `specialist_subsets`) vs the specialist baselines (`baseline_comparison`):

| Subset | labels | gateN subset accuracy | correct/rows | specialist baseline | delta |
|--------|--------|-----------------------|--------------|---------------------|-------|
| gate3a (TIMER) | 10 s / 30 s / 1 min | 0.9545454545454546 | 168/176 | gate3a_v3 0.9431818127632141 | +0.0114 |
| gate3b (ALARM) | 6 AM / 8 AM / 9 PM | **0.953757225433526** | 165/173 | gate3b_v3 0.41040462255477905 | **+0.5434** |
| gate3c (TEMPERATURE) | 18 / 22 / 26 degrees | 0.9333333333333333 | 168/180 | gate3c 0.9555555582046509 | -0.0222 |
| gate3d (BRIGHTNESS) | 20 / 60 / 100 percent | 0.8888888888888888 | 160/180 | gate3d 0.8999999761581421 | -0.0111 |

**ALARM breakthrough:** the single unified model lifts the ALARM subset from `gate3b_v3` 0.4104 to **0.9538** (+0.5434 absolute); the gate3b "6 AM" per-class recall that collapsed to 0.0351 in `vcm8/training/runs/gate3b_v3/report.json` is **0.9649** in gateN (`per_class["3"]`).

**Parameter reduction:** gateN = **414,732** params replaces gate3a + gate3b + gate3c + gate3d. Against the four original specialists (each `param_count` 413,571 — `vcm8/training/runs/gate3c/report.json`, `vcm8/training/runs/gate3d/report.json`) that is 4 × 413,571 = **1,654,284** params → 414,732 / 1,654,284 = **0.2507 ≈ 75% reduction** (task: "single model replacing 4 models totaling ~1.66M params — 75% reduction").

**Routing contract:** gateN replaces gate3a–d when **Gate 2 predicts TIMER / ALARM / TEMPERATURE / BRIGHTNESS**. `vcm8/config/model_registry.json` gate2 `routing` maps those intents to gate3a/b/c/d; the registry gateN `description` = "Unified numerical model (supersedes gate3a-d at inference)". COLOR → gate4 and CREATE_REMINDER → gate5 remain unchanged.

**Epoch curve** (`vcm8/training/runs/gateN_v1/history.csv`): 25 epochs (last index 24); best val_accuracy `0.932299017906189` first at epoch **16** (max `0.932299017906189` also at epochs 17, 22 and 24 — amended 2026-10-03 from `history.csv`, which the earlier text quoted as epoch 22/24 only); train accuracy reaches 1.0 at epoch 7; LR reduced 0.001 → 0.0005 at epoch 13 → 0.00025 at epoch 21. **Flag:** report `val_loss` `0.19537730515003204` is lower than any per-epoch `history.csv` `val_loss` (min `0.20073209702968597` at epoch 8) — this is the restored-best-model re-evaluation; recorded verbatim, consistent with reconciliation item 2 in `vcm8/training/MODEL_PERFORMANCE.md`.


## gateN Filipino-augmentation variants — `gateN_v3` / `gateN_v3_lr1e4` (2026-10-03)

Status: **both NOT promoted** — `gateN_v1` (0.9323) remains the promoted unified checkpoint. The supplemental data produced **no synthetic-val improvement**.

> **CONFLICT FLAG — reviewer must reconcile (not silently resolved).** `vcm8/training/reports/gateN_v3_fil_report.md` states `gateN_v3` val_accuracy = `0.9026798009872437` (a −2.96 pp regression vs v1). The on-disk `vcm8/training/runs/gateN_v3/report.json` instead records `"val_accuracy": 0.932299017906189` (**0.9323**, a tie with `gateN_v1`), `init_checkpoint` = `vcm8/training/runs/gateN_v1/best_model.keras`, and `data_row_counts` `{original_train 5653, tts_aug 90, numerals 2400, total_train 8143, val 709}`. The value `0.9026798009872437` occurs in `vcm8/training/runs/gateN_v1/history.csv` (epoch 5, an intermediate value) and **not** in `gateN_v3/report.json`; the substitute report's "4,932 Filipino rows / trained from scratch" also disagrees with the on-disk `numerals 2400 / init_checkpoint = gateN_v1` metadata. **Neither** the earlier "96.05% / +2.82" claim **nor** the "0.9027" value is supported by the current `gateN_v3/report.json`. All numbers below are transcribed **verbatim from the on-disk reports**.

**Headline metrics** (verbatim `report.json`; `num_classes` 12, `param_count` 414732, `preprocessing_v1_hash` `df881e28…`, `feature_stats_hash` `612cf588…`, Adam, seed 42, val 709 rows):

| Run | val_accuracy (raw) | ≈ | val_loss (raw) | lr | init_checkpoint | train rows | checkpoint |
|-----|--------------------|---|----------------|----|-----------------|-----------|------------|
| `gateN_v3` | `0.932299017906189` | 0.9323 | `0.25373348593711853` | 0.001 | `runs/gateN_v1/best_model.keras` | 8,143 | `vcm8/training/runs/gateN_v3/best_model.keras` |
| `gateN_v3_lr1e4` | `0.9153737425804138` | 0.9154 | `0.26667216420173645` | 0.0001 | `runs/gateN_v1/best_model.keras` | 8,143 | `vcm8/training/runs/gateN_v3_lr1e4/best_model.keras` |

`data_row_counts` (both runs): `original_train` 5,653 + `tts_aug` 90 + `numerals` 2,400 = **total_train 8,143**; val **709**.

**Per-class recall comparison** (verbatim `per_class[*].recall`; v1 from `runs/gateN_v1/report.json`):

| # | label | v1 recall | v3 recall | v3_lr1e4 recall |
|---|-------|-----------|-----------|----------------|
| 0 | 10 seconds | 1 | 0.8666666666666667 | 1 |
| 1 | 30 seconds | 0.8620689655172413 | 0.896551724137931 | 0.8620689655172413 |
| 2 | 1 minute | 1 | 0.9655172413793104 | 0.9310344827586207 |
| 3 | 6 AM | 0.9649122807017544 | 0.9649122807017544 | 0.9473684210526315 |
| 4 | 8 AM | 0.9322033898305084 | 0.9661016949152542 | 0.864406779661017 |
| 5 | 9 PM | 0.9649122807017544 | 0.9473684210526315 | 0.9473684210526315 |
| 6 | 18 degrees | 1 | 0.9333333333333333 | 0.9666666666666667 |
| 7 | 22 degrees | 0.8333333333333334 | 0.8666666666666667 | 0.7 |
| 8 | 26 degrees | 0.9666666666666667 | 0.9666666666666667 | 1 |
| 9 | 20 percent | 0.9 | 0.95 | 0.9333333333333333 |
| 10 | 60 percent | 0.9 | 1 | 0.9333333333333333 |
| 11 | 100 percent | 0.8666666666666667 | 0.8666666666666667 | 0.9 |

Lowest v3 recall = 0.8667 (classes 0 "10 seconds" and 11 "100 percent"); lowest v3_lr1e4 recall = 0.7 (class 7 "22 degrees"). Tradeoff vs v1: TIMER decreased (v1 10s/30s/1m = 1.0/0.8621/1.0 → v3 0.8667/0.8966/0.9655), while ALARM was mixed (8 AM 0.9322→0.9661, 9 PM 0.9649→0.9474); TEMPERATURE class 7 worsened (0.8333→0.8667→0.7).

**Per-intent subset accuracy** (verbatim `specialist_subsets` vs v1):

| Subset | labels | val_accuracy | correct/rows | v1 subset |
|--------|--------|--------------|--------------|-----------|
| gate3a (TIMER) | 10 seconds / 30 seconds / 1 minute | 0.9090909090909091 | 160/176 | 0.9545454545454546 |
| gate3b (ALARM) | 6 AM / 8 AM / 9 PM | 0.9595375722543352 | 166/173 | 0.953757225433526 |
| gate3c (TEMPERATURE) | 18 degrees / 22 degrees / 26 degrees | 0.9222222222222223 | 166/180 | 0.9333333333333333 |
| gate3d (BRIGHTNESS) | 20 percent / 60 percent / 100 percent | 0.9388888888888889 | 169/180 | 0.8888888888888888 |

(lr1e4: TIMER 0.9318181818181818, ALARM 0.9190751445086706, TEMPERATURE 0.8888888888888888, BRIGHTNESS 0.9222222222222223.)
(The document's claim "8 AM 0.86, 9 PM 0.91" is contradicted by `gateN_v3/report.json`: 8 AM recall is 0.9661, 9 PM is 0.9474.)

**`gateN_v3` full confusion matrix** (verbatim `report.json` `confusion_matrix`; rows = true, cols = predicted):

| true \ pred | 10 seconds | 30 seconds | 1 minute | 6 AM | 8 AM | 9 PM | 18 degrees | 22 degrees | 26 degrees | 20 percent | 60 percent | 100 percent | Σ true |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **10 seconds** | 52 | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 2 | 2 | 0 | 60 |
| **30 seconds** | 2 | 52 | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **1 minute** | 0 | 0 | 56 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **6 AM** | 0 | 0 | 0 | 55 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 57 |
| **8 AM** | 0 | 0 | 0 | 2 | 57 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 |
| **9 PM** | 0 | 0 | 2 | 1 | 0 | 54 | 0 | 0 | 0 | 0 | 0 | 0 | 57 |
| **18 degrees** | 0 | 0 | 0 | 2 | 0 | 0 | 56 | 0 | 2 | 0 | 0 | 0 | 60 |
| **22 degrees** | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 52 | 4 | 0 | 0 | 0 | 60 |
| **26 degrees** | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 58 | 0 | 0 | 0 | 60 |
| **20 percent** | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 57 | 2 | 0 | 60 |
| **60 percent** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 60 |
| **100 percent** | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 52 | 60 |
| **Σ pred** | 59 | 54 | 60 | 60 | 65 | 54 | 62 | 52 | 64 | 63 | 64 | 52 | - |

Source: `vcm8/training/runs/gateN_v3/report.json` `confusion_matrix`.

**`gateN_v3_lr1e4` full confusion matrix** (verbatim `report.json` `confusion_matrix`; rows = true, cols = predicted):

| true \ pred | 10 seconds | 30 seconds | 1 minute | 6 AM | 8 AM | 9 PM | 18 degrees | 22 degrees | 26 degrees | 20 percent | 60 percent | 100 percent | Σ true |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **10 seconds** | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 |
| **30 seconds** | 8 | 50 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **1 minute** | 0 | 2 | 54 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **6 AM** | 1 | 0 | 0 | 54 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 57 |
| **8 AM** | 0 | 0 | 0 | 6 | 51 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 59 |
| **9 PM** | 0 | 0 | 3 | 0 | 0 | 54 | 0 | 0 | 0 | 0 | 0 | 0 | 57 |
| **18 degrees** | 0 | 0 | 0 | 0 | 0 | 0 | 58 | 0 | 2 | 0 | 0 | 0 | 60 |
| **22 degrees** | 0 | 0 | 0 | 0 | 0 | 0 | 10 | 42 | 8 | 0 | 0 | 0 | 60 |
| **26 degrees** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 60 |
| **20 percent** | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 | 0 | 0 | 60 |
| **60 percent** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 56 | 0 | 60 |
| **100 percent** | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 54 | 60 |
| **Σ pred** | 77 | 52 | 57 | 60 | 55 | 54 | 70 | 42 | 70 | 62 | 56 | 54 | - |

Source: `vcm8/training/runs/gateN_v3_lr1e4/report.json` `confusion_matrix`.

**Epoch curves** (`history.csv`): `gateN_v3` 30 epochs, best val_accuracy 0.932299017906189 at epoch 17 (last epoch 0.9252468347549438); `gateN_v3_lr1e4` 19 epochs, best val_accuracy 0.9153737425804138 at epoch 10 (last epoch 0.9111424684524536).

**Verdict:** Filipino/supplemental data did **not** improve gateN on the current synthetic MEX2 validation split; `gateN_v1` remains promoted. The supplemental variants' expected value is real-voice accent robustness, which cannot be measured on the synthetic val split — evaluate on real sessions (`vcm8/live_test/score_voice.py`) before any promotion decision.

## 148-frame window experiments — `gateN_v2_148` / `gate2_v2_148` (VERIFIED 2026-10-03)

Two runs retrained on a **148-frame / 5.92 s** window instead of the frozen 74-frame / 2.96 s window, using the parallel feature store `vcm8/training/features_148.bin` (`feature_shape_148.json`, `row_indices_148.csv`, `feature_stats_148.npz`, `preprocessing_v1_148.json`, script `vcm8/training/train_148.py`). Both `report.json` files exist; every number below is verbatim from them or from `vcm8/training/reports/gate2_148_report.md`.

| Run | Task | input_shape | val_accuracy (raw) | ≈ | val_loss (raw) | params | train rows / val rows | epoch cap / epochs run | checkpoint |
|---|---|---|---|---|---|---|---|---|---|
| `gateN_v2_148` | unified 12-class numerical | `[1, 148, 60, 1]` | `0.9435825347900391` | 0.9436 | `0.2145748883485794` | 414732 | 5,653 / 709 | 40 / 25 (`epochs_trained` 25; best epoch 16) | `vcm8/training/runs/gateN_v2_148/best_model.keras` |
| `gate2_v2_148` | 19-intent command classifier | `[148, 60, 1]` | `0.9568106532096863` | 0.9568 | `0.18247570097446442` | 415635 | 14,256 / 1,806 | 40 / 21 (`history.csv` rows 0–20; best epoch 12) | `vcm8/training/runs/gate2_v2_148/best_model.keras` |

**Verdict — 148 frames HELPED `gateN`:** `0.9435825347900391` vs `gateN_v1` `0.932299017906189` = **+0.0112835168838501 (+1.13 pp)** with the same parameter count (414,732). The gain is specialist-subset-led (verbatim `report.json` `specialist_subsets`, v1 values from the same file's `gateN_v1_baseline`): ALARM `0.976878612716763` (169/173) vs v1 `0.953757225433526` (**+0.023121387283237**), BRIGHTNESS `0.9166666666666666` (165/180) vs v1 `0.8888888888888889` (**+0.0277777777777777**), TEMPERATURE `0.9388888888888889` (169/180) vs v1 `0.9333333333333333` (+0.0055555555555556), TIMER `0.9431818181818182` (166/176) vs v1 `0.9545454545454546` (**−0.0113636363636364**). Cost: `val_loss` `0.2145748883485794` vs v1 `0.195377305150032` — accuracy up, calibration down. Lowest per-class recall `0.8333333333333334` (classes 7 "22 degrees" and 11 "100 percent") vs v1's single worst class 7 `0.8333333333333334`; worst per-class precision `0.7945205479452054` (class 0 "10 seconds").

**Verdict — 148 frames HURT `gate2` overall:** `0.9568106532096863` vs `gate2_v2` `0.9712070822715759` = **−0.0143964290618896 (−1.44 pp)** (1,728/1,806 vs 1,754/1,806 correct per `vcm8/training/reports/gate2_148_report.md`); `val_loss` `0.18247570097446442` vs `0.113602414727211`. It is **not uniformly worse**: `LIST_REMINDERS` recall rises `0.7931` → `0.9310344827586207` (46/58 → 54/58, **+0.1379**, the long-phrase class that 74 frames truncate by centre crop), while `PAUSE` precision drops `0.9273` → `0.7681159420289855` and the lowest per-class recall becomes `0.8148148148148148` (class 2 `TIME`). The 148 report's own recommendation: keep 74-frame `gate2_v2` for 3.0 s streaming buffers, and treat `gate2_v2_148` as the reference for 6 s long-buffer deployment only.

**Epoch curves:** `gateN_v2_148` 25 epochs, best `0.9435825347900391` at epoch 16, last epoch `0.9351198673248291` (`vcm8/training/runs/gateN_v2_148/history.csv`); `gate2_v2_148` 21 epochs, best `0.9568106532096863` at epoch 12, last epoch `0.9368770718574524` (`vcm8/training/runs/gate2_v2_148/history.csv`).

**Lineage caution (do not pool with the 74-frame tables):** the 148 feature store uses different hashes — `preprocessing_v1_148.json` `012639eef0c1cc6e55e6b656767c9d3300dca226b74dda1a83913762035677be` and `feature_stats_148.npz` `846bd3c2beb21980186028356d3ce62f0b784bcd322d8458ae2930fd38f74862` — vs the v1 74-frame `df881e28…` / `612cf588…`. Same MEX2 split (train 14,256 / val 1,806) and speakers s1–s90.

**Registry/status gap — FLAGGED, not silently resolved:** neither `gateN_v2_148` nor `gate2_v2_148` appears in `vcm8/config/model_registry.json` (9 entries, all `input_shape` `(1, 74, 60, 1)`) nor in `vcm8/status.json` `training_results.models`. They are unpromoted research variants: `gateN_v2_148` (0.9436) would beat the promoted `gateN_v1` (0.9323) on accuracy but loses on `val_loss` and changes the input shape; `gate2_v2_148` (0.9568) is below the promoted `gate2_v2` (0.9712) and below 74-frame `gate2_v3` `0.9772979021072388` (`vcm8/training/runs/gate2_v3/report.json`). Cross-model comparison with `gateN_v2_148` is only valid within `gateN` (5,653 train rows), not against `gate2_v2_148` (14,256 rows). No standalone `.md` report exists for `gateN_v2_148`; evidence is `vcm8/training/runs/gateN_v2_148/report.json` + `history.csv`.

## Data and preprocessing (all runs)

- Train 14,256 rows / validation 1,806 rows for **gate2** — `vcm8/training/runs/gate2/report.json` `data_row_counts`; scope confirmed by `vcm8/status.json` (`manifests_verified_scope`).
- Conditional models (gate3a–d, gate4, gate5) train on ~1,400-row subsets: gate3a 1,389 / 176, gate3b 1,402 / 173, gate3c 1,435 / 180, gate3d 1,427 / 180, gate4 1,429 / 180, gate5 1,406 / 175 — each model's `report.json` `data_row_counts`.
- Unified `gateN` trains on the union of the four numeric subsets: `data_row_counts` original_train 5,653 + tts_aug 90 = total_train 5,743, val 709 — `vcm8/training/runs/gateN_v1/report.json` (the TTS source is not recorded in that report).
- `preprocessing_v1_hash` = `df881e2845d34bcbc04f35a3810cded93153ef08b25e4fdc7c46cc2359e5b838` and `feature_stats_hash` = `612cf588cd8b1b6b81d1df2fee046892d7b3a8cb0e4c7875d562110119a8a707`, identical across all `report.json` files (including `gateN_v1`).
- Common training config (all reports): seed 42, batch_size 64, epochs_max 40, Adam, learning_rate 0.001, early_stop_patience 8, early_stop_monitor val_accuracy.
- MEX2 fetch: 16,062 train/val files, speakers s1–s90 only, commit `5b23a950` — `vcm8/training/NEXT_STEPS.md` stage 1; `data/mex2/FETCH_MANIFEST.json`.

## Known issues

1. **gate3a is SOLVED; gate3b is data-limited.** The original runs sat near chance (`runs/gate3a/report.json` 0.4659, `runs/gate3b/report.json` 0.4566). After tuning (see "Tuning results" below):
   - gate3a_v3 → 0.9432 (`vcm8/training/runs/gate3a_v3/report.json`); recommend promoting it as gate3a's primary checkpoint.
   - gate3b specialist stayed weak: v1/v2/v3 all 0.4104 (`vcm8/training/runs/gate3b_v{1,2,3}/report.json`); root cause in "gate3b deep diagnosis" below. Threshold route **NOT VIABLE**, TTS retrain `gate3b_v4` regressed to 0.3642 (`vcm8/training/runs/gate3b_v4/report.json`), and the CosyVoice3 Round-2 retrain `gate3b_v5` edged up to 0.4509 but class 0 "6 AM" recall is still 0.0 (`vcm8/training/runs/gate3b_v5/report.json`) — see "gate3b mitigation attempts" below. **The unified `gateN` model solves this** (ALARM subset 0.9538).
   - `vcm8/config/model_registry.json` now records the ADOPTED statuses `trained_val_acc_0.9432_v3_promoted` (gate3a) and `trained_val_acc_0.4104_data_limited` (gate3b) — see "Registry status suggestions" below.
2. **Strong models (0.89–0.98):** gate2 0.9635, gate3c 0.9556, gate3d 0.9000, gate4 0.8889, gate5 0.9771 — see table above; each `report.json`.
3. **gate2 worst class is class 2 = TIME**, f1 0.84 (precision 0.9130, recall 0.7778) — `vcm8/training/runs/gate2/report.json` `per_class["2"]`. Class 2 label from `vcm8/config/model_registry.json` gate2 `labels` (index 2 = "TIME"). All other gate2 classes have f1 >= 0.8667.
4. **Worst per-class recall summary:** gate4 "Green" 0.7333 and gate2 "TIME" 0.7778 are the weakest among the otherwise strong models; gate3b "6 AM" is 0.0000 — sources as in the table.
5. **Unified `gateN` supersedes gate3a–d (recommended).** One 12-class model (414,732 params) scores 0.9323 over the union of the four numeric subsets, with the ALARM subset at 0.9538 — see "Unified numerical model (gateN)" below and `vcm8/training/runs/gateN_v1/report.json`.

## Status reconciliation

- `vcm8/config/model_registry.json` statuses — gate2 `trained_val_acc_0.9635`, gate3c `0.9556`, gate3d `0.9000`, gate4 `0.8889`, gate5 `0.9771` still **agree** with the reports above. **gate3a/gate3b conflict RESOLVED (adopted):** the registry now holds gate3a `status` = `trained_val_acc_0.9432_v3_promoted` (matching `vcm8/training/runs/gate3a_v3/report.json` = 0.9432) and gate3b `status` = `trained_val_acc_0.4104_data_limited` (matching `vcm8/training/runs/gate3b_v{1,2,3}/report.json` = 0.4104).
- **gateN agrees (recommended promotion):** `vcm8/config/model_registry.json` gateN `status` = `trained_val_acc_0.9323_recommended_promotion` and `vcm8/status.json` `training_results.models.gateN.val_acc` = 0.9323 both match `vcm8/training/runs/gateN_v1/report.json` val_accuracy 0.9323 — no conflict.
- `vcm8/status.json` `implementation_status` = `foundation_implemented`, `training_allowed` = true; it does not itself carry per-model accuracy, so no conflict with reports.
- **Gate1 conflict to flag:** `vcm8/config/model_registry.json` gate1 `status` is now `trained_val_acc_0.9400_v1` (matches `vcm8/training/runs/gate1_v1/report.json` val_accuracy 0.9400) and `vcm8/status.json` `training_results.models.gate1` was added (val_acc 0.94), BUT `vcm8/status.json` `owner_overrides.gate1_still_blocked` still reads `true`. These two entries in `status.json` disagree; this doc does not silently pick one — the raw owner-approval scope line was not updated when gate1 was trained. Flagged for the registry/status owning process.
- **Gate4 status.json value to flag (minor):** `vcm8/status.json` `training_results.models.gate4.val_acc` = 0.8833 records the non-promoted v2 experiment (its `note` states v1 remains the baseline), while `vcm8/config/model_registry.json` gate4 = `trained_val_acc_0.8889` and this doc's adopted value is 0.8889 (v1 `runs/gate4/report.json`). Not silently resolved — status.json should either carry the adopted 0.8889 or label 0.8833 as the v2 experiment. Flagged for the registry/status owning process.

## Provenance

- Reports: `vcm8/training/runs/{gate1_v1,gate2,gate3a,gate3b,gate3b_v5,gate3c,gate3d,gate4,gate5,gateN_v1}/report.json`.
- Histories: same directories, `history.csv`.
- Run launches: `vcm8/training/RUNS.md`.
- Stage board: `vcm8/training/NEXT_STEPS.md`.
- Per-model metrics + confusion matrices: `vcm8/training/MODEL_PERFORMANCE.md`.
- Model/dataset contract: `MODEL_DATASET_SPECIFICATIONS.md` (project root).

## Tuning plan — gate3a and gate3b

Updated: 2026-10-02 (documentation only — no code or config changed by this section).
Data revision: MEX2 commit `5b23a950`; preprocessing **v1** (`preprocessing_v1_hash` `df881e2845d34bcbc04f35a3810cded93153ef08b25e4fdc7c46cc2359e5b838`).
Every number below is verbatim from the cited file.

### 1. Evidence summary

- **Validation stalls at chance while train saturates (overfitting).**
  - gate3a — `vcm8/training/runs/gate3a/history.csv`: train `accuracy` hits 1.0 at epoch 7; `val_accuracy` is 0.3295 for epochs 2–8; best `val_accuracy` 0.4659 is at epoch 0 (pre-overfit); `val_loss` RISES from 1.0785 (epoch 0) to 2.4569 (epoch 6).
  - gate3b — `vcm8/training/runs/gate3b/history.csv`: train `accuracy` hits 1.0 at epoch 4; best `val_accuracy` 0.4566 at epoch 2; `val_loss` rises from 1.0896 (epoch 0) to 1.9939 (epoch 9) / 1.9811 (epoch 10).
  - Both `report.json` record `early_stop_monitor: "val_accuracy"`, so the selected checkpoint is chosen on a metric that plateaued, while `val_loss` (which was worsening) is ignored.
- **Sample-rate mix ruled out.** `/tmp/check_sr_leaf.py` (rerunnable; opens each WAV with `wave.getframerate()`) shows `ALARM_6_00AM`, `ALARM_8_00AM`, `ALARM_9_00PM` and `TIMER_10s`, `TIMER_30s`, `TIMER_1m` are ALL uniformly **16 kHz**. A rate mismatch across sibling classes is therefore not the cause. Script samples 100 files per label with `random.seed(3)`.
- **Class counts are near-balanced; imbalance is not the cause.** No run's `report.json` contains a `validation_rows_by_class` field (only `per_class` and `data_row_counts`), so counts are taken from `data_row_counts` and the row sums of `confusion_matrix`:
  - gate3a `data_row_counts` train 1,389 / val 176; confusion-matrix row sums 60/58/58 = 176 (val support 60, 58, 58); `train_class_weights` 0.9909 / 0.9762 / 1.0329.
  - gate3b `data_row_counts` train 1,402 / val 173; row sums 57/59/57 = 173 (val support 57, 59, 57); `train_class_weights` 0.9986 / 0.9986 / 1.0029.
- **Confusable sibling phrases (pair-confusion).** Labels from `vcm8/config/model_registry.json` (gate3a `["10 seconds","30 seconds","1 minute"]`, gate3b `["6 AM","8 AM","9 PM"]`). Matrices verbatim from each `report.json` `confusion_matrix` (rows = true, cols = predicted):

  gate3a (`vcm8/training/runs/gate3a/report.json`):

  | true \ pred | 10 s | 30 s | 1 min |
  |-------------|------|------|-------|
  | 10 seconds  | 18 | 28 | 14 |
  | 30 seconds  | 12 | 38 | 8 |
  | 1 minute    | 4  | 28 | 26 |

  Dominant merge is **10 s <-> 30 s** (28 + 12 off-diagonal), with **1 min -> 30 s** (28).

  gate3b (`vcm8/training/runs/gate3b/report.json`):

  | true \ pred | 6 AM | 8 AM | 9 PM |
  |-------------|------|------|------|
  | 6 AM        | 0 | 55 | 2 |
  | 8 AM        | 0 | 59 | 0 |
  | 9 PM        | 0 | 37 | 20 |

  All errors collapse to **8 AM**: **6 AM <-> 8 AM** merged (55) and **9 PM -> 8 AM** (37). `per_class["0"]` for gate3b is precision 0.0 / recall 0.0 / f1 0.0.

### 2. Proposed levers in priority order

| # | Lever | Exact change site (train_model.py) | Rationale |
|---|-------|------------------------------------|-----------|
| d | Early-stop / checkpoint on **val_loss** | `train_model.py:102` `EarlyStopping(monitor='val_accuracy', ...)` -> `monitor='val_loss'`; `train_model.py:103` `ModelCheckpoint(..., monitor='val_accuracy')` -> `monitor='val_loss'`; report field `early_stop_monitor` at `train_model.py:136` | Cheapest fix, no capacity change. `val_accuracy` was flat at 0.3295 while `val_loss` ROSE, so the current monitor/checkpoint is blind to the failure mode (evidence §1). |
| a | Stronger **dropout 0.3 -> 0.5** and/or **label smoothing 0.1** | `train_model.py:32` `layers.Dropout(0.3)` -> `Dropout(0.5)`; `train_model.py:97` loss `'sparse_categorical_crossentropy'` -> add `label_smoothing=0.1` | Direct countermeasure to train accuracy 1.0 (overfit) on ~1,400 rows. |
| b | **Smaller GRU 64 -> 32** and/or drop bidirectional | `train_model.py:31` `layers.Bidirectional(layers.GRU(64))` -> `GRU(32)` (or plain `layers.GRU(32)`) | 413,571 params (`report.json` `param_count`) on ~1,400 rows is oversized; cut recurrent capacity. |
| c | **Lower LR 1e-3 -> 3e-4** + **ReduceLROnPlateau** | `train_model.py:96` `Adam(1e-3)` -> `Adam(3e-4)`; add `ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3)` to the callback list at `train_model.py:102-104` (no plateau callback exists today); update report field `learning_rate` at `train_model.py:135` | Slowly learn the hard sibling boundary and reduce LR when val stalls. |
| e | **Time-shift / pitch augmentation, training-only** | No augmentation code exists in `train_model.py` today; would be added in `main()` around `train_model.py:88-92`, applied to `X_train` only (leave `X_val` untouched to keep split hygiene) | Speaker-independent generalization with more varied views; targets unseen-speaker failure. |
| f | **Pair-confusion analysis** | Diagnostic from `report.json` `confusion_matrix` (see §1 tables) | Confirms WHICH siblings merge (10 s<->30 s; 6 AM<->8 AM) so levers are aimed, not blind; not itself a fix. |

### 3. Next-experiment table

| Variant | Exact train_model.py / registry change | Expected runtime |
|---------|----------------------------------------|------------------|
| A — D0.5 + val_loss monitor | `train_model.py:32` Dropout 0.3 -> 0.5; `train_model.py:102` EarlyStopping monitor -> `val_loss`; `train_model.py:103` ModelCheckpoint monitor -> `val_loss` | ~2-4 min |
| B — GRU32 + LR3e-4 | `train_model.py:31` GRU(64) -> GRU(32); `train_model.py:96` Adam(1e-3) -> Adam(3e-4); add `ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3)` to callbacks at `train_model.py:102-104` | ~2-4 min |
| C — D0.5 + GRU32 + smooth0.1 | `train_model.py:32` Dropout 0.5; `train_model.py:31` GRU(32); `train_model.py:97` loss `label_smoothing=0.1`; plus variant-A `val_loss` monitor | ~2-4 min |

Runtime basis: `vcm8/training/RUNS.md` launch timestamps 2026-10-02T15:57:48 and 2026-10-02T16:08:06; gate3a/gate3b run 9-11 epochs at batch_size 64 on one A100 (`report.json` `gpu_visible: "3"`) and completed within the 16:08 -> ~16:18 window (task-stated ~2-4 min per variant).

### Notes and gaps

- `vcm8/config/model_registry.json` gate3a/gate3b statuses were updated (ADOPTED) to `trained_val_acc_0.9432_v3_promoted` / `trained_val_acc_0.4104_data_limited` (see "Registry status suggestions"); this documentation-only section still makes NO code/config change itself.
- Gap: `report.json` has no `validation_rows_by_class`; adding it would report exact per-class validation support instead of the confusion-matrix row-sum proxy used above.

## Tuning results — gate3a and gate3b (executed 2026-10-02)

Status: **VERIFIED** — each variant has its own `report.json` + `history.csv`. Three variants (v1/v2/v3) per model, launches in `vcm8/training/RUNS.md` (2026-10-02T16:48:15+08:00). Numbers verbatim from each `report.json`.

| Variant | Config (from `report.json`) | early_stop_monitor | val_accuracy | val_loss | param_count | checkpoint |
|---------|------------------------------|--------------------|--------------|----------|-------------|------------|
| gate3a_v1 | dropout 0.5, gru_units 64, lr 1e-3, label_smoothing 0.0 | val_loss | 0.3523 | 1.1155 | 413,571 | `vcm8/training/runs/gate3a_v1/best_model.keras` |
| gate3a_v2 | dropout 0.3, gru_units 32, lr 3e-4, label_smoothing 0.0 | val_accuracy | 0.3636 | 1.0958 | 210,243 | `vcm8/training/runs/gate3a_v2/best_model.keras` |
| gate3a_v3 | dropout 0.5, gru_units 32, lr 1e-3, label_smoothing 0.1 | val_accuracy | **0.9432** | 0.4238 | 210,243 | `vcm8/training/runs/gate3a_v3/best_model.keras` |
| gate3b_v1 | dropout 0.5, gru_units 64, lr 1e-3, label_smoothing 0.0 | val_loss | 0.4104 | 1.0297 | 413,571 | `vcm8/training/runs/gate3b_v1/best_model.keras` |
| gate3b_v2 | dropout 0.3, gru_units 32, lr 3e-4, label_smoothing 0.0 | val_accuracy | 0.4104 | 1.0826 | 210,243 | `vcm8/training/runs/gate3b_v2/best_model.keras` |
| gate3b_v3 | dropout 0.5, gru_units 32, lr 1e-3, label_smoothing 0.1 | val_accuracy | 0.4104 | 1.0869 | 210,243 | `vcm8/training/runs/gate3b_v3/best_model.keras` |
| gate3b_v5 | dropout 0.5, gru_units 32, lr 1e-3, label_smoothing 0.1, +75 CosyVoice3 Round-2 TTS rows | val_accuracy | 0.4509 | 1.1714 | 210,243 | `vcm8/training/runs/gate3b_v5/best_model.keras` |

- **gate3a is SOLVED by v3** — `vcm8/training/runs/gate3a_v3/report.json` `val_accuracy` 0.9431818127632141 (0.9432), `val_loss` 0.4238, per-class f1 0.9206 / 0.9091 / 1.0000. The dropout-0.5 + GRU-32 + label-smoothing-0.1 recipe lifted gate3a from 0.4659 (original `runs/gate3a/report.json`) to 0.9432. **Recommendation: promote `vcm8/training/runs/gate3a_v3/best_model.keras` as gate3a's primary checkpoint.**
- **gate3b specialist stayed weak** — v1/v2/v3 all `val_accuracy` 0.41040462255477905 (`vcm8/training/runs/gate3b_v{1,2,3}/report.json`); the TTS retrain `gate3b_v4` regressed to 0.3642; the CosyVoice3 Round-2 retrain `gate3b_v5` edged up to **0.4509** (`vcm8/training/runs/gate3b_v5/report.json`) but class 0 "6 AM" recall is still **0.0**. **The unified `gateN` model solves this instead** (ALARM subset 0.9538; see "Unified numerical model (gateN)").
- gate3a_v3 `history.csv` shows the fix mechanism: `val_loss` falls steadily (1.1252 epoch 0 → 0.9556 epoch 11) instead of rising, so label smoothing + smaller GRU stopped the epoch-0 collapse (`vcm8/training/runs/gate3a_v3/history.csv`).

## gate3b deep diagnosis (root cause)

Status: **PARTIALLY VERIFIED** — (a)/(b) are backed by in-repo artifacts; (c)/(d) are diagnostic-script results whose stdout is not persisted to a report file (script paths cited; numbers as reported).

(a) **In-sample check — the restored checkpoint underfits its own training rows.** `vcm8/training/check_gate3b_train.py` loads `vcm8/training/runs/gate3b_v3/best_model.keras` and predicts on the first 600 ALARM training rows (`gate2 == 14`, `slot != -1`, `y = slot - 3`). Reported result: **0.13 accuracy, predicting almost always class 1 (8 AM)** — far below the v3 training accuracy (`history.csv` reaches 1.0). So the checkpoint restored by early stopping is not the overfit-but-competent model; it is underskilled. (Script stdout is not saved to a report; the 0.13 figure is the script's reported output.)

(b) **val_loss bottoms within the first epochs, then rises monotonically.** From each `history.csv` `val_loss` column:
   - `gate3b_v1` (`runs/gate3b_v1/history.csv`, monitor val_loss): min at epoch **2** (`1.0297`), then 1.1815, 1.3982, … rising.
   - `gate3b_v2` (`runs/gate3b_v2/history.csv`, monitor val_accuracy): min at epoch **0** (`1.0817`), then 1.0835, 1.0826, 1.1126, … rising.
   - `gate3b_v3` (`runs/gate3b_v3/history.csv`, monitor val_accuracy): min at epoch **0** (`1.0771`), then 1.0869, 1.2277, … rising.
   Early-stopping on `val_loss` (v1) therefore restores an epoch-0/2 model while train accuracy was still low (v3 epoch 0 train accuracy 0.4158 ≈ the quoted 0.42). The `val_loss` minimum does not coincide with the best `val_accuracy`, so neither monitor yields a competent gate3b model.

(c) **Class separability is not the problem (centroid cosines).** `vcm8/training/check_alarm_feat.py` computes the per-class mean of per-file L2-normalized flattened features straight from `vcm8/training/features.bin` (first 400 rows/class). Reported: ALARM pairs `centroid_cosine` ≈ **0.963–0.968**; TIMER pairs `centroid_cosine` ≈ **0.967–0.976** (script comment: "TIMER (healthy-ish after v3: 0.94)"). TIMER pairs are as similar as (or more similar than) ALARM pairs, yet TIMER trained to 0.9432 (`runs/gate3a_v3/report.json`). ALARM feature-space collapse is therefore not the sole cause. (Script now at `vcm8/training/check_alarm_feat.py`; stdout not persisted — numbers as reported. The supporting sample-rate check is `vcm8/training/check_sr_leaf.py`, which samples 100 WAVs/label and reports uniform 16 kHz.)

(d) **Data integrity is clean (no label/pipeline bug).** Reported for the ALARM leaves: 1,575 unique WAV hashes with **zero cross-label duplicates**, transcripts correct, durations similar (means 1.8–2.0 s). (This diagnostic's output is not persisted in a report file; cited as reported. `vcm8/training/row_indices.csv` lists the ALARM rows and `runs/gate3b_*/report.json` `data_row_counts` give 1,402 train / 173 val.)

**Conclusion:** gate3b failure is **confusable audio across unseen validation speakers + extreme early-overfit** — not a label or preprocessing bug. Options (as recommended):
1. Early-stop on `val_accuracy` with restore-best — v1 already did this and still returned 0.4104 (`runs/gate3b_v1/report.json`), so it does not fix it alone.
2. More training data for the ALARM leaves, or speaker-balanced sampling.
3. Cross-validate which validation speakers fail.
4. ~~OR accept gate3b as known-weak for this data revision and route ALARM confidently with a confidence threshold.~~ **RETRACTED — the threshold route was attempted and is NOT VIABLE** (see "gate3b mitigation attempts" below: at 0.55 accuracy 0.6667 on only 3.5% acceptance with single-class collapse; at <=0.50 accuracy ~0.41). Remaining option: more real ALARM training data, or accept gate3b as known-weak.

## gate3b mitigation attempts — threshold sweep + TTS-augmented retrain (VERIFIED 2026-10-02)

Status: **VERIFIED — both mitigation routes are NEGATIVE.**

### Phase A — confidence-threshold routing: NOT VIABLE

Source: `vcm8/training/reports/gate3b_threshold_sweep.json` and `vcm8/training/reports/gate3b_threshold.md`.

True sweep table (verbatim from the sweep json):

| Threshold | Acc rate | Acc on accepted | macro-F1 (accepted) | recall 0 | recall 1 | recall 2 |
|-----------|----------|-----------------|----------------------|----------|----------|----------|
| 0.30 | 1.0000 | 0.4104 | 0.3112 | 0.0351 | 0.9661 | 0.2105 |
| 0.35 | 1.0000 | 0.4104 | 0.3112 | 0.0351 | 0.9661 | 0.2105 |
| 0.40 | 0.9769 | 0.4083 | 0.3027 | 0.0351 | 0.9661 | 0.1887 |
| 0.45 | 0.6416 | 0.4234 | 0.2825 | 0.0000 | 1.0000 | 0.1667 |
| 0.50 | 0.2023 | 0.4286 | 0.2000 | 0.0000 | 1.0000 | 0.0000 |
| 0.55 | 0.0347 | 0.6667 | 0.4000 | 0.0000 | 1.0000 | 0.0000 |
| 0.60–0.95 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

- The recommended row in `gate3b_threshold.md` is **threshold 0.55**: `acceptance_rate` 0.0347 (**3.5%**), `accuracy_on_accepted` **0.6667**, `macro_f1_on_accepted` 0.4, `recalls` {0: 0.0, 1: 1.0, 2: 0.0} — single-class collapse (only "8 AM" accepted). Raw json row is `threshold` 0.5499999999999999.
- At thresholds **<= 0.50** acceptance is high but `accuracy_on_accepted` stays **~0.41–0.43**. No threshold yields acceptable accuracy with usable acceptance → **NOT VIABLE**.
- **Conflict corrected:** `vcm8/training/reports/gate3b_resolver_report.md` Phase A misstated the operating point as accuracy-on-accepted **~`0.8614`** at acceptance **~`0.5420`** (the "86.1%/54%" numbers). The authoritative sweep data records **0.6667 / 0.0347**; the resolver report is superseded on these Phase A figures.
- **Corrected config:** `vcm8/config/routing_thresholds.json` now records gate3b `threshold` = `null`, `viable` = `false`, with the reason string and file citations (the resolver had written threshold 0.55 as viable based on the misreading).

### Phase B — TTS-augmented retrain (`gate3b_v4`): NEGATIVE

Source: `vcm8/training/runs/gate3b_v4/report.json`.

- `val_accuracy` **0.3641618490219116 → 0.3642** — **worse** than v3 0.4104 (`vcm8/training/runs/gate3b_v3/report.json`).
- `val_loss` 1.0634816884994507 → 1.0635.
- `confusion_matrix` `[[12,7,38],[16,6,37],[8,4,45]]`.
- `data_counts`: original_train 1,402, **tts_aug 60**, val 173.
- ~99.9% train accuracy = overfit to the synthetic voices. `vcm8/training/reports/gate3b_resolver_report.md` Phase B documents this honestly; **v4 is NOT promoted**.

### Remaining option

The standalone gate3b specialist remains weak: TTS augmentation v4 (0.3642) and CosyVoice3 Round-2 v5 (0.4509) did not clear it (`vcm8/training/runs/gate3b_v{4,5}/report.json`). **Superseded for inference by the unified `gateN` model** (ALARM subset 0.9538; one 414,732-param model replacing gate3a–d) — see "Unified numerical model (gateN)". More real-world ALARM recordings remain an option only if the standalone gate3b checkpoint is ever needed.

## TFLite export matrix (VERIFIED)

Artifacts: `vcm8/training/tflite/` (per-model `*.tflite` + `*.json`). Exported models: **gate2, gate3c, gate3d, gate4, gate5** (the 5 strong models). Numbers verbatim from each `tflite/<model>_<variant>.json`.

| Model | float32 bytes | float32 parity | float16 bytes | float16 parity |
|-------|---------------|----------------|---------------|----------------|
| gate2 | 1,684,032 | 1.000 | 856,500 | 1.000 |
| gate3c | 1,675,776 | 1.000 | 852,372 | 1.000 |
| gate3d | 1,675,776 | 1.000 | 852,372 | 1.000 |
| gate4 | 1,675,776 | 1.000 | 852,372 | **0.995** |
| gate5 | 1,675,776 | 1.000 | 852,372 | 1.000 |

- float32 sizes span **1.676–1.684 MB** (1,675,776–1,684,032 bytes), parity **1.000** for all five.
- float16 sizes span **0.852–0.857 MB** (852,372–856,500 bytes), parity 1.000 for all except **gate4 = 0.995** (`vcm8/training/tflite/gate4_float16.json`).
- Parity = agreement between the exported TFLite model and the Keras model over a fixed 200-row train slice (`export_one.py`: `agree / 200`; `vcm8/training/reports/export.log`: `gate2 float32: 1684032 bytes, parity 200/200`).

**int8 quantization: BLOCKED — TF 2.21 converter crashes on GRU (evidence persisted).** No `int8` `.tflite`/`.json` exists in `vcm8/training/tflite/` (`ls`). Repro command `python vcm8/training/export_one.py --model gate2 --variant int8` exits **`rc=139`** (SIGSEGV); full log at `vcm8/training/reports/export_int8_segfault.log`. The log shows the float32 SavedModel/TFLite conversion path proceeding (`flatbuffer_export.cc:4302] Estimated count of arithmetic ops: 45.146 M ops`) and then stopping, with the final line `rc=139`. This supersedes the earlier run-3 note that the rc=139 claim was not independently verifiable: the run-3 conclusion was drawn from `vcm8/training/reports/export.log`, which indeed has no `rc=139` line; the dedicated repro log above now carries the exit code. Caveat: the log records `rc=139` (exit status) but no literal `Segmentation fault` string (a segfault can lose buffered stdout); the code is evidence of SIGSEGV. Both tools attempt int8: `export_tflite.py` default `--models` `gate2,gate3c,gate3d,gate4,gate5` with a `["float32", "int8"]` variant loop; `export_one.py` accepts `--variant {float32,int8,float16}`.

**int8 resolver findings (2026-10-02)** — source: `vcm8/training/reports/int8_resolver_report.md` (**VERIFIED**: the report file is now populated (previously noted as 0 bytes) and independently records the Phase A/B conclusions below). The `gate2_uni` **training** numbers are verified from its `report.json` (see variant subsection above).
- **Phase A — newer TF: NEGATIVE (no upgrade path).** The TF release index shows **2.21.0 is the latest stable available**, so the int8 crash cannot be bypassed by upgrading TensorFlow at this time (`vcm8/training/reports/int8_resolver_report.md`).
- **Phase B — unidirectional GRU: STILL CRASHES → GRU-general.** The `gate2_uni` variant (unidirectional GRU, `vcm8/training/runs/gate2_uni/report.json` val_accuracy 0.9059) was int8-converted and **still segfaults `rc=139`** (`vcm8/training/reports/int8_resolver_report.md`). Therefore the TF 2.21 int8 crash is **GRU-general, not bidirectional-specific** — it is not fixed by making the GRU unidirectional.
  - Note: `vcm8/status.json` line "tflite_int8": `BLOCKED - TF 2.21 converter segfault on Bidirectional GRU` is now **stale** (should read GRU-general); flagged for the registry/status owner.

**Recommendations (int8, from the resolver)** — source: `vcm8/training/reports/int8_resolver_report.md`:
1. **RECOMMENDED: replace the GRU with a TCN / 1D-Conv stack** — `Conv1D` quantizes stably to int8 in TFLite. Effort: retrain + re-export (each model is a small CRNN; roughly one training wave, then re-run `export_one.py` for int8). Expected tradeoff: validation accuracy may **dip** (the uni experiment already shows a GRU-architecture change costs ~5.8 points), and every gate must be re-validated and re-exported (`float32` + `float16` + `int8`).
2. **float16 remains the shipping fallback** — already produced for gate2/gate3c/gate3d/gate4/gate5 with parity **0.995–1.000** (see matrix above); no int8 dependency.

**Export tooling** (`vcm8/training/`):
- `export_tflite.py` — batch attempt (float32 + int8).
- `export_one.py` — isolated per-model/variant; the tool that produced the shipped float32/float16 files.
- Both hide GPUs before loading checkpoints (`tf.config.set_visible_devices([], "GPU")`) and rebuild a static batch-1 CPU graph via `build_fixed_crnn(..., batch_shape=(1, 74, 60, 1))`, so fused `CudnnRNNV3` ops from GPU training are re-created as TFLite-convertible ops.

## Gate 1 (wake word) — rebuild + training provenance (2026-10-02)

- **Dataset rebuild** (`vcm8/training/data_gate1/rebuild_evidence.json`): initial 4,426 rows → 633 quarantined → 5 redundant negatives dropped → 0 overlapping positive speakers → **final 3,788 rows** (`negative` 2,141 / `nova` 828 / `piattos` 819; train 3,738 / validation 50). 0 in-split sha duplicates, 0 cross-label groups. Summary: `vcm8/training/reports/gate1_rebuild_report.md` ("Verification passed. Training can proceed.").
- **Process note** (`vcm8/training/reports/gate1_resolver_report.md`): the gate1-rebuilder agent completed the dataset rebuild but its session died on a provider context-length limit *before* training; the orchestrator completed training directly with `vcm8/training/train_gate1.py` (CRNN identical to `train_model.py`; dropout 0.5, BiGRU 64; seed 42; class weights from train only; early stopping on val_accuracy patience 10; GPU 1, log `vcm8/training/runs/gate1_v1.log`). The report at `gate1_resolver_report.md` states this provenance.
- **Result:** `vcm8/training/runs/gate1_v1/report.json` val_accuracy 0.9400 (val_loss 0.1581); checkpoint `vcm8/training/runs/gate1_v1/best_model.keras`; curves `vcm8/training/runs/gate1_v1/history.csv`.
- **Next verification:** live-mic false-wake testing via `vcm8/live_test/live_session.py` (owner microphone) — the small 50-row validation split does not exercise real background noise.

## Registry status suggestions (ADOPTED 2026-10-02)

The two suggestions below were **ADOPTED**: `vcm8/config/model_registry.json` (updated by the registry's owning process, not this doc) now records:
- gate3a `status` = `trained_val_acc_0.9432_v3_promoted` (matches `vcm8/training/runs/gate3a_v3/report.json` val_accuracy 0.9432).
- gate3b `status` = `trained_val_acc_0.4104_data_limited` (matches `vcm8/training/runs/gate3b_v{1,2,3}/report.json` val_accuracy 0.4104).

Previously (superseded): the registry held `gate3a: trained_val_acc_0.4659_needs_tuning` and `gate3b: trained_val_acc_0.4566_needs_tuning`.


