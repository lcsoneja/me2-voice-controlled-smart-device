const AUDIO_RATE = 48000;
const MAX_TAKE_MS = 600000;
const ui = {
 recState: document.getElementById("recState"), micState: document.getElementById("micState"),
 elapsed: document.getElementById("elapsed"), levelFill: document.getElementById("levelFill"),
 wave: document.getElementById("wave"), miniTop: document.getElementById("miniTop"),
 miniConf: document.getElementById("miniConf"), miniMatch: document.getElementById("miniMatch"),
 miniChart: document.getElementById("miniChart"), g2minNote: document.getElementById("g2minNote"),
 miniLog: document.getElementById("miniLog"), stopMic: document.getElementById("stopMic"),
 status: document.getElementById("status"), recordingLabel: document.getElementById("recording-label"),
 phraseList: document.getElementById("phrase-list"), logList: document.getElementById("log-list"),
 exportCsv: document.getElementById("export-csv"), exportZip: document.getElementById("export-zip"),
 clearAll: document.getElementById("clear-all"), countTotal: document.getElementById("countTotal"),
 countIntents: document.getElementById("countIntents"), countPhrases: document.getElementById("countPhrases")
};
let phrases = [];
let takes = [];
let state = "idle"; // idle | recording | saving
let currentPhrase = null; // item being recorded
let openTake = null; // {phrase, id} mini player shown
let playing = null; // {take, source, offset, t0, paused}
let chunks = [], capturedSamples = 0, recordTimer = null;
let capturing = false;
let context = null, stream = null, sourceNode = null, workletNode = null, muteNode = null;
let ws = null, wsReady = false, wsTimer = null, sendAccum = null;
let lastRms = 0, liveMax = 0.08, busyExport = false;
const chartTicks = [];
const thumbMap = new Map();

function setStatus(text, isError) {
 ui.status.textContent = text;
 ui.status.classList.toggle("error", Boolean(isError));
}
function phraseSlug(phrase) {
 return phrase.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}
function stampOf(date) {
 return date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}
function wavFilename(intent, phrase, date) {
 return "gate2_" + intent + "__" + phraseSlug(phrase) + "__" + stampOf(date) + ".wav";
}
function formatTime(seconds) {
 const m = Math.floor(seconds / 60);
 const s = seconds - m * 60;
 return m + ":" + (s < 10 ? "0" : "") + s.toFixed(1);
}

function openDb() {
 return new Promise(function (resolve, reject) {
 const request = indexedDB.open("gate2-dataset-recorder", 1);
 request.onupgradeneeded = function () {
 const db = request.result;
 if (!db.objectStoreNames.contains("takes")) db.createObjectStore("takes", { keyPath: "id" });
 };
 request.onsuccess = function () { resolve(request.result); };
 request.onerror = function () { reject(request.error || new Error("Could not open local take database")); };
 });
}
function storeRun(storeName, mode, factory) {
 return openDb().then(function (db) {
 return new Promise(function (resolve, reject) {
 const tx = db.transaction(storeName, mode);
 const request = factory(tx.objectStore(storeName));
 request.onsuccess = function () { resolve(request.result); };
 request.onerror = function () { reject(request.error || new Error("Local database request failed")); };
 });
 });
}
const saveTake = (take) => storeRun("takes", "readwrite", (store) => store.put(take));
const deleteTake = (id) => storeRun("takes", "readwrite", (store) => store.delete(id));
const getTakes = () => storeRun("takes", "readonly", (store) => store.getAll());
const clearTakes = () => storeRun("takes", "readwrite", (store) => store.clear());

