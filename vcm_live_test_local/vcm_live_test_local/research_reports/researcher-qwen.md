# Research: TFLite+XNNPACK vs alternatives for CRNN wake-word/command models on Raspberry Pi 5

*Researcher brief — alternatives benchmark. All claims checked 2026-10-04 via web search + source fetch. Runtime note: the sandboxed writer could not reach the designated output path (permission policy blocks writes outside the project working directory); full brief returned below for persistence, per runtime instructions.*

## Verdict
For this project (small CRNN, float16/float32 TFLite, numpy preprocessing, fully offline), **TFLite (LiteRT) + XNNPACK remains the best deployment path on Pi 5** — it is the most benchmarked, best-supported runtime on ARM64 Linux, and a 2025/2026 Pi 5 study found TFLite 2–4× faster than ONNX Runtime or the Rust Burn runtime at the same precision. The main caveat: XNNPACK does **not** accelerate the GRU ops in your model, so your speedup comes from the 2D-conv + pooling path; measure, don't assume. The wake-word community largely standardizes on TFLite/ONNX for Pi-class devices, so you are aligned with practice — but int8 is the real gap vs community deployments.

## Key findings
1. **Pi 5, TFLite vs ONNX Runtime vs Burn (MobileNetV2, Cortex-A76):** TFLite 22.2 ms @1 thread / 10.7 ms @4 threads; ONNX Runtime 45.4 ms / 20.3 ms; Burn (tract-onnx) 101 ms, no thread scaling. TFLite ~2× faster single-thread, ~2× faster 4-thread than ORT; all stable under 59°C passive. Source: https://github.com/jaweed3/edge-burn-benchmark
2. **openWakeWord (community standard for Pi wake-word):** runs on Linux via onnxruntime + tflite-runtime; 80 ms frames; third-party Pi 5 docs claim 15–20 wake-word models on a single Pi core; supported Linux inference frameworks are TFLite or ONNX. Sources: https://github.com/CarbonRaven/tele-ai/blob/main/documentation/raspberry-pi-5-openwakeword.md , https://github.com/dscripka/openWakeWord
3. **Porcupine (commercial baseline):** advertises **<3.5% CPU on Raspberry Pi**, 100% offline, Arm Cortex-M through Pi 5 — evidence that Pi 5 CPU headroom for a small int8 KWS model is very large. Source: https://picovoice.ai/products/voice/wake-word/
4. **micro_speech (TFLite Micro, 5-word CNN):** under 20 kB, designed for Cortex-M class; runs on Pi 5 with orders of magnitude to spare — confirms TFLite is the community format for tiny CRNN-style audio models. Source: https://github.com/tensorflow/tflite-micro/blob/main/tensorflow/lite/micro/examples/micro_speech/README.md
5. **ExecuTorch (PyTorch stack) on Pi 5:** works (XNNPACK backend documented in a Gemma-4 Pi 5 deployment with ExecuTorch 1.2.0), but that deployment reported Pi 5 far slower than optimized llama.cpp; ExecuTorch's own ARM CPU/NPU blog states performance is backend-dependent. No published Pi 5 benchmark for a small CRNN exists. Sources: https://github.com/bamb00boy/Gemma4_executorch_deployment , https://pytorch.org/blog/efficient-edge-ai-on-arm-cpus-and-npus/
6. **XNNPACK operator coverage:** official README: work-in-progress, limited operator set, unsupported operators fall back to default implementations. Bidirectional GRU has no XNNPACK kernel in TFLite — expect fallback to reference GRU, i.e., XNNPACK helps the conv layers only. Source: https://android.googlesource.com/platform/external/tensorflow/+/HEAD/tensorflow/lite/delegates/xnnpack/README.md
7. **GRU-specific conversion trouble is real:** TensorFlow issue #97941 documents GRU-to-TFLite conversion problems (stateful/unrolled interaction); the project's int8-segfault-on-Bidirectional-GRU is consistent with this known weak spot. Source: https://github.com/tensorflow/tensorflow/issues/97941
8. **microWakeWord:** ESP32-S3/ESPHome-focused; official guidance for "Raspberry Pi or PC" is to use full openWakeWord models instead — the wrong tool for Pi 5. Source: https://microwakeword.com/
9. **TFLite memory:** 540 MB RSS in the Pi 5 benchmark, dominated by Python overhead; the C runtime (benchmark_model) is far smaller — relevant only if the target Pi has 1–2 GB. Source: https://github.com/jaweed3/edge-burn-benchmark

