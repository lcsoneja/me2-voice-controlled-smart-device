# Consolidated verdict

**Keep TFLite/LiteRT + XNNPACK as lead baseline, not proven “best.”** No brief provides a Pi-5 CRNN benchmark or profile of this exact 74/148-frame graph. XNNPACK lists Conv2D, MaxPool2D and FullyConnected, but no fused GRU; actual loop-body delegation is unknown. Full-int8 crashes are reported for particular models on TF 2.14–2.18; TF 2.13 worked in one report. Neither proves universal failure or current-release status. Keep float32 baseline; trial dynamic-range PTQ and float16 weights. On CPU, float16 weights expand to float32, so expect mainly size reduction.

## Per-brief audit table

| Claim | Verdict | Note |
|---|---|---|
| Luna 1: GRU converts as WHILE/subgraph | OK | #87468/#97941 show examples; not an exact BiGRU guarantee. |
| Luna 2: XNNPACK lacks GRU; recurrent ops fall back | OVERREACH | [README](https://github.com/tensorflow/tensorflow/blob/master/tensorflow/lite/delegates/xnnpack/README.md) lacks GRU and documents fallback; exact WHILE partition/“conv only” is unprofiled. |
| Luna 3: int8 GRU conversion is risky | OK | #62281/#76672/#87468 show model/version-specific failures, not universal failure. |
| Luna 4: quantization does not ensure XNNPACK speedup | OVERREACH | True for unsupported ops; dynamic-range evidence conflicts: README says unsupported; [2024 announcement](https://blog.tensorflow.org/2024/04/faster-dynamically-quantized-inference-with-xnnpack.html) supports FC/Conv2D from TF 2.17, not GRU. |
| Luna 5: ONNX/ORT is a GRU challenger | OK | [ONNX](https://onnx.ai/onnx/operators/onnx__GRU.html)/[ORT](https://onnxruntime.ai/docs/reference/operators/OperatorKernels.html) list float GRU; export semantics and Pi speed untested. |
| GLM 1: out-of-graph features are standard | OVERREACH | openWakeWord is one precedent, not evidence of a general standard. |
| GLM 2: librosa mel matrix can be precomputed | OK | Fixed matrix supported; parity needs matching FFT/window/log/dtype. Claimed 20/20 project parity not independently inspected. |
| GLM 3: TF 2.14+ segfault; 2.13 works | OK | #62281 reproduction; it closed stale, not as a general fix. |
| GLM 4: persists through TF 2.16–2.18 | OK | #76672/#87468 report those versions. Newer status unverified; tf-keras is not a universal fix. |
| GLM 5: float works; int8 crash is calibration | OK | #87468 reports float conversion/inference succeeds; representative-data calibration crashes for its model. |
| GLM 6: TF 2.13, AI-Edge-Torch, onnx2tf are workarounds | OVERREACH | One version result; AI-Edge-Torch example is PyTorch, not drop-in Keras; onnx2tf citation is secondary and parity-unverified. |
| GLM 7: float16 is official fallback | OVERREACH | [Guide](https://developers.google.com/edge/litert/conversion/tensorflow/quantization/post_training_float16_quant) supports it; CPU expands weights to float32, with no speed promise. |
| GLM 8: 4 threads slower than 2 on Pi 5 | UNVERIFIED | Single-user forum report, not this model. |
| Qwen 1: Pi-5 benchmark favors TFLite | OVERREACH | [Benchmark](https://github.com/jaweed3/edge-burn-benchmark): MobileNetV2 TFLite 22.19/10.68 vs ORT 45.35/20.34 ms (~2× vs ORT; 4–5× vs Burn), not CRNN. Self-published with harness/results. |
| Qwen 2: wake-word standard / model count | OVERREACH | openWakeWord supports TFLite and ONNX; cited 15–20-model page says Pi 3, not Pi 5. |
| Qwen 3: Porcupine <3.5% CPU proves headroom | UNVERIFIED | Vendor claim not independently confirmed; cannot predict CRNN load. |
| Qwen 4: micro_speech validates TFLite performance | OVERREACH | Official README confirms <20-kB, 2-word TFLM model; different CNN/runtime, no Pi-5 CRNN result. |
| Qwen 5: ExecuTorch works on Pi 5 | OK | Community Gemma demo runs there; it is an LLM, not CRNN evidence. |
| Qwen 6: GRU not accelerated; fallback | OVERREACH | No fused GRU listed; exact decomposition/delegation unknown. |
| Qwen 7: #97941 supports int8-crash generalization | OVERREACH | TF 2.12 stateful/unroll/TFLM discussion, not int8 calibration crash; closed stale. |
| Qwen 8: microWakeWord is wrong for Pi | UNVERIFIED | Cited site unavailable; peripheral. |
| Qwen 9: 540-MB RSS is Python overhead | OVERREACH | Benchmark reports Python RSS; attribution/C-runtime comparison not demonstrated there. |

## Contradictions

Official XNNPACK sources conflict on dynamic-range support: README says unsupported; 2024 announcement documents FC/Conv2D from TF 2.17. Treat as operator/version-specific and test the actual package. All briefs infer “conv-only” benefit from no fused GRU op, but no exact graph profile verifies this. #87468 closure does not prove a fix; reports through TF 2.18 show failures, newer status unverified.

## Consolidated recommendations (prioritized; confidence)

1. **High:** Benchmark exact model on Pi 5 at both lengths: float32 XNNPACK on/off, 1/2/4 threads; end-to-end features+inference p50/p95, cold start, RSS, sustained temperature and accuracy/parity. Record versions, delegated nodes and per-op time.
2. **High:** Keep float32 baseline. Trial dynamic-range PTQ (eligible FC/Conv only) and float16 weights (mainly size on CPU). Compare parity/accuracy, latency and size. Test full-int8 with pinned/current converter before calling it blocked.
3. **Medium-high:** Try ORT only if equivalent ONNX export is straightforward or TFLite misses targets; compare same graph/inputs. No migration based on MobileNet numbers.
4. **Medium:** No ExecuTorch/NCNN action now; no exact-model Pi-5 evidence justifies conversion/maintenance cost.

Verify final offline packaging has no runtime download/network dependency. No actual Pi 5 result or exact graph profile was independently verified.