function encodePcmWav(samples, sampleRate) {
 const buffer = new ArrayBuffer(44 + samples.length * 2);
 const view = new DataView(buffer);
 const putText = function (offset, text) {
 for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
 };
 putText(0, "RIFF");
 view.setUint32(4, 36 + samples.length * 2, true);
 putText(8, "WAVE");
 putText(12, "fmt ");
 view.setUint32(16, 16, true);
 view.setUint16(20, 1, true);
 view.setUint16(22, 1, true);
 view.setUint32(24, sampleRate, true);
 view.setUint32(28, sampleRate * 2, true);
 view.setUint16(32, 2, true);
 view.setUint16(34, 16, true);
 putText(36, "data");
 view.setUint32(40, samples.length * 2, true);
 let offset = 44;
 for (let i = 0; i < samples.length; i++) {
 const clipped = Math.max(-1, Math.min(1, samples[i]));
 view.setInt16(offset, Math.round(clipped * (clipped < 0 ? 32768 : 32767)), true);
 offset += 2;
 }
 return new Blob([buffer], { type: "audio/wav" });
}
function downloadBlob(blob, filename) {
 const url = URL.createObjectURL(blob);
 const anchor = document.createElement("a");
 anchor.href = url;
 anchor.download = filename;
 document.body.appendChild(anchor);
 anchor.click();
 anchor.remove();
 window.setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
}
const CRC_TABLE = (function () {
 const table = new Uint32Array(256);
 for (let n = 0; n < 256; n++) {
 let value = n;
 for (let k = 0; k < 8; k++) value = (value & 1) ? (3988292384 ^ (value >>> 1)) : (value >>> 1);
 table[n] = value >>> 0;
 }
 return table;
})();
function crc32(bytes) {
 let crc = -1;
 for (let i = 0; i < bytes.length; i++) crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ bytes[i]) & 255];
 return (crc ^ -1) >>> 0;
}
function buildZip(files) {
 const encoder = new TextEncoder();
 const localParts = [];
 const centralParts = [];
 let offset = 0;
 files.forEach(function (file) {
 const nameBytes = encoder.encode(file.name);
 const data = file.data;
 const crc = crc32(data);
 const local = new DataView(new ArrayBuffer(30));
 local.setUint32(0, 67324752, true);
 local.setUint16(4, 20, true);
 local.setUint16(6, 0x0800, true);
 local.setUint16(8, 0, true);
 local.setUint16(10, 0, true);
 local.setUint16(12, 0x5c21, true);
 local.setUint32(14, crc, true);
 local.setUint32(18, data.length, true);
 local.setUint32(22, data.length, true);
 local.setUint16(26, nameBytes.length, true);
 local.setUint16(28, 0, true);
 localParts.push(new Uint8Array(local.buffer), nameBytes, data);
 const central = new DataView(new ArrayBuffer(46));
 central.setUint32(0, 33639248, true);
 central.setUint16(4, 20, true);
 central.setUint16(6, 20, true);
 central.setUint16(8, 0x0800, true);
 central.setUint16(10, 0, true);
 central.setUint16(12, 0, true);
 central.setUint16(14, 0x5c21, true);
 central.setUint32(16, crc, true);
 central.setUint32(20, data.length, true);
 central.setUint32(24, data.length, true);
 central.setUint16(28, nameBytes.length, true);
 central.setUint32(42, offset, true);
 centralParts.push(new Uint8Array(central.buffer), nameBytes);
 offset += 30 + nameBytes.length + data.length;
 });
 const centralSize = centralParts.reduce((total, part) => total + part.length, 0);
 const end = new DataView(new ArrayBuffer(22));
 end.setUint32(0, 101010256, true);
 end.setUint16(8, files.length, true);
 end.setUint16(10, files.length, true);
 end.setUint32(12, centralSize, true);
 end.setUint32(16, offset, true);
 return new Blob(localParts.concat(centralParts, [new Uint8Array(end.buffer)]), { type: "application/zip" });
}
function computePeaks(samples, buckets) {
 const peaks = new Float32Array(buckets * 2);
 const size = Math.max(1, Math.floor(samples.length / buckets));
 for (let b = 0; b < buckets; b++) {
 let min = 1, max = -1;
 const start = b * size;
 const stop = Math.min(samples.length, start + size);
 for (let i = start; i < stop; i++) {
 const v = samples[i];
 if (v < min) min = v;
 if (v > max) max = v;
 }
 peaks[b * 2] = stop > start ? min : 0;
 peaks[b * 2 + 1] = stop > start ? max : 0;
 }
 return peaks;
}


function down48to16(samples) {
 const output = new Float32Array(Math.floor(samples.length / 3));
 for (let i = 0; i < output.length; i++) output[i] = (samples[i * 3] + samples[i * 3 + 1] + samples[i * 3 + 2]) / 3;
 return output;
}

const LIVE_COLS = 200;
const livePeaks = new Float32Array(LIVE_COLS * 2);
function pushLivePeak(min, max) {
 livePeaks.copyWithin(0, 2);
 livePeaks[LIVE_COLS * 2 - 2] = min;
 livePeaks[LIVE_COLS * 2 - 1] = max;
}
const waveCtx = ui.wave.getContext("2d");
function drawLive() {
 const w = ui.wave.width, h = ui.wave.height, mid = h / 2;
 waveCtx.fillStyle = "#0d1117";
 waveCtx.fillRect(0, 0, w, h);
 waveCtx.strokeStyle = "#1f2937";
 waveCtx.lineWidth = 1;
 waveCtx.beginPath(); waveCtx.moveTo(0, mid); waveCtx.lineTo(w, mid); waveCtx.stroke();
 waveCtx.strokeStyle = "#58c9b0";
 const usable = h / 2 - 4;
 const scale = 1 / Math.max(0.08, liveMax);
 for (let c = 0; c < LIVE_COLS; c++) {
 const min = livePeaks[c * 2], max = livePeaks[c * 2 + 1];
 if (min === 0 && max === 0) continue;
 const x = (c / LIVE_COLS) * w;
 waveCtx.beginPath();
 waveCtx.moveTo(x + 0.5, mid - max * scale * usable);
 waveCtx.lineTo(x + 0.5, mid - min * scale * usable);
 waveCtx.stroke();
 }
}
function drawSparkline(canvas, peaks, progress) {
 const ctx2 = canvas.getContext("2d");
 const w = canvas.width, h = canvas.height, mid = h / 2;
 ctx2.fillStyle = "#0d1117";
 ctx2.fillRect(0, 0, w, h);
 ctx2.strokeStyle = "#2f6f63";
 const buckets = peaks.length / 2;
 const colW = w / buckets;
 for (let b = 0; b < buckets; b++) {
 const min = peaks[b * 2], max = peaks[b * 2 + 1];
 if (min === 0 && max === 0) continue;
 ctx2.beginPath();
 ctx2.moveTo(b * colW + 0.5, mid - max * (mid - 1));
 ctx2.lineTo(b * colW + 0.5, mid - min * (mid - 1));
 ctx2.stroke();
 }
 if (progress !== undefined && progress > 0) {
 ctx2.fillStyle = "rgba(130,174,232,0.25)";
 ctx2.fillRect(0, 0, w * Math.min(1, progress), h);
 ctx2.fillStyle = "#82aee8";
 ctx2.fillRect(w * Math.min(1, progress) - 1, 0, 2, h);
 }
}

