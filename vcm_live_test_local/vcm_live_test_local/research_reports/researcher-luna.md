# Research: TFLite/LiteRT runtime coverage for Gate-1 CRNN on Raspberry Pi 5

## Verdict
Keep TFLite/LiteRT as the leading deployment candidate: the project already has a fast float32 TFLite path, and the runtime supports offline CPU inference. But TFLite plus XNNPACK is not necessarily the best path for the whole Conv2D–BiGRU graph: XNNPACK has no documented GRU operator, so recurrent work is likely handled by TFLite’s builtin CPU kernels. Compare on the Pi before calling it best.

## Key findings
1. **TFLite can represent a GRU without a fused GRU op.** A TensorFlow converter issue describes a float TFLite GRU model as a `WHILE` op plus a subgraph implementing the cell. This supports conversion by decomposition, not a guarantee that every Keras BiGRU variant converts identically. Inspect this model’s FlatBuffer op list and run it on target. [TF issue #87468](https://github.com/tensorflow/tensorflow/issues/87468) **Support: direct evidence; confidence: high.**

2. **XNNPACK does not document GRU/BiGRU support.** Its README enumerates supported operators but has no GRU entry; it describes delegation of supported graph portions and fallback to the default backend. **Inference:** convolutional segments may accelerate while the recurrent part remains on builtin CPU kernels. Don’t attribute whole-model speed to XNNPACK without profiling. [XNNPACK operator and delegation README](https://github.com/tensorflow/tensorflow/blob/master/tensorflow/lite/delegates/xnnpack/README.md) **Support: direct list plus interpretation; confidence: medium-high.**

3. **Full-int8 conversion is a real risk; fp16 and dynamic-range are possible fallbacks.** An issue reports GRU full-integer conversion segfaulting during calibration in TF 2.18; a comment reports float16 and dynamic-range quantization worked for that case. A separate report describes GRU conversion failures in TF 2.14, 2.15, and nightly. These reports are model/version-specific, not proof of a universal current failure or fix. [#87468](https://github.com/tensorflow/tensorflow/issues/87468) · [#62281](https://github.com/tensorflow/tensorflow/issues/62281) **Support: direct reports; confidence: high for risk, medium for workarounds.**

4. **Quantization does not guarantee XNNPACK acceleration.** XNNPACK documents FP16 inference subject to supported operators and hardware/metadata conditions; quantized XNNPACK is opt-in and its listed quantized operators do not include GRU. Its README explicitly says dynamic-range quantization is unsupported in XNNPACK. Thus, reduced model size does not imply a GRU speedup. [XNNPACK README](https://github.com/tensorflow/tensorflow/blob/master/tensorflow/lite/delegates/xnnpack/README.md) · [LiteRT post-training quantization](https://developers.google.com/edge/litert/conversion/tensorflow/quantization/post_training_quantization) **Support: direct evidence; confidence: high.**

5. **Alternatives:** ONNX defines a standard GRU operator, and ONNX Runtime’s current CPU kernel table lists GRU for float/double. This makes ORT a credible challenger if export preserves model semantics, but does not show that it is faster on Pi 5. [ONNX GRU](https://onnx.ai/onnx/operators/onnx__GRU.html) · [ORT CPU kernels](https://raw.githubusercontent.com/microsoft/onnxruntime/main/docs/OperatorKernels.md) A TensorFlow issue also gives an AI Edge Torch example exporting a PyTorch GRU to TFLite; this is an export route, not evidence of a better Pi runtime. [TF issue #62281](https://github.com/tensorflow/tensorflow/issues/62281) **NCNN and full TensorFlow:** no primary-source Pi 5 benchmark or exact BiGRU coverage proving an advantage was verified.

## Risks/caveats
- Pi 5 performance is unknown from the supplied x86 measurements; confirm delegate partition and fallback with target profiling.
- Converter reports are version/model-specific; closure or stale status does not establish a general fix.
- Exact `reset_after=True` bidirectional semantics and Pi 5 package behavior were not independently tested.

## Recommended action for this project
Keep float32 TFLite as the baseline. On Pi 5, benchmark end-to-end preprocessing and inference with XNNPACK enabled and disabled, then test a float16-weight variant; check output parity/accuracy and inspect delegated nodes. Try int8 only in an isolated conversion test and do not replace the baseline without successful conversion and validation. Test ONNX Runtime only with a semantically equivalent export, comparing latency, memory, startup, and packaging on the Pi. Don’t migrate to NCNN, ExecuTorch, or full TensorFlow without measured benefit.

## Open questions
- Which operations in this exact export delegate to XNNPACK on Pi 5?
- Does float16 reduce memory or latency for this BiGRU graph on Pi OS/A76 without unacceptable accuracy loss?
- Can the current converter handle this exact graph as fully int8?
- Does ONNX export preserve `reset_after=True` and bidirectional semantics, and does ORT win on target measurements?