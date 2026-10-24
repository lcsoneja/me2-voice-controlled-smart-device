const FLUSH_AT = 4096;

class RawCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(FLUSH_AT);
    this.length = 0;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input || !input.length) return true;
    let offset = 0;
    while (offset < input.length) {
      const count = Math.min(FLUSH_AT - this.length, input.length - offset);
      this.buffer.set(input.subarray(offset, offset + count), this.length);
      this.length += count;
      offset += count;
      if (this.length === FLUSH_AT) {
        const out = this.buffer.slice(0, this.length);
        this.port.postMessage({ type: "audio", samples: out.buffer }, [out.buffer]);
        this.buffer = new Float32Array(FLUSH_AT);
        this.length = 0;
      }
    }
    return true;
  }
}

registerProcessor("raw-capture", RawCaptureProcessor);
