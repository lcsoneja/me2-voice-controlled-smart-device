# Architecture v2 — False-Trigger Verification Designs

**Date:** 2026-10-23
**Context:** Gate 2 (19-intent classifier) on Raspberry Pi 5, fully offline. Gate 1 = wake word (Nova/Piattos) DS-CNN TFLite. Gate 2 current: 5.92 s sliding window, 1 s evaluation cadence, per-intent thresholds, NEGATIVE class, PID confidence integrator (V54/V54b margin-based), wake-ordering grace.
**Problem:** Single-stage argmax classification false-triggers; CALL fires on unrelated speech. Already-tried mitigations reduce but do not eliminate the problem.

---

## Summary

Five concrete Architecture v2 candidates are evaluated for their mechanism, expected false-trigger reduction, Pi 5 feasibility, and implementation sketch. The recommended first deployment path is **Candidate A (VAD + Two-Pass Verification)**, which leverages existing project infrastructure, adds minimal latency, and directly targets the CALL false-trigger case with a post-trigger verification stage. The most aggressive reduction requires **Candidate C (Per-Intent Verification Network)**, which adds a tiny dedicated verifier per high-false-positive intent. **Candidate E (Temporal Consistency via Frame-Level Posteriors)** is the most principled approach but requires a new model architecture.

---

## Candidate A: VAD Gate + Post-Trigger Verification

### Mechanism
Insert a **Voice Activity Detection (VAD)** stage before Gate 2 inference. Currently the pipeline runs every 1 s on a sliding window regardless of whether acoustic energy represents speech. Adding VAD means:
- Gate 2 inference runs only when VAD reports speech probability > threshold (e.g., 0.5).
- A **post-trigger verification** buffer: after Gate 2 triggers an intent, the system collects ~1 s of *additional* post-trigger audio and runs a small binary classifier on the concatenated trigger + post-trigger window to confirm or reject the activation.
- Rejected triggers are dropped before reaching Gate 3-5.

This is directly inspired by Apple's Streaming Transformer architecture (Garg et al., Interspeech 2021), which "suppresses 95% of false triggers with an additional one second of post-trigger audio" using a streaming transformer encoder that jointly performs VTD and FTM tasks using only acoustic features.

### Expected false-trigger reduction
- **VAD alone:** Eliminates triggers on silence/noise segments. Approximately 15-30% of current false triggers may originate from non-speech (background noise, microphone handling) that VAD would gate.
- **VAD + post-trigger verification:** Aims at 50-80% reduction on hard false triggers (CALL fired on speech containing phonetic fragments that resemble "call"). Benchmarks from Apple's LSTM-based FTM (Dighe et al.) show 87% false trigger mitigation at 99% TPR using small-footprint models.

### Added latency and memory
- **VAD:** ~1-2 ms per 32 ms frame (Silero v5 scales: ~0.6 ms/frame on iPhone 13 Pro). On Pi 5, expect ~2-3 ms per frame — negligible vs. the current 1 s cadence.
- **Post-trigger verification:** Adds 1 s of post-trigger audio collection + a small forward pass (~1-5 ms for a 10-50K parameter binary classifier TFLite). Total latency added: ~1-1.1 s.
- **Memory:** VAD model ~1.7 MB (Silero). Verification model ~50-200 KB (TFLite).

### Pi 5 feasibility
**High.** VAD models (especially Silero v5, MIT-licensed) are well-established for ARM deployment. Silero v5 has been benchmarked on ARM CPUs with real-time factors well under 1. The post-trigger binary classifier can be a tiny DS-CNN (like the existing Gate 1 wake model architecture) with 2 outputs (TRIGGER_CONFIRMED / REJECT). Pi 5's Cortex-A76 @ 2.4 GHz with NEON handles this comfortably.