function readThresholds() {
 let map = {}, globalMin = 0.5;
 try {
 const saved = localStorage.getItem("vcm_thr_g2");
 if (saved) map = JSON.parse(saved) || {};
 } catch {}
 try {
 const saved = localStorage.getItem("vcm_thr");
 if (saved) {
 const parsed = JSON.parse(saved) || {};
 if (Number.isFinite(parsed.gate2MinConf)) globalMin = parsed.gate2MinConf;
 }
 } catch {}
 return { map: map, globalMin: globalMin };
}
function thresholdFor(intent) {
 const thresholds = readThresholds();
 const value = Number(thresholds.map[intent]);
 if (Number.isFinite(value)) return Math.min(0.95, Math.max(0.05, value));
 return Math.min(0.95, Math.max(0.05, thresholds.globalMin));
}
function referenceIntent() {
 if (currentPhrase) return currentPhrase.intent;
 if (ui.phrase) {
 const selected = ui.phrase.value;
 const item = phrases.find(function (p) { return p.phrase === selected; });
 if (item) return item.intent;
 }
 return takes.length ? takes[0].intent : null;
}

const miniCtx = ui.miniChart.getContext("2d");
function drawMiniChart() {
 const w = ui.miniChart.width, h = ui.miniChart.height, mid = h / 2;
 miniCtx.fillStyle = "#0d1117";
 miniCtx.fillRect(0, 0, w, h);
 const intent = referenceIntent();
 const threshold = intent ? thresholdFor(intent) : 0.5;
 const ticks = chartTicks.slice(-30);
 if (ticks.length) {
 miniCtx.strokeStyle = "#82aee8";
 miniCtx.lineWidth = 1.5;
 miniCtx.beginPath();
 ticks.forEach(function (tickData, index) {
 const x = (index / Math.max(1, ticks.length - 1)) * (w - 8) + 4;
 const y = mid - (tickData.conf - 0.5) * 2 * (h / 2 - 4);
 if (index === 0) miniCtx.moveTo(x, y); else miniCtx.lineTo(x, y);
 });
 miniCtx.stroke();
 }
 miniCtx.strokeStyle = "#e4b669";
 miniCtx.setLineDash([5, 4]);
 miniCtx.beginPath();
 const ty = mid - (threshold - 0.5) * 2 * (h / 2 - 4);
 miniCtx.moveTo(4, ty); miniCtx.lineTo(w - 4, ty);
 miniCtx.stroke();
 miniCtx.setLineDash([]);
 ui.g2minNote.textContent = threshold.toFixed(2);
}

function handleInference(message) {
 chartTicks.push({ conf: Number(message.conf) || 0, intent: message.top });
 if (chartTicks.length > 60) chartTicks.shift();
 const intent = referenceIntent();
 const threshold = intent ? thresholdFor(intent) : 0.5;
 const conf = Number(message.conf) || 0;
 ui.miniTop.textContent = message.top || "—";
 ui.miniConf.textContent = conf.toFixed(3);
 const matched = intent !== null && message.top === intent && conf >= threshold;
 ui.miniTop.classList.toggle("match", matched);
 ui.miniMatch.textContent = matched
 ? "match ✓ for current label (≥ threshold)"
 : (intent ? "expected label: " + intent : "waiting…");
 ui.miniMatch.className = "minimatch" + (matched ? " good" : "");
 drawMiniChart();
 const stamp = new Date().toLocaleTimeString();
 const line = document.createElement("div");
 line.className = matched ? "good" : "";
 line.textContent = stamp + " · " + message.top + " · " + conf.toFixed(4);
 ui.miniLog.prepend(line);
 while (ui.miniLog.children.length > 8) ui.miniLog.removeChild(ui.miniLog.lastChild);
}

const WORKLET_URL = URL.createObjectURL(new Blob([
 'class RawCaptureProcessor extends AudioWorkletProcessor{constructor(){super();this.buffer=new Float32Array(4096);this.length=0}process(inputs){const input=inputs[0]&&inputs[0][0];if(!input||!input.length)return true;let offset=0;while(offset<input.length){const count=Math.min(4096-this.length,input.length-offset);this.buffer.set(input.subarray(offset,offset+count),this.length);this.length+=count;offset+=count;if(this.length===4096){const out=this.buffer.slice(0,this.length);this.port.postMessage({type:"audio",samples:out.buffer},[out.buffer]);this.buffer=new Float32Array(4096);this.length=0}}return true}}registerProcessor("raw-capture",RawCaptureProcessor);'
], { type: "application/javascript" }));

