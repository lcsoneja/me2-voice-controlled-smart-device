# ME2 — Voice Controlled Smart Device

*Always-on keyword + intent recognition at the edge · no cloud round-trip*

**1 October 2026 · Leandro Soneja — AI 231 ME2 · Model · Dataset · Training on A100 · Validation on RPi 4**

> Corrected transcription of `me2-deck-filled.pdf` (2026-10-24). Fixes vs the filled PDF:
> cluster (DGX → A100), classifier (DS-CNN → TC-ResNet), optimiser ("n/a" → Adam+cosine),
> dataset source (class holdout → own training corpus), runtime (onnxruntime → TFLite),
> clipped strings restored, honest RPi-validation status.

---

## Model

| Item | Value |
|---|---|
| Parameters / weights | **0.34 M · 0.70 MB** (V64P: 338,260 params; TFLite float16 = 698,728 B) |
| Architecture | TC-ResNet pure-CNN 1D (3 residual blocks, 64/128/256 filters; no GRU, no Flex ops) |
| Input | 9-channel 9-window log-mel (148 frames × 60 mels; time offsets ±2 s) |
| Outputs | 20-way softmax: 19 intents + NEG (rejection class) |

## Dataset

| Item | Value |
|---|---|
| Source (training) | Own corpus: synthetic TTS bank (CosyVoice, 21 voices × accents) × 8 noise-augmented views + paired background-only NEG rows + owner voice recordings |
| Hours / utts | ≈ 5.8 h base speech / 8,730 base utterances → ×8 views = **239,169 feature rows**; + 1,581 ambient NEG rows; + 280 owner clips (owner fine-tune) |
| Speakers | 21 synthetic TTS voices + 1 owner (training); 6 real speakers (holdout evaluation only) |
| Labels | **19 intents · 3 slots** (Gate 3-5: ALARM time, TIMER duration, TEMPERATURE degrees, BRIGHTNESS %, COLOR, REMINDER text) |
| Evaluation sets | ME2 class holdout (HF: `airimonda/ai231-me2-voice-commands`, 202 clips: 186 commands = 100 syn + 86 real-voice, 16 OOS) + sealed 20-clip owner wake benchmark + owner-280 diagnostic |

## Training on the A100 cluster

| Item | Value |
|---|---|
| Cluster | **A100 cluster — 8× A100-SXM4-40GB (shared)**; 1 GPU per run, memory-growth enabled |
| Objective | Cross-entropy (sparse categorical) on TC-ResNet CNN classifier; 20-way with NEG rejection class. No CTC / no attention. |
| Optimiser | **Adam** + cosine decay (LR 1e-3 head training → 1e-4 fine-tune; α=0.05) |
| Steps / loss | 3,687 steps/epoch × 15 epochs (V46 lineage); final train CE ≈ 0.004–0.02 |
| Augmentation on-the-fly | Importance-weighted time warp (p=0.7, max 0.18); 8 dataset views: clean, music, music+Gaussian, music+babble, gain ±6 dB, time-shift ±100 ms, speed 0.85–1.15×, ambient |
| Fine-tune stages | V46 (warp) → +paired/expanded NEG (V64d) → owner fine-tune w=2.0 (V64P) → temperature scaling T=0.5 (V64P-T) |
| Seed | 42 (all runs) |
| Wall-clock | ≈ 96 min per 15-epoch base run (shared GPU); fine-tune ≈ 80 min |

## Architecture diagram (text form)

```
Mic 16 kHz ──▶ log-mel 148×60 ──▶ 9-window slide (offsets −50…+50 frames)
          ──▶ TC-ResNet causal 1D CNN × 3 residual blocks ──▶ intent head (19+NEG softmax)
                                          └──▶ slot head: Gate 3-5 CRNN specialists (routed by Gate 2)
                                          └──▶ actuator: Raspberry Pi 4
Streaming: 20 s ring buffer · 6-frame scoring window (pure CNN, stateless — no KV-cache)
```

## Validation on the Raspberry Pi 4

| Item | Value |
|---|---|
| Keyword / intent acc | **pending live Pi test** (Pi offline at submission prep) |
| Pipeline batch (laptop audio path, 2026-10-24) | full **91.2%** (187/205) · action 91.7% · wake 94.6% · OOS reject 0.0% |
| False-accept rate | TBD (live test) |
| Latency p95 / RTF | batch p95 **47.9 ms** (winner stack); model-only TFLite p50 0.55 ms (host) |
| Runtime | **TensorFlow Lite float16 · 1 thread (XNNPACK)** — not onnxruntime |

