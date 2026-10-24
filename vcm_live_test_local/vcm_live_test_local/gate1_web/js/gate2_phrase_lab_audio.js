const AUDIO_RATE = 48000;
const WINDOW_SECONDS = 5.92;
const WINDOW_SAMPLES = Math.round(AUDIO_RATE * WINDOW_SECONDS);
const CHUNK_SAMPLES = 4096;

function downsample48To16(samples) {
  const output = new Float32Array(Math.floor(samples.length / 3));
  for (let i = 0; i < output.length; i++) {
    output[i] = (samples[i * 3] + samples[i * 3 + 1] + samples[i * 3 + 2]) / 3;
  }
  return output;
}

function mixToMono(buffer) {
  const output = new Float32Array(buffer.length);
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const input = buffer.getChannelData(channel);
    for (let i = 0; i < input.length; i++) output[i] += input[i] / buffer.numberOfChannels;
  }
  return output;
}

function resampleLinear(input, sourceRate, targetRate) {
  if (sourceRate === targetRate) return input;
  const outputLength = Math.max(1, Math.round(input.length * targetRate / sourceRate));
  const output = new Float32Array(outputLength);
  const ratio = sourceRate / targetRate;
  for (let i = 0; i < outputLength; i++) {
    const position = i * ratio;
    const left = Math.min(input.length - 1, Math.floor(position));
    const right = Math.min(input.length - 1, left + 1);
    const weight = position - left;
    output[i] = input[left] * (1 - weight) + input[right] * weight;
  }
  return output;
}

class PcmChunker {
  constructor(socket) {
    this.socket = socket;
    this.buffer = new Float32Array(CHUNK_SAMPLES);
    this.length = 0;
  }

  push(samples) {
    let offset = 0;
    while (offset < samples.length) {
      const count = Math.min(CHUNK_SAMPLES - this.length, samples.length - offset);
      this.buffer.set(samples.subarray(offset, offset + count), this.length);
      this.length += count;
      offset += count;
      if (this.length === CHUNK_SAMPLES) this.flush();
    }
  }

  flush() {
    if (!this.length || this.socket.readyState !== WebSocket.OPEN) {
      this.length = 0;
      return;
    }
    this.socket.send(this.buffer.slice(0, this.length).buffer);
    this.length = 0;
  }
}

export class Gate2PhraseAudio {
  constructor(callbacks) {
    this.callbacks = callbacks;
    this.context = null;
    this.stream = null;
    this.micSource = null;
    this.micConnected = false;
    this.workletNode = null;
    this.muteNode = null;
    this.recordingChunks = null;
    this.recording = false;
    this.sockets = { raw: null, clean: null };
    this.chunkers = { raw: null, clean: null };
    this.activeTest = null;
    this.resolveReady = null;
    this.rejectReady = null;
    this.resolveReset = null;
    this.rejectReset = null;
    this.resolveFlush = null;
    this.rejectFlush = null;
  }