async function ensureContext() {
 if (!context) {
 if (!window.AudioContext) throw new Error("Web Audio API is unavailable in this browser");
 context = new window.AudioContext({ sampleRate: AUDIO_RATE });
 if (context.sampleRate !== AUDIO_RATE) throw new Error("This recorder needs a 48 kHz AudioContext; browser provided " + context.sampleRate + " Hz");
 await context.audioWorklet.addModule(WORKLET_URL);
 workletNode = new AudioWorkletNode(context, "raw-capture", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1], channelCount: 1 });
 sendAccum = new Float32Array(4096);
 let sendLength = 0;
 workletNode.port.onmessage = function (event) {
 const data = event.data;
 if (!data || data.type !== "audio") return;
 const chunk = new Float32Array(data.samples);
 let min = 1, max = -1, sum = 0;
 for (let i = 0; i < chunk.length; i++) {
 const v = chunk[i];
 if (v < min) min = v;
 if (v > max) max = v;
 sum += v * v;
 }
 if (capturing) { chunks.push(chunk); capturedSamples += chunk.length; }
 pushLivePeak(min, max);
 liveMax = Math.max(liveMax * 0.997, Math.max(Math.abs(min), Math.abs(max)));
 lastRms = Math.sqrt(sum / chunk.length);
 const down = down48to16(chunk);
 let offset = 0;
 while (offset < down.length) {
 const count = Math.min(4096 - sendLength, down.length - offset);
 sendAccum.set(down.subarray(offset, offset + count), sendLength);
 sendLength += count; offset += count;
 if (sendLength === 4096) {
 if (wsReady) ws.send(sendAccum.buffer);
 sendAccum = new Float32Array(4096); sendLength = 0;
 }
 }
 };
 muteNode = context.createGain();
 muteNode.gain.value = 0;
 workletNode.connect(muteNode);
 muteNode.connect(context.destination);
 }
 await context.resume();
}

function connectGate2() {
 if (ws || !stream) return;
 const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
 ws = new WebSocket(protocol + "//" + window.location.host + "/ws");
 ws.binaryType = "arraybuffer";
 ws.onopen = function () {
 wsReady = true;
 ws.send(JSON.stringify({ type: "mode", mode: "gate2" }));
 };
 ws.onmessage = function (event) {
 if (typeof event.data !== "string") return;
 let message;
 try { message = JSON.parse(event.data); } catch { return; }
 if (message.type === "probs2") handleInference(message);
 };
 ws.onclose = function () {
 ws = null; wsReady = false;
 if (stream && !wsTimer) wsTimer = window.setTimeout(function () { wsTimer = null; connectGate2(); }, 2000);
 };
 ws.onerror = function () { try { ws.close(); } catch {} };
}

async function attachMic() {
 if (!stream) {
 stream = await navigator.mediaDevices.getUserMedia({
 audio: { channelCount: 1, sampleRate: AUDIO_RATE, echoCancellation: false, noiseSuppression: false, autoGainControl: false }
 });
 }
 if (!sourceNode) {
 sourceNode = context.createMediaStreamSource(stream);
 sourceNode.connect(workletNode);
 }
 ui.micState.textContent = "Mic: live";
 ui.stopMic.disabled = false;
 connectGate2();
}
function releaseAudio() {
 stopMiniPlayback();
 if (sourceNode) { try { sourceNode.disconnect(); } catch {} sourceNode = null; }
 if (workletNode) { try { workletNode.disconnect(); } catch {} workletNode = null; }
 if (muteNode) { try { muteNode.disconnect(); } catch {} muteNode = null; }
 if (stream) { stream.getTracks().forEach(function (track) { track.stop(); }); stream = null; }
 if (wsTimer) { window.clearTimeout(wsTimer); wsTimer = null; }
 if (ws) { try { ws.close(); } catch {} ws = null; wsReady = false; }
 if (context) { try { context.close(); } catch {} context = null; }
 ui.micState.textContent = "Mic: off";
 ui.stopMic.disabled = true;
}