---

## To Be Submitted — what the reviewer will look for

| # | Item | Status |
|---|---|---|
| 1 | Repo public, one-command reproduction | pending — repo URL TBD |
| 2 | Dataset licensed and citable (DOI) | **uploaded to HF (private)** — `Drewboy/ai231-vcm-v64p-training-store` + `Drewboy/ai231-vcm-v20aux-phoneme-store`, CC-BY-NC-4.0 research-only |
| 3 | Training logs + final checkpoint committed | **done** — shipping/ packages + SHA256SUMS + timestamps + reports/*.json |
| 4 | Pi 4 latency reproduced by the posted script | **pending** — Pi offline 2026-10; model-only latency measured on host (0.55 ms p50) |
| 5 | Held-out test set, unseen speakers | **done** — ME2 holdout (6 unseen speakers) + sealed 20-clip owner benchmark |
| 6 | Baseline of comparable size compared | **done** — 55-model Gate-2 comparison (V3→V77) + 13 Gate-1 variants |

## Submission links

| Item | Value |
|---|---|
| GitHub repository | ⟨pending — to be provided⟩ |
| Dataset location | huggingface.co/datasets/**Drewboy/ai231-vcm-v64p-training-store** (V64P store) · huggingface.co/datasets/**Drewboy/ai231-vcm-v20aux-phoneme-store** (v20-aux) · eval holdout: huggingface.co/datasets/airimonda/ai231-me2-voice-commands |
| A100 cluster | 8× A100-SXM4-40GB shared node; per-run wall-clock in reports/*.json; seed 42 |
| Model weights | shipping/ packages — TFLite f16 + SHA256SUMS + MANIFEST (HF release planned) |

---

## Best Combination — ME2 full-pipeline batch (2026-10-24)

424 takes × 13 Gate 1 × 55 Gate 2 × raw × arch v1+v2 — **winner: `gate1v3_f32` × `gate2v64p_paired_owner` × raw × v1**:
full **187/205 (91.2%)**, action 91.7%, wake 94.6%, OOS reject 0.0%, p95 47.9 ms

**Demo setup (Pipeline test window):** Gate 1 = `gate1v3_f32` · Gate 2 = `gate2v64p_paired_owner` · Architecture = v1 · NC = raw

### Top combinations (ranked by fully-correct rate)

| # | G1 | G2 | nc | arch | full | rate | act | wake | oosrej | ms | p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | v3_f32 | v64p_paired_owner | raw | v1 | 187/205 | 91.2% | 91.7% | 94.6% | 0.0% | 18.0 | 47.9 |
| 2 | v3_f16 | v64p_paired_owner | raw | v1 | 187/205 | 91.2% | 91.7% | 94.6% | 0.0% | 20.1 | 51.8 |
| 3 | v3_f32 | v20_aux | raw | v1 | 186/205 | 90.7% | 93.7% | 94.6% | 0.0% | 12.7 | 30.7 |
| 4 | v3_f16 | v20_aux | raw | v1 | 186/205 | 90.7% | 93.7% | 94.6% | 0.0% | 14.0 | 31.6 |
| 5 | v2_f32 | v64p_paired_owner | raw | v1 | 186/205 | 90.7% | 91.7% | 93.7% | 0.0% | 27.3 | 63.5 |
| 6 | v2_f16 | v64p_paired_owner | raw | v1 | 186/205 | 90.7% | 82.6% | 93.7% | 50.0% | 63.0 | 105.3 |
| 7 | v2_f16 | v20_aux | raw | v1 | 185/205 | 90.2% | 93.9% | 93.7% | 50.0% | 81.9 | 90.1 |
| 8 | v2_f32 | v20_aux | raw | v1 | 185/205 | 90.2% | 93.7% | 93.7% | 0.0% | 19.2 | 50.8 |
| 9 | v3_f32 | v19 | raw | v1 | 185/205 | 90.2% | 92.7% | 94.6% | 0.0% | 6.1 | 14.2 |
| 10 | v3_f16 | v19 | raw | v1 | 185/205 | 90.2% | 92.7% | 94.6% | 0.0% | 7.5 | 18.2 |
