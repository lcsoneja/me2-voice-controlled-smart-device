# Research: Preprocessing + Quantization for Gate-1/CRNN on Pi 5 (LiteRT/TFLite + XNNPACK)

## Verdict
Numpy-only log-mel preprocessing with a precomputed librosa mel filterbank is sound and matches published edge-audio practice: openWakeWord ships a fixed, frozen feature extractor (melspectrogram model) entirely outside its wake-word classifier, and the project's verified 20/20 parity check removes the main correctness risk. The float16/float32 LiteRT path is the right default; int8 PTQ for the Bidirectional-GRU remains blocked by a documented, never-fixed upstream converter segfault, with TF-2.13 downgrade, dynamic-range quantization, or ai-edge-torch/onnx2tf as realistic workarounds.

## Key findings
1. **Out-of-graph frozen preprocessing is standard practice.** openWakeWord's production pipeline computes the melspectrogram in a separate, fixed ONNX/TFLite feature model and feeds static (76,32) mel frames to the classifier — feature extraction decoupled from the wake model, exactly analogous to the numpy mel path. https://github.com/dscripka/openWakeWord/blob/main/openwakeword/utils.py (direct fetch); PyPI: "shared feature extraction backbone ... converts melspectrogram inputs" https://pypi.org/project/openwakeword/ **Support:** direct evidence. **Confidence:** high.
2. **librosa mel filterbank is a fixed linear matrix** (`librosa.filters.mel` returns a constant (n_fft/2+1) x n_mels transform), so precomputing it and applying it in numpy is deterministic and exact. https://librosa.org/doc/latest/generated/librosa.filters.mel.html **Support:** direct evidence (API docs). **Confidence:** high.
3. **The Bidirectional-GRU int8 segfault is a known upstream bug, not a setup error.** #62281: GRU INT8 PTQ with representative dataset segfaults on TF 2.14+ (worked on TF 2.13); confirmed by TF staff, closed stale June 2024 without a fix. https://github.com/tensorflow/tensorflow/issues/62281 **Support:** direct evidence (issue body + staff comments). **Confidence:** high.
4. **Still broken through TF 2.16–2.18, including quantized RNNs.** #76672: quantizing a GRU SavedModel segfaults on 2.16.1–2.18 (LSTM too); TF staff suggested `pip install tf-keras` (Keras 2) as mitigation; closed not_planned and moved to LiteRT (Jan 2025); commenter confirms segfault persists on 2.18. https://github.com/tensorflow/tensorflow/issues/76672 **Support:** direct evidence. **Confidence:** high.
5. **The segfault is confined to quantization calibration, not RNN conversion itself.** #87468: float32 TFLite conversion of the same GRU model succeeds; the crash occurs during representative-dataset calibration for INT8. https://github.com/tensorflow/tensorflow/issues/87468 **Support:** direct evidence (issue body). **Confidence:** high — consistent with the project's float16/float32 success.
6. **Documented workarounds for the segfault:** (a) run conversion with TF 2.13, which predates the regression (#62281 body: "runs and works fine with TF 2.13"); (b) Google's suggested path is re-export via AI-Edge-Torch (PyTorch), which converted GRU models successfully in the thread (#62281, pkgoogle comment); (c) onnx2tf exposes `enable_rnn_unroll` for RNN→TFLite export with directionality/unroll handling. https://github.com/tensorflow/tensorflow/issues/62281 , https://deepwiki.com/PINTO0309/onnx2tf/4.9-other-operators **Support:** direct evidence for (a)/(b); docs-derived for (c). **Confidence:** high for (a)/(b), medium for (c).
7. **Float16 quantization is officially recommended where int8 fails** (weights float16, activations float32 — no calibration step, so it sidesteps the GRU calibration bug). Official PTQ guide and float16 guide. https://www.tensorflow.org/model_optimization/guide/quantization/post_training ; https://developers.google.com/edge/litert/conversion/tensorflow/quantization/post_training_float16_quant **Support:** direct evidence (docs). **Confidence:** high.
8. **XNNPACK Pi 5 caveat:** users report XNNPACK INT8 inference runs slower with 4 threads than 2 on a Raspberry Pi 5 (Jan 2026 Google AI forum). https://discuss.ai.google.dev/t/why-does-inference-with-xnnpack-int8-on-tensorflow-lite-run-slower-with-4-threads-than-with-2-threads-on-a-raspberry-pi-5/116047 **Support:** direct evidence (community report, single user). **Confidence:** medium. Researcher inference: for this tiny CRNN, benchmark 1–4 threads and consider pinning to 2.

## Risks/caveats
- Mel-outside-graph must be mirrored exactly at deployment (FFT windowing, hop, log offset, dtype); the 20/20 parity check is the strongest evidence — keep it as a CI gate.
- UNVERIFIED: whether `Optimize.DEFAULT` dynamic-range quantization (int8 weights, float activations, no representative dataset) avoids the GRU segfault on TF 2.20. Plausible (calibration appears to be the crash point, #87468) but not confirmed in the issues above.
- UNVERIFIED: TFLM reference pipelines (micro_speech) also compute the spectrogram out-of-graph in C++ — consistent with my recollection of the TFLM repo, but not fetched this run.
- Community-only evidence for the Pi 5 XNNPACK thread finding (single forum post).

## Recommended action for this project
1. Keep numpy/precomputed-filterbank preprocessing + float16/float32 LiteRT as the primary deployment (published practice, already parity-verified).
2. Before abandoning int8: (a) try conversion-only with a TF 2.13 env; (b) try `Optimize.DEFAULT` without representative dataset on TF 2.20 and measure; (c) if both fail, document int8 as blocked-by-upstream with the GitHub links — acceptable for this tiny model at 12.3 ms.
3. Sweep XNNPACK thread counts (1/2/4) on the Pi 5 and freeze the best setting in the runtime config.
4. Only invest in ai-edge-torch/onnx2tf if int8 latency ever becomes necessary.

## Open questions
- Does dynamic-range quantization (no calibration) convert the Bidirectional GRU on TF 2.20 without segfault? Cheap to test.
- On Pi 5 Bookworm, does tflite-runtime/LiteRT apply XNNPACK by default for float16 models, and is the GRU fused as BIDIRECTIONAL_SEQUENCE_GRU or executed as a While loop (affects latency)?

## Sources
- Kept: TF issues #62281, #76672, #87468 (upstream segfault + workarounds, primary); official PTQ & float16 docs; openwakeword utils.py + PyPI; librosa.filters.mel docs; Pi 5 XNNPACK thread forum thread.
- Rejected/deprioritized: dev.to / freedom251.com blog posts (SEO/tutorial-grade); slingacademy debugging article (secondary, thin); xnnpack_benchmarks repo (x86 cloud, not Pi-relevant).