let lastElapsed = 0;
let lastDraw = 0;
function tick(now) {
 requestAnimationFrame(tick);
 if (now - lastDraw < 50) return;
 lastDraw = now;
 drawLive();
 ui.levelFill.style.width = Math.min(100, lastRms * 300) + "%";
 if (state === "recording") {
 lastElapsed = capturedSamples / AUDIO_RATE;
 ui.elapsed.textContent = formatTime(lastElapsed);
 } else if (state === "saving") {
 ui.elapsed.textContent = formatTime(lastElapsed);
 }
 const chipText = { idle: "\u25cf Idle", recording: "\u25cf Recording", saving: "\u25cf Saving\u2026" }[state] || "\u25cf Idle";
 ui.recState.textContent = chipText;
 ui.recState.className = "recchip" + (state === "recording" ? " recording" : state === "saving" ? " saving" : "");
 if (playing && !playing.paused) {
 const position = playing.offset + (context ? context.currentTime - playing.t0 : 0);
 const canvas = thumbMap.get(playing.take.id);
 if (canvas) drawSparkline(canvas, playing.take.peaks, position / Math.max(0.001, playing.take.duration));
 }
}
requestAnimationFrame(tick);
function buildPhraseRows() {
 ui.phraseList.replaceChildren();
 const takesByPhrase = {};
 takes.forEach(function (take) {
 takesByPhrase[take.phrase] = (takesByPhrase[take.phrase] || 0) + 1;
 });
 const groups = new Map();
 phrases.forEach(function (item) {
 if (!groups.has(item.group)) groups.set(item.group, []);
 groups.get(item.group).push(item);
 });
 groups.forEach(function (items, groupName) {
 const section = document.createElement("section"); section.className = "group";
 const title = document.createElement("h3");
 const name = document.createElement("span"); name.textContent = groupName;
 const count = document.createElement("small"); count.textContent = items.length + " phrases";
 title.append(name, count); section.appendChild(title);
 items.forEach(function (item) {
 const row = document.createElement("div"); row.className = "prow"; row.dataset.phrase = item.phrase;
 const text = document.createElement("div"); text.className = "ptext"; text.textContent = item.phrase;
 const pint = document.createElement("span"); pint.className = "pint"; pint.textContent = item.intent;
 text.appendChild(pint);
 const btns = document.createElement("div"); btns.className = "btns";
 const record = document.createElement("button"); record.className = "record-phrase primary";
 record.dataset.phrase = item.phrase; record.textContent = "Record";
 record.disabled = state !== "idle" || busyExport;
 record.addEventListener("click", function () { void startRecording(item); });
 const stop = document.createElement("button"); stop.className = "stop-take";
 stop.dataset.phrase = item.phrase; stop.textContent = "Stop & save WAV";
 stop.disabled = !(state === "recording" && currentPhrase && currentPhrase.phrase === item.phrase);
 if (state === "recording" && currentPhrase && currentPhrase.phrase === item.phrase) stop.classList.add("recording");
 stop.addEventListener("click", function () { void stopTakeRow(item); });
 const takesForPhrase = takes.filter(function (take) { return take.phrase === item.phrase; })
 .sort(function (a, b) { return a.createdAt.localeCompare(b.createdAt); });
 const select = document.createElement("select"); select.className = "take-select";
 select.title = "Recordings of this phrase";
 if (!takesForPhrase.length) {
 const option = document.createElement("option"); option.textContent = "No takes";
 select.appendChild(option); select.disabled = true;
 } else {
 takesForPhrase.forEach(function (take, index) {
 const option = document.createElement("option");
 option.value = take.id;
 option.textContent = "take #" + (index + 1) + " · " + take.duration.toFixed(1) + "s";
 select.appendChild(option);
 });
 select.disabled = state === "recording";
 const openId = openTake && openTake.phrase === item.phrase ? openTake.id : takesForPhrase[takesForPhrase.length - 1].id;
 select.value = openId;
 select.addEventListener("change", function () {
 const take = takes.find(function (t) { return t.id === select.value; });
 if (take) openMiniPlayer(item, take); else closeMiniPlayer();
 });
 }
 const takesBadge = document.createElement("span"); takesBadge.className = "takes";
 takesBadge.dataset.phrase = item.phrase;
 takesBadge.textContent = String(takesByPhrase[item.phrase] || 0);
 btns.append(record, stop, select, takesBadge);
 row.append(text, btns);
 if (openTake && openTake.phrase === item.phrase) {
 const take = takes.find(function (t) { return t.id === openTake.id; });
 if (take) row.appendChild(buildMiniPlayer(item, take));
 }
 section.appendChild(row);
 });
 ui.phraseList.appendChild(section);
 });
}

function buildMiniPlayer(_item, take) {
 const player = document.createElement("div"); player.className = "mini-player";
 player.dataset.takeId = take.id;
 const canvas = document.createElement("canvas");
 canvas.className = "mini-canvas"; canvas.width = 150; canvas.height = 18;
 drawSparkline(canvas, take.peaks, playing && playing.take.id === take.id ? miniProgress() : undefined);
 thumbMap.set(take.id, canvas);
 const play = document.createElement("button"); play.className = "mini-play";
 play.textContent = playing && playing.take.id === take.id ? "⏸" : "▶";
 play.title = "Play this take";
 play.disabled = state === "recording" || state === "saving";
 play.addEventListener("click", function () { void playMiniTake(take); });
 const wav = document.createElement("button"); wav.className = "mini-wav"; wav.textContent = "WAV";
 wav.addEventListener("click", function () { downloadBlob(take.wavBlob, take.fileName); });
 const del = document.createElement("button"); del.className = "mini-delete"; del.textContent = "Delete";
 del.addEventListener("click", async function () {
 if (!window.confirm("Delete take " + take.fileName + "?")) return;
 if (playing && playing.take.id === take.id) stopMiniPlayback();
 await deleteTake(take.id);
 closeMiniPlayer();
 await refreshTakes();
 setStatus("Take deleted.");
 });
 const dur = document.createElement("span"); dur.className = "mini-dur";
 dur.textContent = take.duration.toFixed(2) + "s";
 const fname = document.createElement("span"); fname.className = "mini-fname"; fname.textContent = take.fileName;
 player.append(canvas, play, wav, del, dur, fname);
 return player;
}

