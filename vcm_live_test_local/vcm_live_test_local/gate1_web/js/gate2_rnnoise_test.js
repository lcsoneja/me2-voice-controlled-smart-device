const CHUNK_SAMPLES = 4096;
const IS_2S_VARIANT = window.location.pathname.endsWith("_2s.html");
const INFERENCE_INTERVAL_S = IS_2S_VARIANT ? 2 : 1;
const INFERENCE_INTERVAL_LABEL = INFERENCE_INTERVAL_S === 1 ? "1 second" : "2 seconds";
const GATE2_MODE = JSON.stringify({ type: "mode", mode: "gate2", interval_s: INFERENCE_INTERVAL_S });
const LABELS = ["PLAY_MUSIC", "WEATHER", "TIME", "LIGHT_ON", "LIGHT_OFF", "PAUSE", "STOP", "NEXT", "VOLUME_UP", "VOLUME_DOWN", "CALL", "MESSAGE", "LIST_REMINDERS", "TIMER", "ALARM", "TEMPERATURE", "BRIGHTNESS", "COLOR", "CREATE_REMINDER"];
const ui = {
  start: document.getElementById("start"), stop: document.getElementById("stop"), status: document.getElementById("status"), expected: document.getElementById("expected"),
  cadence: document.getElementById("cadence-label"), variantLink: document.getElementById("interval-variant")
};
ui.cadence.textContent = INFERENCE_INTERVAL_LABEL;
ui.variantLink.href = IS_2S_VARIANT ? "/gate2_rnnoise_test.html" : "/gate2_rnnoise_test_2s.html";
ui.variantLink.textContent = IS_2S_VARIANT ? "Use 1-second updates" : "Try 2-second updates";
const branches = {
  raw: { top: document.getElementById("raw-top"), conf: document.getElementById("raw-conf"), match: document.getElementById("raw-match"), rms: document.getElementById("raw-rms"), connection: document.getElementById("raw-connection"), bars: document.getElementById("raw-bars"), socket: null, chunker: null },
  clean: { top: document.getElementById("clean-top"), conf: document.getElementById("clean-conf"), match: document.getElementById("clean-match"), rms: document.getElementById("clean-rms"), connection: document.getElementById("clean-connection"), bars: document.getElementById("clean-bars"), socket: null, chunker: null }
};
let stream = null;
let audioContext = null;
let sourceNode = null;
let workletNode = null;
let muteNode = null;
let running = false;

function setStatus(text, isError) {
  ui.status.textContent = text;
  ui.status.classList.toggle("error", Boolean(isError));
}

function setConnection(name, text) {
  branches[name].connection.textContent = text;
}

function connectBranch(name) {
  return new Promise(function (resolve, reject) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(protocol + "//" + window.location.host + "/ws");
    const branch = branches[name];
    branch.socket = socket;
    socket.binaryType = "arraybuffer";
    const timer = window.setTimeout(function () {
      if (socket.readyState !== WebSocket.OPEN) reject(new Error(name + " Gate 2 connection timed out"));
    }, 10000);
    socket.onopen = function () {
      window.clearTimeout(timer);
      socket.send(GATE2_MODE);
      setConnection(name, "connected");
      resolve(socket);
    };
    socket.onmessage = function (event) {
      if (typeof event.data !== "string") return;
      let message;
      try { message = JSON.parse(event.data); } catch (_) { return; }
      if (message.type === "status") {
        setConnection(name, "filling window");
        return;
      }
      if (message.type === "probs2") renderInference(name, message);
    };
    socket.onclose = function () { setConnection(name, running ? "disconnected" : "stopped"); };
    socket.onerror = function () {
      window.clearTimeout(timer);
      reject(new Error("Could not open the " + name + " Gate 2 WebSocket"));
      setConnection(name, "error");
    };
  });
}

function makeBars(name) {
  const holder = branches[name].bars;
  holder.replaceChildren();
  LABELS.forEach(function (label) {
    const row = document.createElement("div"); row.className = "barrow";
    const text = document.createElement("span"); text.className = "barlabel"; text.textContent = label;
    const track = document.createElement("div"); track.className = "track";
    const fill = document.createElement("div"); fill.className = "fill"; fill.dataset.intent = label; track.appendChild(fill);
    const value = document.createElement("span"); value.className = "barval"; value.textContent = "—"; value.dataset.intent = label;
    row.append(text, track, value); holder.appendChild(row);
  });
}

function renderInference(name, message) {
  const branch = branches[name];
  const probabilities = message.probs || {};
  branch.top.textContent = message.top || "—";
  branch.conf.textContent = Number.isFinite(message.conf) ? Number(message.conf).toFixed(3) : "—";
  branch.bars.querySelectorAll(".fill").forEach(function (fill) {
    const value = Number(probabilities[fill.dataset.intent] || 0);
    fill.style.width = Math.max(0, Math.min(100, value * 100)) + "%";
  });
  branch.bars.querySelectorAll(".barval").forEach(function (valueEl) {
    const value = Number(probabilities[valueEl.dataset.intent] || 0);
    valueEl.textContent = value.toFixed(3);
  });
  renderExpected(name);
}

function renderExpected(name) {
  const expected = ui.expected.value;
  const branch = branches[name];
  if (!expected) { branch.match.textContent = "Choose an expected command above to compare."; branch.match.className = "expect-result"; return; }
  const actual = branch.top.textContent;
  if (actual === "Waiting for audio" || actual === "—") { branch.match.textContent = "Waiting for an inference…"; branch.match.className = "expect-result"; return; }
  const correct = actual === expected;
  branch.match.textContent = (correct ? "MATCH" : "MISMATCH") + " · expected " + expected + ", got " + actual;
  branch.match.className = "expect-result " + (correct ? "good" : "bad");
}