## Risks / caveats
- **GRU is likely the critical path, not the convs.** Laptop v2 total was 12.3 ms; if the bidirectional GRU dominates, Pi 5 (A76, ~1.8 GHz) may land in the tens-to-~100 ms regime (researcher inference, not measured). Benchmark on-device before committing.
- **float16 on Cortex-A76:** full-speed FP16 arithmetic is limited on A76; float16 may buy memory, not speed, or even lose vs float32. Verify on-device.
- **int8 still blocked:** every community KWS deployment (openWakeWord, Porcupine, micro_speech) ships int8, which is what makes them <5% CPU. Options to close the gap: post-training quantization on the already-converted float model, a newer TF/TFLite converter, or per-layer int8 of the convs only.
- Finding #1 is MobileNetV2 (no RNN); the direction (TFLite ≥ ONNX on Pi 5) is well supported, but magnitude for a CRNN is extrapolation.

## Recommended action for this project
1. Keep **TFLite (LiteRT) + XNNPACK** as the primary path — aligned with community practice and the best published Pi 5 numbers.
2. Run `benchmark_model` on the Pi 5 for v1 and v2 (float16 and float32) and inspect op-level times to confirm where the GRU sits; treat the 12.3 ms laptop number as a lower-bound sanity check.
3. Pursue int8 via post-training quantization (or a newer converter build) as a parallel workstream — this is the gap vs openWakeWord/Porcupine deployments.
4. Treat ONNX Runtime as fallback, not alternative: slower in the only published Pi 5 head-to-head.
5. Skip ExecuTorch and Burn for now (no CRNN-class evidence, larger conversion surface).

## Open questions
- Measured per-op latency of Bidirectional-GRU(64) on Pi 5, float16 vs float32 (no public number found — UNVERIFIED for this exact model).
- Whether the newest LiteRT converter (2025–2026 releases) still segfaults on Bidirectional GRU int8 quantization — UNVERIFIED.
- XNNPACK 1→4-thread scaling for this specific op mix (MobileNetV2 result shows ~2×, not a guarantee).
- Whether float16 CRNN inference on A76 beats float32 — UNVERIFIED.

## Sources
- Kept: jaweed3/edge-burn-benchmark (only head-to-head TFLite/ONNX/Burn on Pi 5) — https://github.com/jaweed3/edge-burn-benchmark
- Kept: openWakeWord Pi 5 doc — https://github.com/CarbonRaven/tele-ai/blob/main/documentation/raspberry-pi-5-openwakeword.md ; repo — https://github.com/dscripka/openWakeWord
- Kept: Picovoice Porcupine (Pi CPU claim) — https://picovoice.ai/products/voice/wake-word/
- Kept: TFLM micro_speech (footprint baseline) — https://github.com/tensorflow/tflite-micro/blob/main/tensorflow/lite/micro/examples/micro_speech/README.md
- Kept: ExecuTorch Pi 5 case study — https://github.com/bamb00boy/Gemma4_executorch_deployment ; ARM CPU/NPU blog — https://pytorch.org/blog/efficient-edge-ai-on-arm-cpus-and-npus/
- Kept: XNNPACK delegate README (op-coverage caveat) — https://android.googlesource.com/platform/external/tensorflow/+/HEAD/tensorflow/lite/delegates/xnnpack/README.md
- Kept: TF issue #97941 (GRU conversion) — https://github.com/tensorflow/tensorflow/issues/97941
- Kept: microWakeWord official guidance — https://microwakeword.com/
- Rejected: bigiron.cc openWakeWord-vs-microWakeWord guide (SEO blog, no benchmarks); deepwiki summaries (secondary); tech.raatools.net (hobbyist, no Pi 5 CRNN data).