function openMiniPlayer(item, take) {
 if (state === "recording" || state === "saving") return;
 openTake = { phrase: item.phrase, id: take.id };
 renderPhraseRows();
 const row = ui.phraseList.querySelector('.prow[data-phrase="' + CSS.escape(item.phrase) + '"]');
 if (row) row.scrollIntoView({ block: "nearest" });
}
function closeMiniPlayer() {
 openTake = null;
}
function miniProgress() {
 if (!playing || playing.paused) return 0;
 const position = playing.offset + (context ? context.currentTime - playing.t0 : 0);
 return position / Math.max(0.001, playing.take.duration);
}
async function playMiniTake(take) {
 if (state === "recording" || state === "saving") return;
 if (playing && playing.take.id === take.id) {
 if (playing.paused) {
 await ensureContext();
 playing.paused = false; playing.t0 = context.currentTime;
 startMiniSource(playing.offset);
 const play = ui.phraseList.querySelector('.mini-player[data-take-id="' + take.id + '"] .mini-play');
 if (play) play.textContent = "⏸";
 }
 else {
 playing.offset += context.currentTime - playing.t0;
 try { playing.source.stop(); } catch {}
 playing.source = null; playing.paused = true;
 const play2 = ui.phraseList.querySelector('.mini-player[data-take-id="' + take.id + '"] .mini-play');
 if (play2) play2.textContent = "▶";
 }
 return;
 }
 stopMiniPlayback();
 await ensureContext();
 const buffer = await take.wavBlob.arrayBuffer();
 const decoded = await context.decodeAudioData(buffer);
 playing = { take: take, buffer: decoded, offset: 0, t0: 0, paused: false, source: null };
 startMiniSource(0);
 const startBtn = ui.phraseList.querySelector('.mini-player[data-take-id="' + take.id + '"] .mini-play');
 if (startBtn) startBtn.textContent = "⏸";
 setStatus("Playing " + take.fileName);
}
function startMiniSource(offset) {
 playing.source = context.createBufferSource();
 playing.source.buffer = playing.buffer;
 playing.source.connect(context.destination);
 const take = playing.take;
 playing.source.onended = function () {
 if (playing && playing.source === this) {
 const wasEnded = state !== "recording";
 playing = null;
 const canvas = thumbMap.get(take.id);
 if (canvas) drawSparkline(canvas, take.peaks, undefined);
 const play = ui.phraseList.querySelector('.mini-player[data-take-id="' + take.id + '"] .mini-play');
 if (play) play.textContent = "▶";
 if (wasEnded) setStatus("Playback finished.");
 }
 };
 playing.t0 = context.currentTime; playing.offset = offset;
 playing.source.start(0, offset);
}
function stopMiniPlayback() {
 if (!playing) return;
 const take = playing.take;
 if (playing.source) { try { playing.source.stop(); } catch {} }
 playing = null;
 const canvas = thumbMap.get(take.id);
 if (canvas) drawSparkline(canvas, take.peaks, undefined);
 const play = ui.phraseList.querySelector('.mini-player[data-take-id="' + take.id + '"] .mini-play');
 if (play) play.textContent = "▶";
}

async function startRecording(item) {
 if (state !== "idle" || busyExport) return;
 if (playing) stopMiniPlayback();
 closeMiniPlayer();
 try {
 await ensureContext();
 await attachMic();
 } catch (error) {
 setStatus(error.message || String(error), true);
 return;
 }
 chunks = []; capturedSamples = 0; capturing = true;
 currentPhrase = item; state = "recording";
 ui.recordingLabel.textContent = "Recording label: " + item.intent + " · " + item.phrase;
 setStatus("Recording \u201c" + item.phrase + "\u201d. Say it once, then press Stop & save on this row.");
 renderPhraseRows();
 recordTimer = window.setTimeout(function () { if (state === "recording" && currentPhrase) void stopTakeRow(currentPhrase); }, MAX_TAKE_MS);
}

async function stopTakeRow(item) {
 if (state !== "recording" || !currentPhrase || currentPhrase.phrase !== item.phrase) return;
 capturing = false; state = "saving";
 if (recordTimer) { window.clearTimeout(recordTimer); recordTimer = null; }
 ui.recState.textContent = "● Saving…"; ui.recState.className = "recchip saving";
 renderPhraseRows();
 const merged = chunks; chunks = [];
 const length = merged.reduce(function (total, part) { return total + part.length; }, 0);
 const samples = new Float32Array(length);
 let offset = 0;
 merged.forEach(function (part) { samples.set(part, offset); offset += part.length; });
 if (samples.length < AUDIO_RATE / 8) {
 state = "idle"; currentPhrase = null; lastElapsed = 0;
 ui.recState.textContent = "● Idle"; ui.recState.className = "recchip";
 renderPhraseRows();
 setStatus("Take too short — discarded. Record at least 0.25 seconds.", true);
 return;
 }
 const createdAt = new Date().toISOString();
 const take = {
 id: crypto.randomUUID(), intent: item.intent, phrase: item.phrase, group: item.group,
 createdAt: createdAt, duration: samples.length / AUDIO_RATE, sampleRate: AUDIO_RATE,
 fileName: wavFilename(item.intent, item.phrase, new Date(createdAt)),
 peaks: Array.from(computePeaks(samples, 200)), wavBlob: encodePcmWav(samples, AUDIO_RATE)
 };
 await saveTake(take);
 downloadBlob(take.wavBlob, take.fileName);
 lastElapsed = take.duration;
 await refreshTakes();
 currentPhrase = null; state = "idle";
 ui.recState.textContent = "● Idle"; ui.recState.className = "recchip";
 renderPhraseRows();
 setStatus("Saved " + take.fileName + ". It is in this row\u2019s dropdown and the log.");
}