function rms(samples) {
  if (!samples.length) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / samples.length);
}

function downsample48to16(samples) {
  const output = new Float32Array(Math.floor(samples.length / 3));
  for (let i = 0; i < output.length; i++) output[i] = (samples[i * 3] + samples[i * 3 + 1] + samples[i * 3 + 2]) / 3;
  return output;
}

class PcmChunker {
  constructor(socket) { this.socket = socket; this.buffer = new Float32Array(CHUNK_SAMPLES); this.length = 0; }
  push(samples) {
    let offset = 0;
    while (offset < samples.length) {
      const take = Math.min(CHUNK_SAMPLES - this.length, samples.length - offset);
      this.buffer.set(samples.subarray(offset, offset + take), this.length);
      this.length += take; offset += take;
      if (this.length === CHUNK_SAMPLES) this.flush();
    }
  }
  flush() {
    if (!this.length || !this.socket || this.socket.readyState !== WebSocket.OPEN) { this.length = 0; return; }
    this.socket.send(this.buffer.slice(0, this.length).buffer); this.length = 0;
  }
}

let readyResolve = null;
let readyReject = null;
let readyTimer = null;

function handleWorkletMessage(event) {
  const data = event.data || {};
  if (data.type === "ready") {
    if (readyTimer) window.clearTimeout(readyTimer);
    if (readyResolve) readyResolve();
    return;
  }
  if (data.type === "error") {
    if (readyTimer) window.clearTimeout(readyTimer);
    if (readyReject) readyReject(new Error(data.message));
    else { setStatus("RNNoise failed: " + data.message, true); void stopTest(); }
    return;
  }
  if (data.type !== "audio") return;
  const raw48 = new Float32Array(data.raw);
  const clean48 = new Float32Array(data.clean);
  document.getElementById("raw-rms").textContent = rms(raw48).toFixed(4);
  document.getElementById("clean-rms").textContent = rms(raw48).toFixed(4) + " → " + rms(clean48).toFixed(4);
  branches.raw.chunker.push(downsample48to16(raw48));
  branches.clean.chunker.push(downsample48to16(clean48));
}

async function startTest() {
  if (running) return;
  ui.start.disabled = true;
  setStatus("Requesting microphone…");
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 48000, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
    if (typeof AudioContext === "undefined") throw new Error("Web Audio API is unavailable in this browser");
    audioContext = new AudioContext({ sampleRate: 48000 });
    if (audioContext.sampleRate !== 48000) throw new Error("RNNoise test needs a 48 kHz AudioContext; this browser provided " + audioContext.sampleRate + " Hz");
    await audioContext.audioWorklet.addModule("/js/rnnoise-worklet.js");
    const ready = new Promise(function (resolve, reject) { readyResolve = resolve; readyReject = reject; });
    workletNode = new AudioWorkletNode(audioContext, "rnnoise-dual-capture", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1], channelCount: 1 });
    workletNode.port.onmessage = handleWorkletMessage;
    readyTimer = window.setTimeout(function () { if (readyReject) readyReject(new Error("RNNoise WASM initialization timed out")); }, 15000);
    await Promise.all([connectBranch("raw"), connectBranch("clean")]);
    branches.raw.chunker = new PcmChunker(branches.raw.socket);
    branches.clean.chunker = new PcmChunker(branches.clean.socket);
    sourceNode = audioContext.createMediaStreamSource(stream);
    muteNode = audioContext.createGain(); muteNode.gain.value = 0;
    sourceNode.connect(workletNode); workletNode.connect(muteNode); muteNode.connect(audioContext.destination);
    await audioContext.resume();
    running = true;
    ui.stop.disabled = false;
    setStatus("Loading local RNNoise WASM…");
    await ready;
    setStatus("RNNoise is ready. Both branches use the same 5.92-second window; predictions update every " + INFERENCE_INTERVAL_LABEL + ".");
  } catch (error) {
    setStatus(error && error.message ? error.message : String(error), true);
    await stopTest();
  } finally {
    ui.start.disabled = running;
  }
}

async function stopTest() {
  running = false;
  ui.stop.disabled = true;
  if (readyTimer) { window.clearTimeout(readyTimer); readyTimer = null; }
  readyResolve = null; readyReject = null;
  if (workletNode) {
    try { workletNode.port.postMessage({ type: "dispose" }); workletNode.disconnect(); } catch (_) {}
    workletNode = null;
  }
  if (sourceNode) { try { sourceNode.disconnect(); } catch (_) {} sourceNode = null; }
  if (muteNode) { try { muteNode.disconnect(); } catch (_) {} muteNode = null; }
  Object.keys(branches).forEach(function (name) {
    const branch = branches[name];
    if (branch.chunker) branch.chunker.flush();
    branch.chunker = null;
    if (branch.socket) { try { branch.socket.close(); } catch (_) {} branch.socket = null; }
    setConnection(name, "stopped");
  });
  if (stream) { stream.getTracks().forEach(function (track) { track.stop(); }); stream = null; }
  if (audioContext) { try { await audioContext.close(); } catch (_) {} audioContext = null; }
  ui.start.disabled = false;
  if (!ui.status.classList.contains("error")) setStatus("Stopped. The microphone tracks and both Gate 2 streams are closed.");
}

ui.expected.addEventListener("change", function () { renderExpected("raw"); renderExpected("clean"); });
ui.start.addEventListener("click", startTest);
ui.stop.addEventListener("click", stopTest);
makeBars("raw"); makeBars("clean");
window.addEventListener("pagehide", function () { void stopTest(); });
