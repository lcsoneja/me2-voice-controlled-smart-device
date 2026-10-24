# VCM Model Performance — canonical metrics

> Rebuilt from **all 21** `vcm8/training/runs/*/report.json` files (paired with each run's `history.csv`) and label orders from `vcm8/config/model_registry.json`.

> Every number below is copied verbatim from the cited file; rounded 4-dp figures appear only as an annotation beside the raw value.

> Run inventory: 21 report files, one per run directory (`gate1_v1`, `gate2`, `gate2_uni`, `gate2_v2`, `gate3a`, `gate3a_v1..v3`, `gate3b`, `gate3b_v1..v5`, `gate3c`, `gate3d`, `gate3d_v2`, `gate4`, `gate4_v2`, `gate5`, `gateN_v1`).

## Data lineage

| Item | Value | Source |
|------|-------|--------|
| Dataset | MEX2 train/val, commit `5b23a950` | `vcm8/status.json` `training_results.data`; `vcm8/training/TRAINING_RESULTS.md` |
| Split scope | speakers s1–s90 (gate2: train 14,256 / val 1,806); test split never downloaded | `vcm8/status.json` `manifests_verified_scope` |
| Preprocessing | v1 — log-mel 60×74, 16 kHz, mixed 12k/16k sources resampled to 16 kHz | `vcm8/status.json` `training_results.preprocessing`; `vcm8/training/preprocessing_v1.json` |
| `preprocessing_v1_hash` | `df881e2845d34bcbc04f35a3810cded93153ef08b25e4fdc7c46cc2359e5b838` | identical across all `report.json` (e.g. `vcm8/training/runs/gate2/report.json`) |
| `feature_stats_hash` | `612cf588cd8b1b6b81d1df2fee046892d7b3a8cb0e4c7875d562110119a8a707` | identical across all `report.json` (e.g. `vcm8/training/runs/gate2/report.json`) |
| Input shape | `(1, 74, 60, 1)` (unbatched `(74, 60, 1)`) | `vcm8/config/model_registry.json` `global_config.input_shape`; `vcm8/training/feature_shape.json` = `[16062, 74, 60]` |
| Common config | seed 42, batch_size 64, epochs_max 40, Adam, lr 0.001, early_stop_patience 8 | each `report.json` (per-run overrides noted in sections) |

**Feature spec (per `vcm8/status.json` / `preprocessing_v1.json`):** log-mel **60×74**, **16 kHz** (`n_mels=60`, `target_frames=74`, `n_fft=1024`, `hop_length=640`, loaded as float16); **12k sources resampled to 16 kHz** (`scipy resample_poly` at load). Data revision: MEX2 commit **5b23a950**; preprocessing **v1** (`df881e28…`).

## Summary table — all 21 runs

| Model (run dir) | Variant / description | val_accuracy (raw) | ≈ | val_loss (raw) | params | status |
|---|---|---|---|---|---|---|
| `gate1_v1` | wake-word 3-class (Nova / Piattos / Negative) | `0.9399999976158142` | 0.9400 | `0.15811285376548767` | 413571 | promoted (wake-word v1) |
| `gate2` | 19-intent command classifier (v1 baseline) | `0.9634551405906677` | 0.9635 | `0.13865311443805695` | 415635 | superseded by gate2_v2 |
| `gate2_uni` | gate2 unidirectional-GRU (int8 experiment) | `0.9058693051338196` | 0.9059 | `0.3630006015300751` | 217427 | variant (NOT promoted) |
| `gate2_v2` | 19-intent command classifier (Round-2 TTS) | `0.9712070822715759` | 0.9712 | `0.113602414727211` | 415635 | PROMOTED (registry `trained_val_acc_0.9712_v2_promoted`) |
| `gate3a` | timer value (pre-tuning baseline) | `0.46590909361839294` | 0.4659 | `1.078570008277893` | 413571 | superseded |
| `gate3a_v1` | timer value tuning v1 | `0.35227271914482117` | 0.3523 | `1.1155471801757812` | 413571 | superseded (variant) |
| `gate3a_v2` | timer value tuning v2 | `0.3636363744735718` | 0.3636 | `1.0958129167556763` | 210243 | superseded (variant) |
| `gate3a_v3` | timer value tuning v3 | `0.9431818127632141` | 0.9432 | `0.42375290393829346` | 210243 | PROMOTED (registry `trained_val_acc_0.9432_v3_promoted`) |
| `gate3b` | alarm time (pre-tuning baseline) | `0.4566473960876465` | 0.4566 | `1.0473322868347168` | 413571 | superseded |
| `gate3b_v1` | alarm time tuning v1 | `0.41040462255477905` | 0.4104 | `1.0296995639801025` | 413571 | superseded (variant) |
| `gate3b_v2` | alarm time tuning v2 | `0.41040462255477905` | 0.4104 | `1.0825998783111572` | 210243 | superseded (variant) |
| `gate3b_v3` | alarm time tuning v3 | `0.41040462255477905` | 0.4104 | `1.0869206190109253` | 210243 | PROMOTED / data-limited (registry `trained_val_acc_0.4104_data_limited`) |
| `gate3b_v4` | alarm time TTS-augmented retrain | `0.3641618490219116` | 0.3642 | `1.0634816884994507` | — | NEGATIVE (0.3642 < v3; not promoted) |
| `gate3b_v5` | alarm time TTS Round-2 (75 synthetic rows) | `0.45086705684661865` | 0.4509 | `1.171367883682251` | 210243 | variant: 0.4509 > v3 0.4104 (not yet in registry) |
| `gate3c` | temperature value | `0.9555555582046509` | 0.9556 | `0.1394466906785965` | 413571 | PROMOTED (registry `trained_val_acc_0.9556`) |
| `gate3d` | brightness value (v1 baseline) | `0.8999999761581421` | 0.9000 | `0.43982788920402527` | 413571 | superseded by gate3d_v2 |
| `gate3d_v2` | brightness value (Round-2 TTS) | `0.9166666865348816` | 0.9167 | `0.38111233711242676` | 413571 | PROMOTED (registry `trained_val_acc_0.9167_v2_promoted`) |
| `gate4` | color (v1) | `0.8888888955116272` | 0.8889 | `0.5037104487419128` | 413571 | PROMOTED (registry `trained_val_acc_0.8889`) |
| `gate4_v2` | color (Round-2 TTS) | `0.8833333253860474` | 0.8833 | `0.41009873151779175` | 413571 | NEUTRAL (v1 kept; not promoted) |
| `gate5` | reminder content | `0.977142870426178` | 0.9771 | `0.07386958599090576` | 413571 | PROMOTED (registry `trained_val_acc_0.9771`) |
| `gateN_v1` | unified 12-class numerical model | `0.932299017906189` | 0.9323 | `0.19537730515003204` | 414732 | recommended promotion (registry `trained_val_acc_0.9323_recommended_promotion`) |

Source: `vcm8/training/runs/<run>/report.json` for every row (`val_accuracy`, `val_loss`, `param_count`). `gate3b_v4` records no `param_count` (only an architecture `params` object) — see Notes.

## Promoted models

### gate1_v1 — wake-word 3-class (Nova / Piattos / Negative)

**Status:** **promoted** (registry `gate1` = `trained_val_acc_0.9400_v1`).

**Metrics** — val_accuracy = `0.9399999976158142`, val_loss = `0.15811285376548767`, param_count = `413571`, rows = **train=3738, val=50**.

Source: `vcm8/training/runs/gate1_v1/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | Nova | 0.8947368421052632 | 0.9444444444444444 | 0.918918918918919 |
| 1 | Piattos | 1 | 0.9444444444444444 | 0.9714285714285714 |
| 2 | Negative | 0.9285714285714286 | 0.9285714285714286 | 0.9285714285714286 |

Source: `vcm8/training/runs/gate1_v1/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | Nova | Piattos | Negative | Σ true |
|---|---|---|---|---|
| **Nova** | 17 | 0 | 1 | 18 |
| **Piattos** | 1 | 17 | 0 | 18 |
| **Negative** | 1 | 0 | 13 | 14 |
| **Σ pred** | 19 | 17 | 14 | - |

Source: `vcm8/training/runs/gate1_v1/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **23** (data rows in `history.csv`).
- Best epoch by val_accuracy: **12** — train_accuracy `0.9981273412704468`, val_accuracy `0.9399999976158142`.
- Best epoch by val_loss: **12** — val_loss `0.15811167657375336`.
- Final val_loss `0.25920212268829346`; trend over last 3 epochs: **rising**.
- LR-reduction events: ep17: 0.001 → 0.0005; ep21: 0.0005 → 0.00025.

### gate2_v2 — 19-intent command classifier (Round-2 targeted TTS)

**Status:** **promoted** (registry `gate2` = `trained_val_acc_0.9712_v2_promoted`); supersedes the `gate2` v1 baseline (`0.9635`).

**Metrics** — val_accuracy = `0.9712070822715759`, val_loss = `0.113602414727211`, param_count = `415635`, rows = **train=14281, aug_train=25, original_train=14256, val=1806**. Checkpoint: `vcm8/training/runs/gate2_v2/best_model.keras`.

Source: `vcm8/training/runs/gate2_v2/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | PLAY_MUSIC | 0.9666666666666667 | 0.9666666666666667 | 0.9666666666666667 |
| 1 | WEATHER | 0.9245283018867925 | 0.9074074074074074 | 0.9158878504672897 |
| 2 | TIME | 0.92 | 0.8518518518518519 | 0.8846153846153846 |
| 3 | LIGHT_ON | 0.8484848484848485 | 0.9333333333333333 | 0.8888888888888888 |
| 4 | LIGHT_OFF | 0.9473684210526315 | 0.9642857142857143 | 0.9557522123893806 |
| 5 | PAUSE | 0.9272727272727272 | 0.9272727272727272 | 0.9272727272727272 |
| 6 | STOP | 0.9166666666666666 | 0.9322033898305084 | 0.9243697478991597 |
| 7 | NEXT | 0.9666666666666667 | 1 | 0.9830508474576272 |
| 8 | VOLUME_UP | 1 | 0.9821428571428571 | 0.990990990990991 |
| 9 | VOLUME_DOWN | 0.9672131147540983 | 1 | 0.9833333333333333 |
| 10 | CALL | 0.9655172413793104 | 0.9655172413793104 | 0.9655172413793104 |
| 11 | MESSAGE | 1 | 1 | 1 |
| 12 | LIST_REMINDERS | 1 | 0.7931034482758621 | 0.8846153846153846 |
| 13 | TIMER | 0.9513513513513514 | 1 | 0.9750692520775623 |
| 14 | ALARM | 0.9881656804733728 | 0.9653179190751445 | 0.9766081871345029 |
| 15 | TEMPERATURE | 1 | 1 | 1 |
| 16 | BRIGHTNESS | 1 | 1 | 1 |
| 17 | COLOR | 1 | 1 | 1 |
| 18 | CREATE_REMINDER | 0.9829545454545454 | 0.9885714285714285 | 0.9857549857549858 |

Source: `vcm8/training/runs/gate2_v2/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | PLAY_MUSIC | WEATHER | TIME | LIGHT_ON | LIGHT_OFF | PAUSE | STOP | NEXT | VOLUME_UP | VOLUME_DOWN | CALL | MESSAGE | LIST_REMINDERS | TIMER | ALARM | TEMPERATURE | BRIGHTNESS | COLOR | CREATE_REMIN.. | Σ true |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **PLAY_MUSIC** | 58 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 |
| **WEATHER** | 0 | 49 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 54 |
| **TIME** | 2 | 0 | 46 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 2 | 54 |
| **LIGHT_ON** | 0 | 0 | 0 | 56 | 0 | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 |
| **LIGHT_OFF** | 0 | 0 | 0 | 2 | 54 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 |
| **PAUSE** | 0 | 0 | 2 | 0 | 0 | 51 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 55 |
| **STOP** | 0 | 2 | 0 | 0 | 0 | 0 | 55 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 |
| **NEXT** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **VOLUME_UP** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 55 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 |
| **VOLUME_DOWN** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 |
| **CALL** | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 56 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **MESSAGE** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 55 |
| **LIST_REMINDERS** | 0 | 2 | 0 | 4 | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 46 | 2 | 0 | 0 | 0 | 0 | 0 | 58 |
| **TIMER** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 176 | 0 | 0 | 0 | 0 | 0 | 176 |
| **ALARM** | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 167 | 0 | 0 | 0 | 1 | 173 |
| **TEMPERATURE** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 180 | 0 | 0 | 0 | 180 |
| **BRIGHTNESS** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 180 | 0 | 0 | 180 |
| **COLOR** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 180 | 0 | 180 |
| **CREATE_REMINDER** | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 173 | 175 |
| **Σ pred** | 60 | 53 | 50 | 66 | 57 | 55 | 60 | 60 | 55 | 61 | 58 | 55 | 46 | 185 | 169 | 180 | 180 | 180 | 176 | - |

Source: `vcm8/training/runs/gate2_v2/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **23** (data rows in `history.csv`).
- Best epoch by val_accuracy: **14** — train_accuracy `1`, val_accuracy `0.9712070822715759`.
- Best epoch by val_loss: **14** — val_loss `0.1135217696428299`.
- Final val_loss `0.12632186710834503`; trend over last 3 epochs: **mixed (last3: 0.12362784 → 0.13684443 → 0.12632187)**.
- LR-reduction events: ep11: 0.001 → 0.0005; ep19: 0.0005 → 0.00025.

### gate3a_v3 — timer value tuning v3

**Status:** **promoted** (registry `gate3a` = `trained_val_acc_0.9432_v3_promoted`).

**Metrics** — val_accuracy = `0.9431818127632141`, val_loss = `0.42375290393829346`, param_count = `210243`, rows = **train=1389, val=176**. Checkpoint: `vcm8/training/runs/gate3a_v3/best_model.keras`.

Source: `vcm8/training/runs/gate3a_v3/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 10 seconds | 0.8787878787878788 | 0.9666666666666667 | 0.9206349206349206 |
| 1 | 30 seconds | 0.9615384615384616 | 0.8620689655172413 | 0.9090909090909091 |
| 2 | 1 minute | 1 | 1 | 1 |

Source: `vcm8/training/runs/gate3a_v3/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 10 seconds | 30 seconds | 1 minute | Σ true |
|---|---|---|---|---|
| **10 seconds** | 58 | 2 | 0 | 60 |
| **30 seconds** | 8 | 50 | 0 | 58 |
| **1 minute** | 0 | 0 | 58 | 58 |
| **Σ pred** | 66 | 52 | 58 | - |

Source: `vcm8/training/runs/gate3a_v3/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **40** (data rows in `history.csv`).
- Best epoch by val_accuracy: **33** — train_accuracy `1`, val_accuracy `0.9431818127632141`.
- Best epoch by val_loss: **33** — val_loss `0.4237537384033203`.
- Final val_loss `0.43703654408454895`; trend over last 3 epochs: **mixed (last3: 0.44903085 → 0.44949177 → 0.43703654)**.
- LR-reduction events: ep32: 0.001 → 0.0005; ep38: 0.0005 → 0.00025.

### gate3b_v3 — alarm time tuning v3

**Status:** **promoted / data-limited** (registry `gate3b` = `trained_val_acc_0.4104_data_limited`); **superseded by `gateN_v1` at inference**.

**Metrics** — val_accuracy = `0.41040462255477905`, val_loss = `1.0869206190109253`, param_count = `210243`, rows = **train=1402, val=173**. Checkpoint: `vcm8/training/runs/gate3b_v3/best_model.keras`.

Source: `vcm8/training/runs/gate3b_v3/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 6 AM | 1 | 0.03508771929824561 | 0.06779661016949153 |
| 1 | 8 AM | 0.3630573248407643 | 0.9661016949152542 | 0.5277777777777778 |
| 2 | 9 PM | 0.8571428571428571 | 0.21052631578947367 | 0.3380281690140845 |

Source: `vcm8/training/runs/gate3b_v3/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 6 AM | 8 AM | 9 PM | Σ true |
|---|---|---|---|---|
| **6 AM** | 2 | 55 | 0 | 57 |
| **8 AM** | 0 | 57 | 2 | 59 |
| **9 PM** | 0 | 45 | 12 | 57 |
| **Σ pred** | 2 | 157 | 14 | - |

Source: `vcm8/training/runs/gate3b_v3/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **10** (data rows in `history.csv`).
- Best epoch by val_accuracy: **1** — train_accuracy `0.7047075629234314`, val_accuracy `0.41040462255477905`.
- Best epoch by val_loss: **0** — val_loss `1.0770536661148071`.
- Final val_loss `1.5095248222351074`; trend over last 3 epochs: **falling (last3: 1.58729541 → 1.54293191 → 1.50952482)**.
- LR-reduction events: ep6: 0.001 → 0.0005.

### gate3c — temperature value

**Status:** **promoted** (registry `gate3c` = `trained_val_acc_0.9556`).

**Metrics** — val_accuracy = `0.9555555582046509`, val_loss = `0.1394466906785965`, param_count = `413571`, rows = **train=1435, val=180**. Checkpoint: `vcm8/training/runs/gate3c/best_model.keras`.

Source: `vcm8/training/runs/gate3c/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 18 degrees | 0.8823529411764706 | 1 | 0.9375 |
| 1 | 22 degrees | 1 | 0.9 | 0.9473684210526315 |
| 2 | 26 degrees | 1 | 0.9666666666666667 | 0.9830508474576272 |

Source: `vcm8/training/runs/gate3c/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 18 degrees | 22 degrees | 26 degrees | Σ true |
|---|---|---|---|---|
| **18 degrees** | 60 | 0 | 0 | 60 |
| **22 degrees** | 6 | 54 | 0 | 60 |
| **26 degrees** | 2 | 0 | 58 | 60 |
| **Σ pred** | 68 | 54 | 58 | - |

Source: `vcm8/training/runs/gate3c/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **33** (data rows in `history.csv`).
- Best epoch by val_accuracy: **24** — train_accuracy `1`, val_accuracy `0.9555555582046509`.
- Best epoch by val_loss: **28** — val_loss `0.13210730254650116`.
- Final val_loss `0.14454494416713715`; trend over last 3 epochs: **rising (last3: 0.13778363 → 0.13892065 → 0.14454494)**.
- LR-reduction events: none logged (no learning_rate column).

### gate3d_v2 — brightness value (Round-2 targeted TTS)

**Status:** **promoted** (registry `gate3d` = `trained_val_acc_0.9167_v2_promoted`); supersedes `gate3d` v1 (`0.9000`).

**Metrics** — val_accuracy = `0.9166666865348816`, val_loss = `0.38111233711242676`, param_count = `413571`, rows = **train=1442, aug_train=15, original_train=1427, val=180**. Checkpoint: `vcm8/training/runs/gate3d_v2/best_model.keras`.

Source: `vcm8/training/runs/gate3d_v2/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 20 percent | 0.8082191780821918 | 0.9833333333333333 | 0.8872180451127819 |
| 1 | 60 percent | 1 | 0.9 | 0.9473684210526315 |
| 2 | 100 percent | 0.9811320754716981 | 0.8666666666666667 | 0.9203539823008849 |

Source: `vcm8/training/runs/gate3d_v2/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 20 percent | 60 percent | 100 percent | Σ true |
|---|---|---|---|---|
| **20 percent** | 59 | 0 | 1 | 60 |
| **60 percent** | 6 | 54 | 0 | 60 |
| **100 percent** | 8 | 0 | 52 | 60 |
| **Σ pred** | 73 | 54 | 53 | - |

Source: `vcm8/training/runs/gate3d_v2/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **40** (data rows in `history.csv`).
- Best epoch by val_accuracy: **31** — train_accuracy `1`, val_accuracy `0.9166666865348816`.
- Best epoch by val_loss: **39** — val_loss `0.374038964509964`.
- Final val_loss `0.374038964509964`; trend over last 3 epochs: **falling (last3: 0.37855127 → 0.37677276 → 0.37403896)**.
- LR-reduction events: ep29: 0.001 → 0.0005; ep36: 0.0005 → 0.00025.

### gate4 — color (v1)

**Status:** **promoted** (registry `gate4` = `trained_val_acc_0.8889`); `gate4_v2` was neutral, so v1 is kept.

**Metrics** — val_accuracy = `0.8888888955116272`, val_loss = `0.5037104487419128`, param_count = `413571`, rows = **train=1429, val=180**. Checkpoint: `vcm8/training/runs/gate4/best_model.keras`.

Source: `vcm8/training/runs/gate4/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | Red | 0.9375 | 1 | 0.967741935483871 |
| 1 | Blue | 0.7777777777777778 | 0.9333333333333333 | 0.8484848484848485 |
| 2 | Green | 1 | 0.7333333333333333 | 0.8461538461538461 |

Source: `vcm8/training/runs/gate4/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | Red | Blue | Green | Σ true |
|---|---|---|---|---|
| **Red** | 60 | 0 | 0 | 60 |
| **Blue** | 4 | 56 | 0 | 60 |
| **Green** | 0 | 16 | 44 | 60 |
| **Σ pred** | 64 | 72 | 44 | - |

Source: `vcm8/training/runs/gate4/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **31** (data rows in `history.csv`).
- Best epoch by val_accuracy: **22** — train_accuracy `1`, val_accuracy `0.8888888955116272`.
- Best epoch by val_loss: **30** — val_loss `0.38110554218292236`.
- Final val_loss `0.38110554218292236`; trend over last 3 epochs: **falling (last3: 0.43501240 → 0.40424484 → 0.38110554)**.
- LR-reduction events: none logged (no learning_rate column).

### gate5 — reminder content

**Status:** **promoted** (registry `gate5` = `trained_val_acc_0.9771`).

**Metrics** — val_accuracy = `0.977142870426178`, val_loss = `0.07386958599090576`, param_count = `413571`, rows = **train=1406, val=175**. Checkpoint: `vcm8/training/runs/gate5/best_model.keras`.

Source: `vcm8/training/runs/gate5/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | Drink water | 1 | 0.9655172413793104 | 0.9824561403508771 |
| 1 | Study | 0.9666666666666667 | 1 | 0.9830508474576272 |
| 2 | Exercise | 0.9661016949152542 | 0.9661016949152542 | 0.9661016949152542 |

Source: `vcm8/training/runs/gate5/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | Drink water | Study | Exercise | Σ true |
|---|---|---|---|---|
| **Drink water** | 56 | 0 | 2 | 58 |
| **Study** | 0 | 58 | 0 | 58 |
| **Exercise** | 0 | 2 | 57 | 59 |
| **Σ pred** | 56 | 60 | 59 | - |

Source: `vcm8/training/runs/gate5/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **28** (data rows in `history.csv`).
- Best epoch by val_accuracy: **19** — train_accuracy `1`, val_accuracy `0.977142870426178`.
- Best epoch by val_loss: **27** — val_loss `0.03947500139474869`.
- Final val_loss `0.03947500139474869`; trend over last 3 epochs: **falling (last3: 0.04528762 → 0.04160068 → 0.03947500)**.
- LR-reduction events: none logged (no learning_rate column).

### gateN_v1 — unified 12-class numerical model (timer + alarm + temperature + brightness)

**Status:** **recommended promotion** (registry `gateN` = `trained_val_acc_0.9323_recommended_promotion`); supersedes gate3a–d at inference.

**Metrics** — val_accuracy = `0.932299017906189`, val_loss = `0.19537730515003204`, param_count = `414732`, rows = **total_train=5743, tts_aug=90, original_train=5653, val=709**. Checkpoint: `vcm8/training/runs/gateN_v1/best_model.keras`.

Source: `vcm8/training/runs/gateN_v1/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 | support |
|---|-------|-----------|--------|----|---------|
| 0 | 10 seconds | 0.8823529411764706 | 1 | 0.9375 | 60 |
| 1 | 30 seconds | 0.9615384615384616 | 0.8620689655172413 | 0.9090909090909091 | 58 |
| 2 | 1 minute | 0.9830508474576272 | 1 | 0.9914529914529915 | 58 |
| 3 | 6 AM | 0.9649122807017544 | 0.9649122807017544 | 0.9649122807017544 | 57 |
| 4 | 8 AM | 0.9166666666666666 | 0.9322033898305084 | 0.9243697478991597 | 59 |
| 5 | 9 PM | 1 | 0.9649122807017544 | 0.9821428571428571 | 57 |
| 6 | 18 degrees | 0.8823529411764706 | 1 | 0.9375 | 60 |
| 7 | 22 degrees | 1 | 0.8333333333333334 | 0.9090909090909091 | 60 |
| 8 | 26 degrees | 0.9354838709677419 | 0.9666666666666667 | 0.9508196721311475 | 60 |
| 9 | 20 percent | 0.8181818181818182 | 0.9 | 0.8571428571428571 | 60 |
| 10 | 60 percent | 0.9310344827586207 | 0.9 | 0.9152542372881356 | 60 |
| 11 | 100 percent | 0.9629629629629629 | 0.8666666666666667 | 0.9122807017543859 | 60 |

Source: `vcm8/training/runs/gateN_v1/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 10 seconds | 30 seconds | 1 minute | 6 AM | 8 AM | 9 PM | 18 degrees | 22 degrees | 26 degrees | 20 percent | 60 percent | 100 percent | Σ true |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **10 seconds** | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 |
| **30 seconds** | 8 | 50 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **1 minute** | 0 | 0 | 58 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **6 AM** | 0 | 0 | 0 | 55 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 57 |
| **8 AM** | 0 | 0 | 0 | 2 | 55 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 59 |
| **9 PM** | 0 | 0 | 1 | 0 | 1 | 55 | 0 | 0 | 0 | 0 | 0 | 0 | 57 |
| **18 degrees** | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 60 |
| **22 degrees** | 0 | 0 | 0 | 0 | 2 | 0 | 4 | 50 | 4 | 0 | 0 | 0 | 60 |
| **26 degrees** | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 58 | 0 | 0 | 0 | 60 |
| **20 percent** | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 54 | 4 | 0 | 60 |
| **60 percent** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 54 | 2 | 60 |
| **100 percent** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 52 | 60 |
| **Σ pred** | 68 | 52 | 59 | 57 | 60 | 55 | 68 | 50 | 62 | 66 | 58 | 54 | - |

Source: `vcm8/training/runs/gateN_v1/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **25** (data rows in `history.csv`).
- Best epoch by val_accuracy: **16** — train_accuracy `1`, val_accuracy `0.932299017906189`.
- Best epoch by val_loss: **16** — val_loss `0.19538447260856628`.
- Final val_loss `0.21253788471221924`; trend over last 3 epochs: **mixed (last3: 0.21033461 → 0.20959297 → 0.21253788)**.
- LR-reduction events: ep13: 0.001 → 0.0005; ep21: 0.0005 → 0.00025.

## Secondary — tuning variants, baselines, and negative results

Full per-class tables and confusion matrices are included for every secondary run for completeness.

### gate2 — 19-intent command classifier (v1 baseline)

**Status:** superseded by `gate2_v2`; kept for provenance.

**Metrics** — val_accuracy = `0.9634551405906677`, val_loss = `0.13865311443805695`, param_count = `415635`, rows = **train=14256, val=1806**. Checkpoint: `vcm8/training/runs/gate2/best_model.keras`.

Source: `vcm8/training/runs/gate2/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | PLAY_MUSIC | 0.967741935483871 | 1 | 0.9836065573770492 |
| 1 | WEATHER | 0.94 | 0.8703703703703703 | 0.9038461538461539 |
| 2 | TIME | 0.9130434782608695 | 0.7777777777777778 | 0.84 |
| 3 | LIGHT_ON | 0.8666666666666667 | 0.8666666666666667 | 0.8666666666666667 |
| 4 | LIGHT_OFF | 0.8666666666666667 | 0.9285714285714286 | 0.896551724137931 |
| 5 | PAUSE | 0.8153846153846154 | 0.9636363636363636 | 0.8833333333333333 |
| 6 | STOP | 0.9298245614035088 | 0.8983050847457628 | 0.9137931034482759 |
| 7 | NEXT | 0.9180327868852459 | 0.9655172413793104 | 0.9411764705882353 |
| 8 | VOLUME_UP | 0.9152542372881356 | 0.9642857142857143 | 0.9391304347826087 |
| 9 | VOLUME_DOWN | 0.9672131147540983 | 1 | 0.9833333333333333 |
| 10 | CALL | 0.9333333333333333 | 0.9655172413793104 | 0.9491525423728814 |
| 11 | MESSAGE | 0.9814814814814815 | 0.9636363636363636 | 0.9724770642201835 |
| 12 | LIST_REMINDERS | 1 | 0.9310344827586207 | 0.9642857142857143 |
| 13 | TIMER | 0.9775280898876404 | 0.9886363636363636 | 0.9830508474576272 |
| 14 | ALARM | 1 | 0.953757225433526 | 0.9763313609467456 |
| 15 | TEMPERATURE | 1 | 1 | 1 |
| 16 | BRIGHTNESS | 1 | 0.9777777777777777 | 0.9887640449438202 |
| 17 | COLOR | 1 | 1 | 1 |
| 18 | CREATE_REMINDER | 0.9775280898876404 | 0.9942857142857143 | 0.9858356940509915 |

Source: `vcm8/training/runs/gate2/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | PLAY_MUSIC | WEATHER | TIME | LIGHT_ON | LIGHT_OFF | PAUSE | STOP | NEXT | VOLUME_UP | VOLUME_DOWN | CALL | MESSAGE | LIST_REMINDERS | TIMER | ALARM | TEMPERATURE | BRIGHTNESS | COLOR | CREATE_REMIN.. | Σ true |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **PLAY_MUSIC** | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 |
| **WEATHER** | 0 | 47 | 0 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 54 |
| **TIME** | 0 | 0 | 42 | 2 | 2 | 0 | 4 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 54 |
| **LIGHT_ON** | 0 | 0 | 0 | 52 | 1 | 4 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 |
| **LIGHT_OFF** | 0 | 0 | 0 | 4 | 52 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 |
| **PAUSE** | 0 | 0 | 2 | 0 | 0 | 53 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 55 |
| **STOP** | 0 | 0 | 0 | 0 | 0 | 0 | 53 | 2 | 0 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 |
| **NEXT** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **VOLUME_UP** | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 54 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 |
| **VOLUME_DOWN** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 |
| **CALL** | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 56 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **MESSAGE** | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 53 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 55 |
| **LIST_REMINDERS** | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 54 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **TIMER** | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 174 | 0 | 0 | 0 | 0 | 0 | 176 |
| **ALARM** | 0 | 3 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 165 | 0 | 0 | 0 | 2 | 173 |
| **TEMPERATURE** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 180 | 0 | 0 | 0 | 180 |
| **BRIGHTNESS** | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 176 | 0 | 2 | 180 |
| **COLOR** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 180 | 0 | 180 |
| **CREATE_REMINDER** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 174 | 175 |
| **Σ pred** | 62 | 50 | 46 | 60 | 60 | 65 | 57 | 61 | 59 | 61 | 60 | 54 | 54 | 178 | 165 | 180 | 176 | 180 | 178 | - |

Source: `vcm8/training/runs/gate2/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **35** (data rows in `history.csv`).
- Best epoch by val_accuracy: **26** — train_accuracy `1`, val_accuracy `0.9634551405906677`.
- Best epoch by val_loss: **12** — val_loss `0.13620004057884216`.
- Final val_loss `0.1928686946630478`; trend over last 3 epochs: **mixed (last3: 0.25881216 → 0.17050485 → 0.19286869)**.
- LR-reduction events: none logged (no learning_rate column).

### gate2_uni — gate2 unidirectional-GRU (int8 experiment)

**Status:** variant; NOT promoted (val 0.9059 < v1/v2).

**Metrics** — val_accuracy = `0.9058693051338196`, val_loss = `0.3630006015300751`, param_count = `217427`, rows = **train=14256, val=1806**. Checkpoint: `vcm8/training/runs/gate2_uni/best_model.keras`.

Source: `vcm8/training/runs/gate2_uni/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | PLAY_MUSIC | 0.9523809523809523 | 1 | 0.975609756097561 |
| 1 | WEATHER | 0.875 | 0.9074074074074074 | 0.8909090909090909 |
| 2 | TIME | 0.8947368421052632 | 0.6296296296296297 | 0.7391304347826086 |
| 3 | LIGHT_ON | 0.7288135593220338 | 0.7166666666666667 | 0.7226890756302521 |
| 4 | LIGHT_OFF | 0.7719298245614035 | 0.7857142857142857 | 0.7787610619469026 |
| 5 | PAUSE | 0.6571428571428571 | 0.8363636363636363 | 0.736 |
| 6 | STOP | 0.6811594202898551 | 0.7966101694915254 | 0.734375 |
| 7 | NEXT | 0.9574468085106383 | 0.7758620689655172 | 0.8571428571428571 |
| 8 | VOLUME_UP | 0.7741935483870968 | 0.8571428571428571 | 0.8135593220338984 |
| 9 | VOLUME_DOWN | 0.7727272727272727 | 0.864406779661017 | 0.816 |
| 10 | CALL | 0.9122807017543859 | 0.896551724137931 | 0.9043478260869565 |
| 11 | MESSAGE | 0.9814814814814815 | 0.9636363636363636 | 0.9724770642201835 |
| 12 | LIST_REMINDERS | 0.9259259259259259 | 0.8620689655172413 | 0.8928571428571429 |
| 13 | TIMER | 0.9653179190751445 | 0.9488636363636364 | 0.9570200573065902 |
| 14 | ALARM | 0.9526627218934911 | 0.930635838150289 | 0.9415204678362573 |
| 15 | TEMPERATURE | 0.9887640449438202 | 0.9777777777777777 | 0.9832402234636871 |
| 16 | BRIGHTNESS | 0.9775280898876404 | 0.9666666666666667 | 0.9720670391061452 |
| 17 | COLOR | 0.9771428571428571 | 0.95 | 0.9633802816901409 |
| 18 | CREATE_REMINDER | 0.9116022099447514 | 0.9428571428571428 | 0.9269662921348315 |

Source: `vcm8/training/runs/gate2_uni/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | PLAY_MUSIC | WEATHER | TIME | LIGHT_ON | LIGHT_OFF | PAUSE | STOP | NEXT | VOLUME_UP | VOLUME_DOWN | CALL | MESSAGE | LIST_REMINDERS | TIMER | ALARM | TEMPERATURE | BRIGHTNESS | COLOR | CREATE_REMIN.. | Σ true |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **PLAY_MUSIC** | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 |
| **WEATHER** | 0 | 49 | 0 | 0 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 54 |
| **TIME** | 0 | 2 | 34 | 4 | 2 | 0 | 4 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 4 | 54 |
| **LIGHT_ON** | 0 | 0 | 0 | 43 | 5 | 5 | 0 | 0 | 0 | 5 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 |
| **LIGHT_OFF** | 0 | 0 | 0 | 4 | 44 | 2 | 4 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 |
| **PAUSE** | 0 | 0 | 2 | 0 | 0 | 46 | 0 | 0 | 0 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 55 |
| **STOP** | 0 | 2 | 0 | 0 | 2 | 4 | 47 | 0 | 0 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 59 |
| **NEXT** | 0 | 0 | 0 | 0 | 2 | 2 | 4 | 45 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 58 |
| **VOLUME_UP** | 0 | 0 | 0 | 0 | 0 | 2 | 2 | 0 | 48 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 56 |
| **VOLUME_DOWN** | 0 | 0 | 0 | 2 | 0 | 2 | 0 | 0 | 0 | 51 | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 59 |
| **CALL** | 0 | 0 | 2 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 52 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 |
| **MESSAGE** | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 53 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 55 |
| **LIST_REMINDERS** | 0 | 0 | 0 | 2 | 0 | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 50 | 0 | 0 | 2 | 0 | 0 | 0 | 58 |
| **TIMER** | 2 | 1 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 167 | 0 | 0 | 2 | 0 | 0 | 176 |
| **ALARM** | 0 | 2 | 0 | 1 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 161 | 0 | 0 | 0 | 1 | 173 |
| **TEMPERATURE** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 176 | 0 | 0 | 0 | 180 |
| **BRIGHTNESS** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 174 | 0 | 4 | 180 |
| **COLOR** | 1 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 171 | 0 | 180 |
| **CREATE_REMINDER** | 0 | 0 | 0 | 0 | 2 | 0 | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 2 | 0 | 165 | 175 |
| **Σ pred** | 63 | 56 | 38 | 59 | 57 | 70 | 69 | 47 | 62 | 66 | 57 | 54 | 54 | 173 | 169 | 178 | 178 | 175 | 181 | - |

Source: `vcm8/training/runs/gate2_uni/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **17** (data rows in `history.csv`).
- Best epoch by val_accuracy: **8** — train_accuracy `0.9877946376800537`, val_accuracy `0.9058693051338196`.
- Best epoch by val_loss: **8** — val_loss `0.3629634380340576`.
- Final val_loss `0.42649129033088684`; trend over last 3 epochs: **mixed (last3: 0.43319479 → 0.45355672 → 0.42649129)**.
- LR-reduction events: ep13: 0.001 → 0.0005.

### gate3a — timer value (pre-tuning baseline)

**Status:** superseded by `gate3a_v3`.

**Metrics** — val_accuracy = `0.46590909361839294`, val_loss = `1.078570008277893`, param_count = `413571`, rows = **train=1389, val=176**. Checkpoint: `vcm8/training/runs/gate3a/best_model.keras`.

Source: `vcm8/training/runs/gate3a/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 10 seconds | 0.5294117647058824 | 0.3 | 0.3829787234042553 |
| 1 | 30 seconds | 0.40425531914893614 | 0.6551724137931034 | 0.5 |
| 2 | 1 minute | 0.5416666666666666 | 0.4482758620689655 | 0.49056603773584906 |

Source: `vcm8/training/runs/gate3a/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 10 seconds | 30 seconds | 1 minute | Σ true |
|---|---|---|---|---|
| **10 seconds** | 18 | 28 | 14 | 60 |
| **30 seconds** | 12 | 38 | 8 | 58 |
| **1 minute** | 4 | 28 | 26 | 58 |
| **Σ pred** | 34 | 94 | 48 | - |

Source: `vcm8/training/runs/gate3a/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **9** (data rows in `history.csv`).
- Best epoch by val_accuracy: **0** — train_accuracy `0.4636428952217102`, val_accuracy `0.46590909361839294`.
- Best epoch by val_loss: **0** — val_loss `1.0785704851150513`.
- Final val_loss `2.0929512977600098`; trend over last 3 epochs: **falling (last3: 2.45692945 → 2.30402231 → 2.09295130)**.
- LR-reduction events: none logged (no learning_rate column).

### gate3a_v1 — timer value tuning v1

**Status:** superseded (tuning variant; collapsed to a single class).

**Metrics** — val_accuracy = `0.35227271914482117`, val_loss = `1.1155471801757812`, param_count = `413571`, rows = **train=1389, val=176**. Checkpoint: `vcm8/training/runs/gate3a_v1/best_model.keras`.

Source: `vcm8/training/runs/gate3a_v1/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 10 seconds | 0 | 0 | 0 |
| 1 | 30 seconds | 0.3466666666666667 | 0.896551724137931 | 0.5 |
| 2 | 1 minute | 0.38461538461538464 | 0.1724137931034483 | 0.23809523809523808 |

Source: `vcm8/training/runs/gate3a_v1/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 10 seconds | 30 seconds | 1 minute | Σ true |
|---|---|---|---|---|
| **10 seconds** | 0 | 50 | 10 | 60 |
| **30 seconds** | 0 | 52 | 6 | 58 |
| **1 minute** | 0 | 48 | 10 | 58 |
| **Σ pred** | 0 | 150 | 26 | - |

Source: `vcm8/training/runs/gate3a_v1/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **9** (data rows in `history.csv`).
- Best epoch by val_accuracy: **0** — train_accuracy `0.4391648769378662`, val_accuracy `0.35227271914482117`.
- Best epoch by val_loss: **0** — val_loss `1.1155284643173218`.
- Final val_loss `2.026578664779663`; trend over last 3 epochs: **falling (last3: 2.21341991 → 2.13519073 → 2.02657866)**.
- LR-reduction events: ep5: 0.001 → 0.0005.

### gate3a_v2 — timer value tuning v2

**Status:** superseded (tuning variant).

**Metrics** — val_accuracy = `0.3636363744735718`, val_loss = `1.0958129167556763`, param_count = `210243`, rows = **train=1389, val=176**. Checkpoint: `vcm8/training/runs/gate3a_v2/best_model.keras`.

Source: `vcm8/training/runs/gate3a_v2/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 10 seconds | 0.41025641025641024 | 0.5333333333333333 | 0.463768115942029 |
| 1 | 30 seconds | 0.18181818181818182 | 0.06896551724137931 | 0.1 |
| 2 | 1 minute | 0.3684210526315789 | 0.4827586206896552 | 0.417910447761194 |

Source: `vcm8/training/runs/gate3a_v2/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 10 seconds | 30 seconds | 1 minute | Σ true |
|---|---|---|---|---|
| **10 seconds** | 32 | 6 | 22 | 60 |
| **30 seconds** | 28 | 4 | 26 | 58 |
| **1 minute** | 18 | 12 | 28 | 58 |
| **Σ pred** | 78 | 22 | 76 | - |

Source: `vcm8/training/runs/gate3a_v2/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **9** (data rows in `history.csv`).
- Best epoch by val_accuracy: **0** — train_accuracy `0.35997119545936584`, val_accuracy `0.3636363744735718`.
- Best epoch by val_loss: **1** — val_loss `1.0955920219421387`.
- Final val_loss `1.1320083141326904`; trend over last 3 epochs: **falling (last3: 1.17440939 → 1.16103458 → 1.13200831)**.
- LR-reduction events: ep5: 0.0003 → 0.00015.

### gate3b — alarm time (pre-tuning baseline)

**Status:** superseded by `gate3b_v3` (same data-limited regime).

**Metrics** — val_accuracy = `0.4566473960876465`, val_loss = `1.0473322868347168`, param_count = `413571`, rows = **train=1402, val=173**. Checkpoint: `vcm8/training/runs/gate3b/best_model.keras`.

Source: `vcm8/training/runs/gate3b/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 6 AM | 0 | 0 | 0 |
| 1 | 8 AM | 0.39072847682119205 | 1 | 0.5619047619047619 |
| 2 | 9 PM | 0.9090909090909091 | 0.3508771929824561 | 0.5063291139240507 |

Source: `vcm8/training/runs/gate3b/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 6 AM | 8 AM | 9 PM | Σ true |
|---|---|---|---|---|
| **6 AM** | 0 | 55 | 2 | 57 |
| **8 AM** | 0 | 59 | 0 | 59 |
| **9 PM** | 0 | 37 | 20 | 57 |
| **Σ pred** | 0 | 151 | 22 | - |

Source: `vcm8/training/runs/gate3b/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **11** (data rows in `history.csv`).
- Best epoch by val_accuracy: **2** — train_accuracy `0.9693295359611511`, val_accuracy `0.4566473960876465`.
- Best epoch by val_loss: **1** — val_loss `1.034871220588684`.
- Final val_loss `1.9810986518859863`; trend over last 3 epochs: **mixed (last3: 1.97604597 → 1.99398410 → 1.98109865)**.
- LR-reduction events: none logged (no learning_rate column).

### gate3b_v1 — alarm time tuning v1

**Status:** superseded (tuning variant).

**Metrics** — val_accuracy = `0.41040462255477905`, val_loss = `1.0296995639801025`, param_count = `413571`, rows = **train=1402, val=173**. Checkpoint: `vcm8/training/runs/gate3b_v1/best_model.keras`.

Source: `vcm8/training/runs/gate3b_v1/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 6 AM | 0 | 0 | 0 |
| 1 | 8 AM | 0.3630573248407643 | 0.9661016949152542 | 0.5277777777777778 |
| 2 | 9 PM | 0.875 | 0.24561403508771928 | 0.3835616438356164 |

Source: `vcm8/training/runs/gate3b_v1/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 6 AM | 8 AM | 9 PM | Σ true |
|---|---|---|---|---|
| **6 AM** | 0 | 57 | 0 | 57 |
| **8 AM** | 0 | 57 | 2 | 59 |
| **9 PM** | 0 | 43 | 14 | 57 |
| **Σ pred** | 0 | 157 | 16 | - |

Source: `vcm8/training/runs/gate3b_v1/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **11** (data rows in `history.csv`).
- Best epoch by val_accuracy: **1** — train_accuracy `0.6647646427154541`, val_accuracy `0.5722543597221375`.
- Best epoch by val_loss: **2** — val_loss `1.0297044515609741`.
- Final val_loss `1.5876232385635376`; trend over last 3 epochs: **falling (last3: 1.70202184 → 1.67632425 → 1.58762324)**.
- LR-reduction events: ep7: 0.001 → 0.0005.

### gate3b_v2 — alarm time tuning v2

**Status:** superseded (tuning variant).

**Metrics** — val_accuracy = `0.41040462255477905`, val_loss = `1.0825998783111572`, param_count = `210243`, rows = **train=1402, val=173**. Checkpoint: `vcm8/training/runs/gate3b_v2/best_model.keras`.

Source: `vcm8/training/runs/gate3b_v2/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 6 AM | 1 | 0.07017543859649122 | 0.13114754098360656 |
| 1 | 8 AM | 0.36645962732919257 | 1 | 0.5363636363636364 |
| 2 | 9 PM | 1 | 0.14035087719298245 | 0.24615384615384617 |

Source: `vcm8/training/runs/gate3b_v2/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 6 AM | 8 AM | 9 PM | Σ true |
|---|---|---|---|---|
| **6 AM** | 4 | 53 | 0 | 57 |
| **8 AM** | 0 | 59 | 0 | 59 |
| **9 PM** | 0 | 49 | 8 | 57 |
| **Σ pred** | 4 | 161 | 8 | - |

Source: `vcm8/training/runs/gate3b_v2/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **11** (data rows in `history.csv`).
- Best epoch by val_accuracy: **2** — train_accuracy `0.71897292137146`, val_accuracy `0.41040462255477905`.
- Best epoch by val_loss: **0** — val_loss `1.081681489944458`.
- Final val_loss `1.4607155323028564`; trend over last 3 epochs: **rising (last3: 1.43334329 → 1.44458854 → 1.46071553)**.
- LR-reduction events: ep7: 0.0003 → 0.00015.

### gate3b_v4 — alarm time TTS-augmented retrain

**Status:** NEGATIVE result (0.3642); not promoted.

**Metrics** — val_accuracy = `0.3641618490219116`, val_loss = `1.0634816884994507`, param_count = `(not recorded)`, rows = **tts_aug=60, original_train=1402, val=173**.

Source: `vcm8/training/runs/gate3b_v4/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 6 AM | 0.3333333333333333 | 0.21052631578947367 | 0.25806451612903225 |
| 1 | 8 AM | 0.35294117647058826 | 0.1016949152542373 | 0.15789473684210525 |
| 2 | 9 PM | 0.375 | 0.7894736842105263 | 0.5084745762711864 |

Source: `vcm8/training/runs/gate3b_v4/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 6 AM | 8 AM | 9 PM | Σ true |
|---|---|---|---|---|
| **6 AM** | 12 | 7 | 38 | 57 |
| **8 AM** | 16 | 6 | 37 | 59 |
| **9 PM** | 8 | 4 | 45 | 57 |
| **Σ pred** | 36 | 17 | 120 | - |

Source: `vcm8/training/runs/gate3b_v4/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **9** (data rows in `history.csv`).
- Best epoch by val_accuracy: **2** — train_accuracy `0.8919288516044617`, val_accuracy `0.4566473960876465`.
- Best epoch by val_loss: **0** — val_loss `1.063482642173767`.
- Final val_loss `1.4085084199905396`; trend over last 3 epochs: **mixed (last3: 1.41332948 → 1.43520677 → 1.40850842)**.
- LR-reduction events: ep5: 0.001 → 0.0005.

### gate3b_v5 — alarm time TTS Round-2 retrain

**Status:** variant: 0.4509 beats `gate3b_v3` (0.4104) but is not yet reflected in `model_registry.json`.

**Metrics** — val_accuracy = `0.45086705684661865`, val_loss = `1.171367883682251`, param_count = `210243`, rows = **train=1477, original_train=1402, synthetic_train=75, val=173**. Checkpoint: `/mnt/jfs_hpc/home/leandro.soneja/_Exercise B2/vcm8/training/runs/gate3b_v5/best_model.keras`.

Source: `vcm8/training/runs/gate3b_v5/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 6 AM | 0 | 0 | 0 |
| 1 | 8 AM | 0.3923076923076923 | 0.864406779661017 | 0.5396825396825397 |
| 2 | 9 PM | 0.627906976744186 | 0.47368421052631576 | 0.54 |

Source: `vcm8/training/runs/gate3b_v5/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 6 AM | 8 AM | 9 PM | Σ true |
|---|---|---|---|---|
| **6 AM** | 0 | 49 | 8 | 57 |
| **8 AM** | 0 | 51 | 8 | 59 |
| **9 PM** | 0 | 30 | 27 | 57 |
| **Σ pred** | 0 | 130 | 43 | - |

Source: `vcm8/training/runs/gate3b_v5/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **11** (data rows in `history.csv`).
- Best epoch by val_accuracy: **2** — train_accuracy `0.8259986639022827`, val_accuracy `0.45086705684661865`.
- Best epoch by val_loss: **0** — val_loss `1.1034215688705444`.
- Final val_loss `1.2887439727783203`; trend over last 3 epochs: **falling (last3: 1.35391462 → 1.32204235 → 1.28874397)**.
- LR-reduction events: ep7: 0.001 → 0.0005.

### gate3d — brightness value (v1 baseline)

**Status:** superseded by `gate3d_v2`.

**Metrics** — val_accuracy = `0.8999999761581421`, val_loss = `0.43982788920402527`, param_count = `413571`, rows = **train=1427, val=180**. Checkpoint: `vcm8/training/runs/gate3d/best_model.keras`.

Source: `vcm8/training/runs/gate3d/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | 20 percent | 0.84375 | 0.9 | 0.8709677419354839 |
| 1 | 60 percent | 0.9629629629629629 | 0.8666666666666667 | 0.9122807017543859 |
| 2 | 100 percent | 0.9032258064516129 | 0.9333333333333333 | 0.9180327868852459 |

Source: `vcm8/training/runs/gate3d/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | 20 percent | 60 percent | 100 percent | Σ true |
|---|---|---|---|---|
| **20 percent** | 54 | 2 | 4 | 60 |
| **60 percent** | 6 | 52 | 2 | 60 |
| **100 percent** | 4 | 0 | 56 | 60 |
| **Σ pred** | 64 | 54 | 62 | - |

Source: `vcm8/training/runs/gate3d/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **39** (data rows in `history.csv`).
- Best epoch by val_accuracy: **30** — train_accuracy `1`, val_accuracy `0.8999999761581421`.
- Best epoch by val_loss: **27** — val_loss `0.4230160117149353`.
- Final val_loss `0.450875848531723`; trend over last 3 epochs: **mixed (last3: 0.44835070 → 0.44820806 → 0.45087585)**.
- LR-reduction events: none logged (no learning_rate column).

### gate4_v2 — color (Round-2 targeted TTS)

**Status:** NEUTRAL (0.8833); `gate4` v1 kept.

**Metrics** — val_accuracy = `0.8833333253860474`, val_loss = `0.41009873151779175`, param_count = `413571`, rows = **train=1449, aug_train=20, original_train=1429, val=180**. Checkpoint: `vcm8/training/runs/gate4_v2/best_model.keras`.

Source: `vcm8/training/runs/gate4_v2/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 |
|---|-------|-----------|--------|----|
| 0 | Red | 0.9354838709677419 | 0.9666666666666667 | 0.9508196721311475 |
| 1 | Blue | 0.7971014492753623 | 0.9166666666666666 | 0.8527131782945736 |
| 2 | Green | 0.9387755102040817 | 0.7666666666666667 | 0.8440366972477065 |

Source: `vcm8/training/runs/gate4_v2/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

| true \ pred | Red | Blue | Green | Σ true |
|---|---|---|---|---|
| **Red** | 58 | 0 | 2 | 60 |
| **Blue** | 4 | 55 | 1 | 60 |
| **Green** | 0 | 14 | 46 | 60 |
| **Σ pred** | 62 | 69 | 49 | - |

Source: `vcm8/training/runs/gate4_v2/report.json` `confusion_matrix`.

**Epoch-curve summary:**

- Epochs run: **39** (data rows in `history.csv`).
- Best epoch by val_accuracy: **30** — train_accuracy `1`, val_accuracy `0.8833333253860474`.
- Best epoch by val_loss: **34** — val_loss `0.3932863473892212`.
- Final val_loss `0.39921268820762634`; trend over last 3 epochs: **mixed (last3: 0.39818835 → 0.40621957 → 0.39921269)**.
- LR-reduction events: ep25: 0.001 → 0.0005; ep35: 0.0005 → 0.00025.

### gateN_v3 — unified 12-class numerical model (supplemental-data variant)

**Status:** variant — NOT promoted (`gateN_v1` 0.9323 remains recommended). **CONFLICT FLAG:** `vcm8/training/reports/gateN_v3_fil_report.md` claims `gateN_v3` = 0.9027; the on-disk `report.json` below says otherwise — flagged, not resolved.

**Metrics** — val_accuracy = `0.932299017906189`, val_loss = `0.25373348593711853`, param_count = `414732`, rows = **total_train=8143, original_train=5653, tts_aug=90, numerals=2400, val=709**, Adam lr `0.001`, init_checkpoint `vcm8/training/runs/gateN_v1/best_model.keras`. Checkpoint: `vcm8/training/runs/gateN_v3/best_model.keras`.

Source: `vcm8/training/runs/gateN_v3/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 | support |
|---|-------|-----------|--------|----|---------|
| 0 | 10 seconds | 0.8813559322033898 | 0.8666666666666667 | 0.8739495798319328 | 60 |
| 1 | 30 seconds | 0.9629629629629629 | 0.896551724137931 | 0.9285714285714286 | 58 |
| 2 | 1 minute | 0.9333333333333333 | 0.9655172413793104 | 0.9491525423728814 | 58 |
| 3 | 6 AM | 0.9166666666666666 | 0.9649122807017544 | 0.9401709401709402 | 57 |
| 4 | 8 AM | 0.8769230769230769 | 0.9661016949152542 | 0.9193548387096774 | 59 |
| 5 | 9 PM | 1 | 0.9473684210526315 | 0.972972972972973 | 57 |
| 6 | 18 degrees | 0.9032258064516129 | 0.9333333333333333 | 0.9180327868852459 | 60 |
| 7 | 22 degrees | 1 | 0.8666666666666667 | 0.9285714285714286 | 60 |
| 8 | 26 degrees | 0.90625 | 0.9666666666666667 | 0.9354838709677419 | 60 |
| 9 | 20 percent | 0.9047619047619048 | 0.95 | 0.926829268292683 | 60 |
| 10 | 60 percent | 0.9375 | 1 | 0.967741935483871 | 60 |
| 11 | 100 percent | 1 | 0.8666666666666667 | 0.9285714285714286 | 60 |

Source: `vcm8/training/runs/gateN_v3/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

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

**Epoch-curve summary:**

- Epochs run: **30** (data rows in `history.csv`).
- Best epoch by val_accuracy: **17** — val_accuracy `0.932299017906189`.
- Final val_accuracy `0.9252468347549438`.

### gateN_v3_lr1e4 — unified 12-class numerical model (supplemental-data variant)

**Status:** variant — NOT promoted (`gateN_v1` 0.9323 remains recommended). **CONFLICT FLAG:** `vcm8/training/reports/gateN_v3_fil_report.md` claims `gateN_v3` = 0.9027; the on-disk `report.json` below says otherwise — flagged, not resolved.

**Metrics** — val_accuracy = `0.9153737425804138`, val_loss = `0.26667216420173645`, param_count = `414732`, rows = **total_train=8143, original_train=5653, tts_aug=90, numerals=2400, val=709**, Adam lr `0.0001`, init_checkpoint `vcm8/training/runs/gateN_v1/best_model.keras`. Checkpoint: `vcm8/training/runs/gateN_v3_lr1e4/best_model.keras`.

Source: `vcm8/training/runs/gateN_v3_lr1e4/report.json` (`val_accuracy`, `val_loss`, `param_count`, row counts; `history.csv` for the curve).

**Per-class precision / recall / F1** (labels in `vcm8/config/model_registry.json` order):

| # | label | precision | recall | F1 | support |
|---|-------|-----------|--------|----|---------|
| 0 | 10 seconds | 0.7792207792207793 | 1 | 0.8759124087591241 | 60 |
| 1 | 30 seconds | 0.9615384615384616 | 0.8620689655172413 | 0.9090909090909091 | 58 |
| 2 | 1 minute | 0.9473684210526315 | 0.9310344827586207 | 0.9391304347826087 | 58 |
| 3 | 6 AM | 0.9 | 0.9473684210526315 | 0.9230769230769231 | 57 |
| 4 | 8 AM | 0.9272727272727272 | 0.864406779661017 | 0.8947368421052632 | 59 |
| 5 | 9 PM | 1 | 0.9473684210526315 | 0.972972972972973 | 57 |
| 6 | 18 degrees | 0.8285714285714286 | 0.9666666666666667 | 0.8923076923076924 | 60 |
| 7 | 22 degrees | 1 | 0.7 | 0.8235294117647058 | 60 |
| 8 | 26 degrees | 0.8571428571428571 | 1 | 0.9230769230769231 | 60 |
| 9 | 20 percent | 0.9032258064516129 | 0.9333333333333333 | 0.9180327868852459 | 60 |
| 10 | 60 percent | 1 | 0.9333333333333333 | 0.9655172413793104 | 60 |
| 11 | 100 percent | 1 | 0.9 | 0.9473684210526315 | 60 |

Source: `vcm8/training/runs/gateN_v3_lr1e4/report.json` `per_class`.

**Full confusion matrix** (rows = true label, columns = predicted label; class-label headers in registry order):

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

**Epoch-curve summary:**

- Epochs run: **19** (data rows in `history.csv`).
- Best epoch by val_accuracy: **10** — val_accuracy `0.9153737425804138`.
- Final val_accuracy `0.9111424684524536`.

> **Inventory gap (2026-10-03):** runs `gateN_scratch` (`0.9224259257316589`), `gateN_v3_lr5e4` (`0.8984485268592834`), `gateN_v3`, `gateN_v3_lr1e4`, and `gate2_v3` (`0.9772979021072388`; Filipino synthetic, `total_train` 42,496) exist under `vcm8/training/runs/` but were outside the original 21-run inventory. The two gateN variants are documented above; the others remain flagged for the evidence owner.

## Notes

### Reconciliation — discrepancies flagged (not silently resolved)

- **registry vs reports (gate3b):** `model_registry.json` `gate3b.status` = `trained_val_acc_0.4104_data_limited` does not name a variant; the promoted checkpoint is `runs/gate3b_v3`. Unchanged.
- **gate3b_v5 registry gap:** `gate3b_v5` report val_accuracy `0.45086705684661865` (0.4509) beats `gate3b_v3` `0.41040462255477905` (0.4104) — see `baseline_comparison.beats_v3=true` — yet `model_registry.json` still records `gate3b` = 0.4104. Flagged, not resolved.
- **registry vs report (gate3c/gate4/gate5):** registry statuses are rounded to 4 dp (`0.9556`, `0.8889`, `0.9771`) while reports carry full float values; these agree to 4 dp.
- **val_loss rounding in `status.json`:** `status.json` reports 4-dp `val_acc` only; full-precision values are in each `report.json`.
- **report vs history last-decimal mismatch (val_loss):** for several runs the `report.json` `val_loss` differs from the `history.csv` value at the best epoch in the last 1–2 decimals (e.g. `gate2` report `0.13865311443805695` vs history-by-val_acc epoch 26 `0.1386517882347107`). Presumed float/recompute rounding; flagged, not resolved.
- **`gate3b_v4` missing `param_count`:** its `report.json` has no `param_count`; only a `params` object (`{"dropout":0.5,"gru_units":32,"label_smoothing":0.1}`). Shown as “—” in the summary table.
- **`gate3b_v5` val_loss metric:** its `val_loss` (`1.171367883682251`) is higher than `gate3b_v3` even though val_accuracy is higher — reported verbatim; the model trades calibration for accuracy here.

## Sources

Per-run files: `vcm8/training/runs/<run>/report.json` and `vcm8/training/runs/<run>/history.csv` for all 21 runs listed above.
Label orders and statuses: `vcm8/config/model_registry.json`. Global status/provenance: `vcm8/status.json`. Preprocessing: `vcm8/training/preprocessing_v1.json`, `vcm8/training/feature_shape.json`.
Cross-reference tables: `vcm8/training/TRAINING_RESULTS.md`, `vcm8/training/NEXT_STEPS.md`, `MODEL_DATASET_SPECIFICATIONS.md`.