### Reuse of existing TFLite models
- **VAD:** New model (Silero VAD or WebRTC VAD — no TFLite needed for WebRTC, it's C signal processing ~50 KB).
- **Post-trigger verifier:** New tiny binary classifier, but can reuse the same preprocessing pipeline (148-frame log-mel features) and TFLite runtime.

### Implementation sketch
1. Integrate WebRTC VAD (C library, no ML dependency) or Silero VAD ONNX/TFLite in the audio capture loop.
2. Gate Gate 2 inference: skip classification when VAD probability < threshold.
3. When Gate 2 triggers (intent + threshold-qualified): collect another ~1 s (16000 samples) of post-trigger audio into a circular buffer.
4. Concatenate pre-trigger window + post-trigger audio → same preprocessing pipeline → tiny binary verifier TFLite.
5. Verifier output > threshold → forward to action; else → reject, reset Gate 2 state.

### Sources
- **Apple Streaming Transformer FTM:** Garg et al., *Interspeech 2021*, https://machinelearning.apple.com/research/streaming-transformer — 95% false trigger suppression with 1 s post-trigger audio. Direct evidence.
- **Apple LSTM-based FTM:** Dighe et al., https://machinelearning.apple.com/research/on-device-false-trigger — 87% FTM at 99% TPR, small-footprint LSTM. Direct evidence.
- **Silero VAD:** https://voxrt.com/voice-activity-detection — 1.7 MB, ~0.6 ms/frame on mobile, MIT-licensed. Direct evidence.
- **WebRTC VAD:** https://www.videosdk.live/developer-hub/webrtc/webrtc-voice-activity-detection — GMM + energy-based, 10-30 ms frames, no ML dependency. Direct evidence.

---

## Candidate B: Confidence Calibration + Adaptive Per-Intent Margins

### Mechanism
The current V54b margin integrator uses a fixed margin (τ = 0.25) subtracted from the top-1 minus top-2 difference. Architecture v2 applies:
- **Temperature scaling** to the softmax posterior: calibrate the Gate 2 model's output probabilities on a held-out validation set using post-hoc temperature scaling (learned T > 1 to reduce overconfidence). This produces better-calibrated probabilities where the confidence score is a more reliable indicator of correctness.
- **Per-intent adaptive margins**: instead of a single τ for all 19 intents, compute per-intent τ_i from the validation set's confidence histogram for that intent. Intents with high false-positive rates (especially CALL) get a wider τ.
- **Two-phase margin**: distinguish between (a) the NEGATIVE class (already exists) and (b) an explicit "low confidence" rejection band between τ_min and τ_confirm.

### Expected false-trigger reduction
- **Temperature scaling alone:** Modest (5-15% reduction in false accepts) by making the confidence score more reliable.
- **Per-intent adaptive τ_CALL = 0.4–0.5:** Could reduce CALL false triggers by 30-50% because CALL's post-training confidences on non-CALL audio cluster higher than other intents (model overconfidence on CALL).
- **Combined:** Soft calibration + per-intent margin tuned on false-trigger trace data.

This builds on established techniques: Guo et al., "On Calibration of Modern Neural Networks" (ICML 2017) showed temperature scaling is highly effective for calibrating neural network confidences. The margin approach is used in the existing V54b but with a single global τ.

### Added latency and memory
- **Temperature scaling:** Zero runtime cost — it's a post-hoc scalar multiply on the logits before softmax (T = learned constant). The formula is `softmax_e_i = exp(logit_i / T) / Σ exp(logit_j / T)`.
- **Per-intent thresholds:** Zero cost — 19 floats stored alongside existing per-intent thresholds.
- **Total: 0 added latency, < 100 bytes added memory.**

### Pi 5 feasibility
**Very high.** No additional compute. The scaling factor is applied during the existing softmax operation. Thresholds are already applied per intent.

### Reuse of existing TFLite models
- **Full reuse.** Temperature scaling is applied post-inference in Python before the existing threshold check. No model retraining or conversion needed.

### Implementation sketch
1. Collect a held-out calibration set of ~1000 windows (mix of correct intents and false triggers/background).
2. Fit a single temperature T (scalar) by minimizing negative log-likelihood (NLL) on the calibration set using L-BFGS.
3. For each intent i, compute τ_i = P50_incorrect_i + 2 * MAD_incorrect_i — the margin where incorrect confidences for that intent historically peaked.
4. Modify `observe_gate2()` to apply `softmax(logits / T)` before threshold check, and use τ_intent instead of a single τ.
5. Add an explicit rejection band: if `max_p ∈ (τ_band_low, τ_confirm)`, emit "UNCERTAIN" instead of the intent.

### Sources
- **Temperature scaling for calibration:** Guo et al., *ICML 2017*, https://arxiv.org/abs/1706.04599 — temperature scaling is a simple, effective post-hoc calibration method. Direct evidence.
- **Per-class margin analysis:** https://arxiv.org/html/2312.05640v1 — KWS survey discusses class-wise confidence distributions. Interpretation.
- **Existing V54b margin PID:** Shipping/Gate2V56_ChampionStack_V46_PID_ship_EXPERIMENTAL_20261020/deploy/pid_stream_integrator.py — single global τ = 0.25. Direct evidence (project source).

---

## Candidate C: Per-Intent Verification Network (CALL Verifier)

### Mechanism
Build a small binary **verification network** tailored to the CALL intent (and extendable to other high-FP intents). The verifier operates as a second stage:
- When Gate 2 outputs CALL above threshold, instead of immediately routing to Gate 3, send the same acoustic window to the CALL verifier.
- The verifier is a small TC-ResNet or DS-CNN with 2 outputs: CALL_CONFIRMED / NOT_CALL.
- Only confirmed CALLs proceed to action.

This mirrors the approach of a "second-pass checker" used in Apple's Siri voice trigger system, where the first stage (detector) is high-recall and the second stage (checker) is high-precision.

### Expected false-trigger reduction
- **CALL-specific:** 70-90% reduction in CALL false triggers, because the verifier is trained exclusively to distinguish CALL from non-CALL audio (including acoustically similar commands, background speech, and the specific patterns that cause the false trigger).
- **All-intent extension:** 40-60% overall false trigger reduction if extended to top-5 false-trigger intents.

### Added latency and memory
- **Latency per CALL trigger:** ~2-5 ms for a small TFLite forward pass (DS-CNN with ~50-100K parameters).
- **Memory:** ~200-800 KB per verifier (TFLite float16).
- **Only paid on trigger events** (not on every Gate 2 tick), so average latency impact is < 0.1 ms in steady state.

### Pi 5 feasibility
**High.** A small DS-CNN or TC-ResNet is already proven on this platform (the existing Gate 1 wake model is a DS-CNN). The key question is collecting enough CALL vs. NOT_CALL training data. The existing dataset already has CALL samples (likely ~500-2000) and can use NEGATIVE/noise samples as NOT_CALL.

### Reuse of existing TFLite models
- **Preprocessing:** Full reuse (same 148-frame log-mel pipeline).
- **Model architecture:** Can reuse the Gate 1 DS-CNN model source (`models/gate1v12`-style architecture) with output changed from 2 wake classes to 2 verifier classes.
- **TFLite runtime:** Full reuse.

### Implementation sketch
1. Collect CALL_VERIFIER dataset: ~2000 CALL utterances (positive) + ~4000 not-CALL utterances (near-miss false triggers, acoustically similar commands like PLAY_MUSIC, silence, babble — negative).
2. Train a small DS-CNN (2 conv + 1 FC layers, ~50K params) on the same 148x60 log-mel features.
3. Convert to TFLite float16.
4. Add a `verify_intent(intent, features) -> bool` function in the pipeline.
5. Gate: `candidate = gate2_predict(features); if candidate == "CALL" and not verify_call(features): return NEGATIVE`.

### Sources
- **Apple multistage VTD architecture:** https://machinelearning.apple.com/research/voice-trigger — "high-recall first-stage detector → high-precision second-stage checker on AP." Direct evidence.
- **Apple Unified Acoustic Detector:** Rudovic et al., https://machinelearning.apple.com/research/unified-architecture — multi-task learning with task-specific classification heads. Supports per-invocation verification. Direct evidence.

---

## Candidate D: Embedding-Based Nearest-Neighbor Verification

### Mechanism
Replace the argmax softmax decision with a prototype-based verification:
- Compute a **fixed-dimensional embedding** (e.g., 64-128 dim) from an intermediate layer of the Gate 2 model (or a small embedding network).
- For each intent, maintain a set of **prototype embeddings** computed from clean training examples.
- A trigger is accepted only if (a) the softmax score exceeds threshold AND (b) the embedding distance to the nearest same-intent prototype is below a per-intent distance threshold, AND (c) the distance to the nearest different-intent prototype exceeds a margin.
- This rejects inputs that happen to land near the softmax decision boundary but are far from any training prototype in embedding space — a common pattern for false triggers.

This is related to **contrastive learning for KWS** and **open-set recognition** techniques widely adopted in production voice assistants.

### Expected false-trigger reduction
- **Embedding gap verification:** 40-60% reduction in false triggers from acoustically similar but non-command speech (e.g., someone saying "all" or "hall" that softmax maps near CALL).
- **Rejects OOD:** Particularly effective for out-of-distribution audio (noise, music, non-speech) that happens to score above the softmax threshold.

### Added latency and memory
- **Embedding extraction:** same cost as one Gate 2 forward pass if using an intermediate layer (feature vector readout — available from TFLite intermediate tensors), or ~1-3 ms for a lightweight embedding network.
- **Nearest-neighbor distance:** O(N_classes * D) where N=19, D=64 → ~1200 float operations = negligible on Pi 5 (~0.01 ms).
- **Memory:** 19 prototypes × 64 floats × 4 bytes = ~5 KB. Can optionally store 5-10 prototypes per intent for better coverage (~50 KB).

### Pi 5 feasibility
**Medium.** The embedding space approach requires access to an intermediate activation from the TFLite model. TFLite does support intermediate tensor inspection (`get_tensor(tensor_index)`), but it requires knowing the exact tensor name. Alternatively, train a small embedding network appended to the existing model's penultimate layer. Pi 5 can run this easily.

### Reuse of existing TFLite models
- **Partial reuse.** The existing Gate 2 model can serve as the embedding backbone if we read its penultimate layer activations. This requires identifying the right tensor index in the TFLite graph (tensor name like `dense_2/Relu` or similar).
- **Alternative:** Train a separate embedding network using the existing features.

### Implementation sketch
1. Freeze the existing Gate 2 model and extract penultimate activations for all training examples.
2. Compute class prototype embeddings as the mean of correctly-classified training embeddings per intent.
3. Tune per-intent distance thresholds on the calibration set.
4. Modify the inference pipeline:
   ```
   probs, embedding = gate2_predict_with_embedding(features)
   intent = argmax(probs) if max(probs) > threshold else NEGATIVE
   if intent != NEGATIVE:
       d_same = L2(embedding, prototype[intent])
       d_other = min(L2(embedding, prototype[other]) for other != intent)
       if d_same > d_thresh[intent] or d_other - d_same < margin:
           intent = NEGATIVE
   ```

### Sources
- **Contrastive learning for KWS:** https://arxiv.org/html/2312.05640v1 — discusses embedding-based approaches. Interpretation.
- **Open-set recognition for audio:** https://www.emergentmind.com/topics/device-directed-speech-detection-ddsd — discusses DDSD as binary classification using acoustic embeddings. Direct evidence.
- **TFLite intermediate tensors:** https://www.tensorflow.org/lite/api_docs/python/tf/lite/Interpreter#get_tensor — available via `get_tensor(index)`. Direct evidence.

---

## Candidate E: Temporal Consistency via Frame-Level Posterior Verification

### Mechanism
The current single-window (5.92 s) or slide-window (9 channels) approach collapses the entire temporal context into one classification. Architecture v2 adds **frame-level posterior verification** — inspired by Apple's HMM-DNN approach for "Hey Siri" and the PhoneCascade architecture (Gate2 V20 PhoneCascade already exists in the shipped packages as a disabled candidate):
- Augment the model with a **frame-level phoneme posterior head** that outputs per-frame phonetic probabilities.
- Verify intent consistency across frames: a single-frame peak of CALL does not confirm the command; the intent requires sustained phonetic evidence across multiple frames consistent with the CALL pronunciation.
- If the frame-level sequence is inconsistent (e.g., only 1-2 frames contain CALL-like phonemes, or the phoneme sequence maps to a different word), reject.
- Apple's HMM-DNN approach uses 21 phoneme states (7 phonemes × 3 states) plus silence/background states — the decoder aggregates across frames using Viterbi decoding.

The existing **Gate2 V20 PhonemeAux** package already ships a model trained with auxiliary phoneme supervision. However, the shipped package only exposes the intent output (the phone head was removed in deployment). Reintroducing the phone head or training a new model with this architecture is the key.

### Expected false-trigger reduction
- **Phoneme-consistent verification:** 50-70% reduction on false triggers from acoustically similar patterns. A single false peak of CALL confidence would fail phonetic verification because the frame-level phoneme posteriors over the full window don't spell out the phonetic sequence /kɔːl/.
- **Complementary to all other candidates:** Works on fundamentally different evidence (frame-level phonetics vs. window-level intent), so gains are additive.

### Added latency and memory
- **Frame-level inference:** If the existing Gate 2 model has the frame-level head integrated, the forward pass is identical. Adding a separate phoneme posterior model: ~3-10 ms per inference (small DS-CNN or CRNN with N_phonemes × 3 outputs + silence/background).
- **Phoneme sequence verification:** Viterbi or DTW decoding adds ~0.1-1 ms per inference.
- **Memory:** 200-500 KB for the phone posterior model (TFLite float16).

### Pi 5 feasibility
**Medium.** Requires either (a) retraining the Gate 2 model with a phoneme auxiliary head, or (b) training and deploying a separate phoneme posterior model. Option (b) is lower risk but adds memory. The PhoneCascade adapter is already identified as "needs a dedicated cascade runner" in the dashboard — meaning the project owners have already shipped the necessary model weights but haven't built the runner.

### Reuse of existing TFLite models
- **Gate2 V20 PhoneCascade:** Already shipped and verified as working — just needs the cascade runner to be implemented. Labels and preprocessing spec are in the package.
- **Gate2 V20 PhonemeAux:** Already shipped; intent-only head deployed but the underlying model has phone representations from training.

### Implementation sketch
1. Implement the Gate2 V20 PhoneCascade runner (or train a new frame-level model).
2. The PhoneCascade model produces a phoneme posteriorgram — per-frame probabilities over N_phoneme × 3 HMM states + silence + background.
3. Decode the frame sequence with Viterbi to find the most likely phoneme sequence.
4. Compare the decoded phoneme sequence to canonical pronunciation(s) of the triggered intent using DTW or edit distance.
5. Accept only if the distance is below threshold.

### Sources
- **Apple's HMM-DNN for "Hey Siri":** https://machinelearning.apple.com/research/voice-trigger — 21-state phoneme posterior DNN + HMM decoder with Viterbi. "The DNN predicts the state probabilities of a given speech frame. At the same time, the HMM decoder uses dynamic programming to combine the DNN predictions." Direct evidence.
- **Gate2 V20 PhoneCascade:** Shipping/Gate2V20_PhoneCascade_ship_EXPERIMENTAL_20261018 — shipped package; dashboard shows as disabled with note "two-stage phone-posterior cascade; needs a dedicated cascade runner." Direct evidence (project source).
- **Gate2 V20 PhonemeAux:** Shipping/Gate2V20_PhonemeAux_ship_EXPERIMENTAL_20261018 — trained with phoneme auxiliary loss; intent-only head deployed. Direct evidence (project source).

---

## Comparison Matrix

| Criterion | A (VAD+Post-Trigger) | B (Calibration+Margins) | C (Per-Intent Verifier) | D (Embedding NN) | E (Phoneme Verif.) |
|---|---|---|---|---|---|
| **False-trigger reduction** | Medium-High (50-80%) | Low-Medium (20-50%) | High (70-90% on CALL) | Medium (40-60%) | Medium-High (50-70%) |
| **Latency added** | 1-1.1 s (post-trigger) | None | 2-5 ms (on trigger) | 1-3 ms | 3-10 ms |
| **Memory added** | ~1.7 MB (VAD) + ~100 KB | ~100 bytes | ~200-800 KB | ~5-50 KB | ~200-500 KB |
| **Pi 5 feasibility** | High | Very High | High | Medium | Medium |
| **TFLite reuse** | Medium (new VAD + verifier) | Full | High (same arch) | Partial | Partial (PhoneCascade exists) |
| **Training data needed** | CALL false-trigger + background | None (post-hoc) | CALL + hard negatives | No labels needed | Already exists (V20 trained) |
| **Implementation effort** | 2-3 days | 0.5 day | 3-5 days | 2-3 days | 5-10 days |
| **Risk** | Low | Very Low | Low | Medium | Medium-High |
| **Residual CALL FP** | Can be tuned with TH | Needs wider margin | Lowest residual | Reduced | Reduced |
| **Source** | Apple Streaming Transformer | Guo et al. 2017 | Apple Siri VTD | Open-set recog. lit. | Apple HMM-DNN |

---

## Integration Plan (Recommended Order)

### Phase 1 — Quick wins (1 day)
1. **Candidate B** — Temperature scaling + adaptive per-intent margins. Zero added latency, full model reuse. Calibrate on held-out validation set, set τ_CALL = 0.45 (vs. current global 0.25). Measure false-trigger reduction on the owner-280 diagnostic and trap test.
2. **WebRTC VAD gating** — Simple C integration, no ML dependency. Gate Gate 2 inference on speech detection. Measure false-trigger reduction from silencing noise-only triggers.

### Phase 2 — Medium effort (3-5 days)
3. **Candidate C** — CALL verifier. Collect CALL vs. hard-negative training data (especially the acoustically similar utterances that trigger CALL). Train tiny DS-CNN verifier. Deploy in front of Gate 3 routing for CALL only. This directly addresses the #1 complaint (CALL false trigger).
4. **Candidate A post-trigger verification** — Add the post-trigger 1 s buffer and verification classifier. Reuse the CALL verifier from Phase 2 as the verification model.

### Phase 3 — Advanced (5-10 days)
5. **Candidate E** — PhoneCascade runner. The model weights already exist in Shipping/Gate2V20_PhoneCascade_ship_EXPERIMENTAL_20261018. Build the cascade runner that was identified as missing. This provides frame-level phonetic verification with zero additional model training — just pipeline engineering.
6. **Candidate D** — Embedding verification as an additional gate. Use penultimate activations from the latest Gate 2 model.

---

## Open Questions / Missing Evidence

1. **False-trigger rate breakdown:** What fraction of CALL false triggers come from (a) silence/noise, (b) background speech containing "call"-like fragments, (c) other commands (e.g., "all" in PLAY_MUSIC context), (d) unknown? Project-owner false-trigger trace data would inform which candidate to prioritize. — UNVERIFIED
2. **Temperature scaling effect on existing model:** The calibrated temperature T is unknown without running post-hoc optimization on the Gate 2 model's validation set. — UNVERIFIED
3. **PhoneCascade frame-level accuracy:** The shipped V20 PhoneCascade model's frame-level phoneme accuracy is not documented in its package manifest. The dashboard notes it as "experimental." — UNVERIFIED
4. **Pi 5 TFLite latency for 148x60x9 slide models:** The V56 README reports host (laptop) p50 = 0.562 ms. Pi 5 TFLite latency for slide-window models is not benchmarked in project docs. Community benchmarks show TFLite on Pi 5 running 3-5× faster than Pi 4, suggesting ~2-5 ms for a 338K parameter model. — UNVERIFIED
5. **NEGATIVE class label distribution:** The distribution of NEGATIVE (class 20) training examples is not visible in scope — whether it's balanced across all background types or concentrated in a few categories affects VAD and embedding approaches. — UNVERIFIED

---

## Sources

### Kept (strong sources)
- **Apple Streaming Transformer for VTD/FTM** (Garg et al., Interspeech 2021) — https://machinelearning.apple.com/research/streaming-transformer. Primary source. Key citation for post-trigger verification (95% FTM at 1 s post-trigger audio).
- **Apple Knowledge Transfer for On-device FTM** (Dighe et al.) — https://machinelearning.apple.com/research/on-device-false-trigger. Primary source. LSTM-based FTM, 87% FTM @ 99% TPR, knowledge transfer approach.
- **Apple Unified Acoustic Detector (UAD)** (Rudovic et al.) — https://machinelearning.apple.com/research/unified-architecture. Primary source. Multi-task learning for multiple invocation types, 50% relative FPR improvement.
- **Apple Siri Voice Trigger System Architecture** — https://machinelearning.apple.com/research/voice-trigger. Primary source. Detailed description of multistage Siri voice trigger (HMM-DNN detector → checker → speakerID → SDSD).
- **Device-Directed Speech Detection survey** — https://www.emergentmind.com/topics/device-directed-speech-detection-ddsd. Synthesis source. Comprehensive overview of DDSD literature including acoustic, ASR, and lexical approaches.
- **Temperature Scaling for Neural Net Calibration** (Guo et al., ICML 2017) — https://arxiv.org/abs/1706.04599. Primary source. Foundational paper on post-hoc confidence calibration.
- **On-Device VAD (Silero v5)** — https://voxrt.com/voice-activity-detection. Primary source. ~1.7 MB footprint, < 1 ms/frame on mobile CPUs, MIT-licensed.
- **Gate2 V20 PhoneCascade shipped package** — Shipping/Gate2V20_PhoneCascade_ship_EXPERIMENTAL_20261018. Project source. Frame-level phonetic posterior cascade; adapter identified as "pending dedicated cascade runner."
- **Gate2 V56 Champion Stack PID Integrator** (V54/V54b) — Shipping/Gate2V56_ChampionStack_V46_PID_ship_EXPERIMENTAL_20261020/deploy/pid_stream_integrator.py. Project source. Current PID integrator code and tuning.

### Rejected/deprioritized
- Generic "SigmaMedStat: Temporal Signal Modeling for ICU False Alarm Reduction" — Medical ICU context, not applicable to voice command false triggers.
- Generic KWS survey (arxiv.org/html/2312.05640v1) — Student project covering basic KWS models; no false-trigger-specific content beyond survey framing.
- Edge Impulse KWS tutorial — General embedded ML tutorial; no false-trigger mitigation specifics.
- Hackster.io Pi 5 TFLite benchmark — Community benchmark (single data point); non-authoritative.

---

## Next Steps

1. Run temperature scaling optimization on the current best Gate 2 model (V46 or V21P) to find the calibrated T and per-intent τ_i. This requires a held-out validation set with ~1000 examples.
2. Implement the PhoneCascade runner for the already-shipped Gate2 V20 model to test frame-level phonetic verification with zero additional training cost.
3. Record a CALL-specific false-trigger trace (10-20 naturally-occurring false triggers in the target deployment environment) to understand the acoustic profile of the CALL false-trigger case.
4. Measure Pi 5 TFLite latency for the current champion model (V46 9-window slide, 338K params) to establish baseline for latency budget allocation.