  async ensureAudioGraph(withMicrophone) {
    if (withMicrophone && !this.stream) {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: AUDIO_RATE, echoCancellation: false, noiseSuppression: false, autoGainControl: false }
      });
    }
    if (!this.context) {
      if (!window.AudioContext) throw new Error("Web Audio API is unavailable in this browser");
      this.context = new window.AudioContext({ sampleRate: AUDIO_RATE });
      if (this.context.sampleRate !== AUDIO_RATE) throw new Error("The phrase lab needs a 48 kHz AudioContext; browser provided " + this.context.sampleRate + " Hz");
      await this.context.audioWorklet.addModule("/js/rnnoise-worklet.js?v=phrase-lab-2");
      const ready = new Promise((resolve, reject) => { this.resolveReady = resolve; this.rejectReady = reject; });
      this.workletNode = new AudioWorkletNode(this.context, "rnnoise-dual-capture", {
        numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1], channelCount: 1
      });
      this.workletNode.port.onmessage = (event) => this.onWorkletMessage(event);
      this.muteNode = this.context.createGain();
      this.muteNode.gain.value = 0;
      this.workletNode.connect(this.muteNode);
      this.muteNode.connect(this.context.destination);
      await Promise.race([ready, this.timeout(15000, "RNNoise WASM initialization timed out")]);
    }
    if (withMicrophone && this.stream && !this.micSource) {
      this.micSource = this.context.createMediaStreamSource(this.stream);
      this.micSource.connect(this.workletNode);
      this.micConnected = true;
    }
    await this.context.resume();
  }

  timeout(ms, message) {
    return new Promise((_, reject) => window.setTimeout(() => reject(new Error(message)), ms));
  }

  onWorkletMessage(event) {
    const data = event.data || {};
    if (data.type === "ready") {
      if (this.resolveReady) this.resolveReady();
      this.resolveReady = null;
      this.rejectReady = null;
      return;
    }
    if (data.type === "reset-ready") {
      if (this.resolveReset) this.resolveReset();
      this.resolveReset = null;
      this.rejectReset = null;
      return;
    }
    if (data.type === "flushed") {
      if (this.resolveFlush) this.resolveFlush();
      this.resolveFlush = null;
      this.rejectFlush = null;
      return;
    }
    if (data.type === "error") {
      const error = new Error(data.message || "RNNoise worklet error");
      if (this.rejectReady) this.rejectReady(error);
      if (this.rejectReset) this.rejectReset(error);
      this.callbacks.onStatus(error.message, true);
      return;
    }
    if (data.type !== "audio") return;
    const raw = new Float32Array(data.raw);
    const clean = new Float32Array(data.clean);
    if (this.recording && this.recordingChunks) this.recordingChunks.push(raw.slice());
    if (this.activeTest) {
      this.chunkers.raw.push(downsample48To16(raw));
      this.chunkers.clean.push(downsample48To16(clean));
    }
    if (this.callbacks.onLevels) this.callbacks.onLevels(this.rms(raw), this.rms(clean));
  }

  rms(samples) {
    if (!samples.length) return 0;
    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    return Math.sqrt(sum / samples.length);
  }

  async resetRnnoise() {
    const reset = new Promise((resolve, reject) => { this.resolveReset = resolve; this.rejectReset = reject; });
    this.workletNode.port.postMessage({ type: "reset" });
    await Promise.race([reset, this.timeout(5000, "RNNoise reset timed out")]);
  }

  async flushWorklet() {
    if (!this.workletNode) return;
    const flushed = new Promise((resolve, reject) => { this.resolveFlush = resolve; this.rejectFlush = reject; });
    this.workletNode.port.postMessage({ type: "flush" });
    await Promise.race([flushed, this.timeout(5000, "RNNoise audio flush timed out")]);
  }

  async startRecording() {
    if (this.recording) throw new Error("A recording is already in progress");
    await this.ensureAudioGraph(true);
    await this.resetRnnoise();
    this.recordingChunks = [];
    this.recording = true;
    return { startedAt: new Date().toISOString() };
  }

  async stopRecording() {
    if (!this.recording) throw new Error("No recording is in progress");
    try {
      await this.flushWorklet();
    } finally {
      this.recording = false;
    }
    const chunks = this.recordingChunks || [];
    this.recordingChunks = null;
    const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
    const samples = new Float32Array(length);
    let offset = 0;
    chunks.forEach((chunk) => { samples.set(chunk, offset); offset += chunk.length; });
    if (samples.length < AUDIO_RATE / 4) throw new Error("Recording was too short; record at least 0.25 seconds");
    return { samples, duration: samples.length / AUDIO_RATE };
  }

  async openBranch(name, intervalS) {
    return new Promise((resolve, reject) => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(protocol + "//" + window.location.host + "/ws");
      this.sockets[name] = socket;
      socket.binaryType = "arraybuffer";
      const timer = window.setTimeout(() => reject(new Error(name + " Gate 2 connection timed out")), 10000);
      socket.onopen = () => {
        window.clearTimeout(timer);
        socket.send(JSON.stringify({ type: "mode", mode: "gate2", interval_s: intervalS }));
        this.chunkers[name] = new PcmChunker(socket);
        resolve(socket);
      };
      socket.onerror = () => {
        window.clearTimeout(timer);
        reject(new Error("Could not open the " + name + " Gate 2 connection"));
      };
      socket.onmessage = (event) => {
        if (typeof event.data !== "string" || !this.activeTest) return;
        let message;
        try { message = JSON.parse(event.data); } catch (_) { return; }
        if (message.type !== "probs2") return;
        this.activeTest.results[name] = message;
        if (this.callbacks.onInference) this.callbacks.onInference(name, message);
        if (this.activeTest.results.raw && this.activeTest.results.clean && this.activeTest.resolve) {
          this.activeTest.resolve(this.activeTest.results);
        }
      };
    });
  }

  decodeClip(recording) {
    return recording.wavBlob.arrayBuffer().then((buffer) => this.context.decodeAudioData(buffer));
  }

  alignedWindow(audioBuffer) {
    const mono = mixToMono(audioBuffer);
    const at48k = resampleLinear(mono, audioBuffer.sampleRate, AUDIO_RATE);
    const samples = new Float32Array(WINDOW_SAMPLES);
    const length = Math.min(at48k.length, WINDOW_SAMPLES);
    const sourceStart = Math.floor((at48k.length - length) / 2);
    const targetStart = Math.floor((WINDOW_SAMPLES - length) / 2);
    samples.set(at48k.subarray(sourceStart, sourceStart + length), targetStart);
    const buffer = this.context.createBuffer(1, WINDOW_SAMPLES, AUDIO_RATE);
    buffer.copyToChannel(samples, 0);
    return buffer;
  }

  async testRecording(recording, intervalS) {
    if (this.activeTest) throw new Error("A Gate 2 replay is already running");
    await this.ensureAudioGraph(false);
    const reconnectMic = Boolean(this.micSource && this.micConnected);
    if (reconnectMic) { this.micSource.disconnect(); this.micConnected = false; }
    let source = null;
    try {
      await this.resetRnnoise();
      this.activeTest = { recording, results: {}, resolve: null };
      const resultsPromise = new Promise((resolve) => { this.activeTest.resolve = resolve; });
      await Promise.all([this.openBranch("raw", intervalS), this.openBranch("clean", intervalS)]);
      const audioBuffer = await this.decodeClip(recording);
      const playBuffer = this.alignedWindow(audioBuffer);
      source = this.context.createBufferSource();
      source.buffer = playBuffer;
      source.connect(this.workletNode);
      const ended = new Promise((resolve) => { source.onended = resolve; });
      source.start();
      this.callbacks.onStatus("Testing " + recording.fileName + " through both Gate 2 paths…", false);
      await ended;
      await this.flushWorklet();
      this.chunkers.raw.flush();
      this.chunkers.clean.flush();
      return await Promise.race([resultsPromise, this.timeout(20000, "Timed out waiting for both Gate 2 results")]);
    } finally {
      if (source) { try { source.disconnect(); } catch {} }
      this.activeTest = null;
      Object.keys(this.sockets).forEach((name) => {
        if (this.chunkers[name]) this.chunkers[name].flush();
        this.chunkers[name] = null;
        if (this.sockets[name]) { try { this.sockets[name].close(); } catch {} }
        this.sockets[name] = null;
      });
      if (reconnectMic && this.micSource) {
        this.micSource.connect(this.workletNode);
        this.micConnected = true;
      }
    }
  }

  async close() {
    this.recording = false;
    this.recordingChunks = null;
    this.activeTest = null;
    Object.keys(this.sockets).forEach((name) => { if (this.sockets[name]) this.sockets[name].close(); });
    if (this.micSource) { try { this.micSource.disconnect(); } catch {} this.micSource = null; }
    if (this.workletNode) {
      try { this.workletNode.port.postMessage({ type: "dispose" }); this.workletNode.disconnect(); } catch {}
      this.workletNode = null;
    }
    if (this.muteNode) { try { this.muteNode.disconnect(); } catch {} this.muteNode = null; }
    if (this.stream) { this.stream.getTracks().forEach((track) => track.stop()); this.stream = null; }
    if (this.context) { try { await this.context.close(); } catch {} this.context = null; }
  }
}