function renderPhraseRows() { buildPhraseRows(); }
async function refreshTakes() {
 takes = await getTakes();
 takes.sort(function (a, b) { return b.createdAt.localeCompare(a.createdAt); });
 if (openTake) {
 const found = takes.find(function (t) { return t.id === openTake.id && t.phrase === openTake.phrase; });
 if (!found) closeMiniPlayer();
 }
 renderList();
 const intents = new Set(takes.map(function (t) { return t.intent; }));
 const covered = new Set(takes.map(function (t) { return t.phrase; }));
 ui.countTotal.textContent = String(takes.length);
 ui.countIntents.textContent = String(intents.size);
 ui.countPhrases.textContent = String(covered.size);
}

function renderList() {
 thumbMap.clear();
 ui.logList.replaceChildren();
 if (!takes.length) { ui.logList.innerHTML = '<div class="empty">No takes yet.</div>'; }
 takes.forEach(function (take) {
 const row = document.createElement("div"); row.className = "logrow"; row.title = "Click to open this take\u2019s player on its phrase row";
 row.addEventListener("click", function () {
 const item = phrases.find(function (p) { return p.phrase === take.phrase; });
 if (item) openMiniPlayer(item, take);
 });
 const date = document.createElement("span"); date.textContent = new Date(take.createdAt).toLocaleString();
 const intent = document.createElement("span"); intent.textContent = take.intent;
 const phraseCell = document.createElement("div");
 const phrase = document.createElement("div"); phrase.textContent = take.label || take.phrase;
 const fname = document.createElement("div"); fname.className = "fname"; fname.textContent = take.fileName;
 phraseCell.append(phrase, fname);
 const duration = document.createElement("span"); duration.textContent = take.duration.toFixed(2) + " s · " + take.sampleRate + " Hz";
 const actions = document.createElement("div"); actions.className = "rowbtns";
 const wav = document.createElement("button"); wav.textContent = "WAV";
 wav.addEventListener("click", function (event) { event.stopPropagation(); downloadBlob(take.wavBlob, take.fileName); });
 const del = document.createElement("button"); del.textContent = "Delete";
 del.addEventListener("click", async function (event) {
 event.stopPropagation();
 if (!window.confirm("Delete take " + take.fileName + "?")) return;
 if (playing && playing.take.id === take.id) stopMiniPlayback();
 await deleteTake(take.id);
 if (openTake && openTake.id === take.id) closeMiniPlayer();
 await refreshTakes();
 setStatus("Take deleted.");
 });
 actions.append(wav, del);
 row.append(date, intent, phraseCell, duration, actions);
 ui.logList.appendChild(row);
 });
 buildPhraseRows();
 const intents = new Set(takes.map(function (t) { return t.intent; }));
 const covered = new Set(takes.map(function (t) { return t.phrase; }));
 ui.countTotal.textContent = String(takes.length);
 ui.countIntents.textContent = String(intents.size);
 ui.countPhrases.textContent = String(covered.size);
}

