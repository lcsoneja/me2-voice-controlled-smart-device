import createRNNWasmModuleSync from "/vendor/rnnoise/rnnoise-sync.js";

const FRAME_SIZE = 480;
const FRAMES_PER_BATCH = 4;
const BATCH_SIZE = FRAME_SIZE * FRAMES_PER_BATCH;

class RnnoiseDualCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.pending = new Float32Array(FRAME_SIZE * 2);
    this.pendingLength = 0;
    this.rawBatch = new Float32Array(BATCH_SIZE);
    this.cleanBatch = new Float32Array(BATCH_SIZE);
    this.batchFrames = 0;
    this.module = null;
    this.state = 0;
    this.inputPtr = 0;
    this.outputPtr = 0;
    this.disposed = false;
    this.port.onmessage = (event) => {
      if (!event.data) return;
      if (event.data.type === "dispose") this.dispose();
      if (event.data.type === "reset") {
        const ready = this.resetState();
        this.port.postMessage(ready ? { type: "reset-ready" } : { type: "error", message: "RNNoise state reset failed" });
      }
      if (event.data.type === "flush") {
        this.flushBatch();
        this.port.postMessage({ type: "flushed" });
      }
    };
    this.initialize();
  }

  async initialize() {
    try {
      const created = createRNNWasmModuleSync();
      this.module = await Promise.resolve(created && created.ready ? created.ready : created);
      this.module._rnnoise_init();
      this.state = this.module._rnnoise_create(0);
      if (!this.state) throw new Error("rnnoise_create returned a null state");
      this.inputPtr = this.module._malloc(FRAME_SIZE * Float32Array.BYTES_PER_ELEMENT);
      this.outputPtr = this.module._malloc(FRAME_SIZE * Float32Array.BYTES_PER_ELEMENT);
      if (!this.inputPtr || !this.outputPtr) throw new Error("RNNoise WASM memory allocation failed");
      this.port.postMessage({ type: "ready", sampleRate: sampleRate, frameSize: FRAME_SIZE });
    } catch (error) {
      this.port.postMessage({ type: "error", message: error && error.message ? error.message : String(error) });
    }
  }

  process(inputs, outputs) {
    const input = inputs[0] && inputs[0][0];
    const output = outputs[0] && outputs[0][0];
    if (output) output.fill(0);
    if (this.disposed || !input || !this.state) return true;
    if (this.pendingLength + input.length > this.pending.length) return true;
    this.pending.set(input, this.pendingLength);
    this.pendingLength += input.length;
    while (this.pendingLength >= FRAME_SIZE) {
      this.processFrame();
      this.pending.copyWithin(0, FRAME_SIZE, this.pendingLength);
      this.pendingLength -= FRAME_SIZE;
    }
    return true;
  }

  processFrame() {
    const inputIndex = this.inputPtr >>> 2;
    const outputIndex = this.outputPtr >>> 2;
    const frame = this.pending.subarray(0, FRAME_SIZE);
    this.module.HEAPF32.set(frame, inputIndex);
    this.module._rnnoise_process_frame(this.state, this.outputPtr, this.inputPtr);
    const offset = this.batchFrames * FRAME_SIZE;
    this.rawBatch.set(frame, offset);
    this.cleanBatch.set(this.module.HEAPF32.subarray(outputIndex, outputIndex + FRAME_SIZE), offset);
    this.batchFrames += 1;
    if (this.batchFrames === FRAMES_PER_BATCH) this.flushBatch();
  }

  flushBatch() {
    if (!this.batchFrames) return;
    const usedSamples = this.batchFrames * FRAME_SIZE;
    const raw = this.rawBatch.slice(0, usedSamples).buffer;
    const clean = this.cleanBatch.slice(0, usedSamples).buffer;
    this.port.postMessage({ type: "audio", raw: raw, clean: clean }, [raw, clean]);
    this.rawBatch = new Float32Array(BATCH_SIZE);
    this.cleanBatch = new Float32Array(BATCH_SIZE);
    this.batchFrames = 0;
  }

  resetState() {
    if (!this.module) return false;
    if (this.state) this.module._rnnoise_destroy(this.state);
    this.state = this.module._rnnoise_create(0);
    this.pending.fill(0);
    this.pendingLength = 0;
    this.rawBatch = new Float32Array(BATCH_SIZE);
    this.cleanBatch = new Float32Array(BATCH_SIZE);
    this.batchFrames = 0;
    return Boolean(this.state);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    if (this.module) {
      if (this.state) this.module._rnnoise_destroy(this.state);
      if (this.inputPtr) this.module._free(this.inputPtr);
      if (this.outputPtr) this.module._free(this.outputPtr);
    }
    this.state = 0;
    this.inputPtr = 0;
    this.outputPtr = 0;
  }
}

registerProcessor("rnnoise-dual-capture", RnnoiseDualCaptureProcessor);