function csvCell(value) {
 const text = value === null || value === undefined ? "" : String(value);
 return '"' + text.replace(/"/g, '""') + '"';
}
function manifestRows(rows) {
 const columns = ["file_name", "intent", "phrase", "recorded_at", "duration_seconds", "sample_rate"];
 const ordered = rows.slice().sort(function (a, b) { return a.createdAt.localeCompare(b.createdAt); });
 return [columns.join(",")].concat(ordered.map(function (take) {
 return [take.fileName, take.intent, take.phrase, take.createdAt, take.duration.toFixed(3), take.sampleRate].map(csvCell).join(",");
 })).join("\r\n");
}
async function exportCsv() {
 downloadBlob(new Blob(["\uFEFF", manifestRows(takes)], { type: "text/csv;charset=utf-8" }), "dataset_recorder_log.csv");
 setStatus("CSV log downloaded with " + takes.length + " rows.");
}
async function exportZip() {
 if (!takes.length) { setStatus("No takes to export yet.", true); return; }
 busyExport = true;
 ui.exportZip.disabled = true;
 setStatus("Building ZIP folder with " + takes.length + " WAV takes…");
 try {
 const encoder = new TextEncoder();
 const files = [];
 const ordered = takes.slice().sort(function (a, b) { return a.createdAt.localeCompare(b.createdAt); });
 for (const take of ordered) {
 files.push({ name: "recordings/" + take.intent + "/" + take.fileName, data: new Uint8Array(await take.wavBlob.arrayBuffer()) });
 }
 files.push({ name: "manifest.csv", data: encoder.encode(manifestRows(ordered)) });
 const counts = {};
 ordered.forEach(function (take) { counts[take.intent] = (counts[take.intent] || 0) + 1; });
 const readmeText = [
 "Gate 2 dataset takes",
 "Format: mono 48 kHz PCM16 WAV (dataset recorder, offline).",
 "Folder layout: recordings/<INTENT>/<file>.wav",
 "Labels: " + Object.keys(counts).sort().map(function (key) { return key + "=" + counts[key]; }).join(", "),
 "Total takes: " + ordered.length
 ].join("\r\n");
 files.push({ name: "README.txt", data: encoder.encode(readmeText) });
 downloadBlob(buildZip(files), "gate2_dataset_export_" + stampOf(new Date()) + ".zip");
 setStatus("ZIP folder downloaded with " + ordered.length + " takes, manifest.csv, and README.txt.");
 } catch (error) {
 setStatus(error.message || String(error), true);
 } finally {
 busyExport = false;
 ui.exportZip.disabled = false;
 buildPhraseRows();
 }
}
async function clearAllTakes() {
 if (!window.confirm("Delete every saved take from this browser? Downloaded WAV files stay on disk.")) return;
 await clearTakes();
 closeMiniPlayer();
 await refreshTakes();
 setStatus("All saved takes deleted from this browser.");
}

window.addEventListener("keydown", function (event) {
 if (event.target && (event.target.tagName === "INPUT" || event.target.tagName === "SELECT" || event.target.tagName === "TEXTAREA")) return;
 if (event.key === "Escape") {
 if (state === "recording" && currentPhrase) {
 event.preventDefault();
 capturing = false; chunks = []; capturedSamples = 0; lastElapsed = 0;
 if (recordTimer) { window.clearTimeout(recordTimer); recordTimer = null; }
 currentPhrase = null; state = "idle";
 ui.recState.textContent = "● Idle"; ui.recState.className = "recchip";
 ui.recordingLabel.textContent = "Click Record beside a phrase to begin.";
 renderPhraseRows();
 setStatus("Recording discarded (Esc). Nothing was saved.");
 }
 else if (playing) { event.preventDefault(); stopMiniPlayback(); }
 }
});
window.addEventListener("pagehide", function () {
 if (state === "recording") {
 capturing = false; chunks = []; capturedSamples = 0;
 if (recordTimer) { window.clearTimeout(recordTimer); recordTimer = null; }
 state = "idle";
 }
 releaseAudio();
});

async function rescueToServer() {
 if (!takes.length) { setStatus("No takes to rescue.", true); return; }
 if (state !== "idle") { setStatus("Stop the current recording first, then rescue.", true); return; }
 busyExport = true;
 buildPhraseRows();
 let ok = 0, failed = 0;
 setStatus("Rescuing 0/" + takes.length + " takes to server\u2026");
 for (let i = 0; i < takes.length; i++) {
 const take = takes[i];
 try {
 const buf = await take.wavBlob.arrayBuffer();
 const bytes = new Uint8Array(buf);
 let binary = "";
 const CHUNK = 0x8000;
 for (let j = 0; j < bytes.length; j += CHUNK) binary += String.fromCharCode.apply(null, bytes.subarray(j, j + CHUNK));
 const response = await fetch("http://127.0.0.1:8767/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fileName: take.fileName, intent: take.intent, phrase: take.phrase, createdAt: take.createdAt, durationSeconds: take.duration, sampleRate: take.sampleRate, wavBase64: btoa(binary) }) });
 if (response.ok) ok++; else failed++;
 } catch { failed++; }
 setStatus("Rescuing " + (i + 1) + "/" + takes.length + " takes to server\u2026 (saved " + ok + ", failed " + failed + ")");
 }
 busyExport = false;
 buildPhraseRows();
 setStatus("Rescue finished: " + ok + " takes written to the collected_data folder, " + failed + " failed.");
}

async function initialize() {
 const response = await fetch("/data/gate2_collection_phrases.json", { cache: "no-store" });
 if (!response.ok) throw new Error("Could not load the phrase list (HTTP " + response.status + ")");
 phrases = await response.json();
 ui.exportCsv.addEventListener("click", function () { void exportCsv(); });
 ui.exportZip.addEventListener("click", function () { void exportZip(); });
 ui.clearAll.addEventListener("click", function () { void clearAllTakes(); });
 document.getElementById("rescueServer").addEventListener("click", function () { void rescueToServer(); });
 ui.stopMic.addEventListener("click", function () {
 if (state === "recording" && currentPhrase) void stopTakeRow(currentPhrase).then(releaseAudio);
 else releaseAudio();
 setStatus("Microphone stopped. Saved takes remain available.");
 });
 await refreshTakes();
 setStatus("Ready. Record a phrase, Stop & save on the same row, and watch the live Gate 2 pane.");
}

void initialize().catch(function (error) { setStatus(error.message || String(error), true); });
