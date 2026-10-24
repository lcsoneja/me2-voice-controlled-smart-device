"""Generates gate1_monitor.html (WebSocket client for gate1_server.py).

Browser: mic capture at 16 kHz -> PCM blocks over WebSocket -> server does the
verified 148-frame features + gate1v2 TFLite inference -> probabilities stream
back. Charts, per-word thresholds (localStorage), CSV/JSON log saving.
Run:  python _generate_html.py      then   python ../gate1_server.py
"""
from pathlib import Path

HERE = Path(__file__).parent

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Gate 1 Wake-Word Monitor (gate1v2)</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; background:#0d1117; color:#c9d1d9; margin:0; padding:14px; }
  h1 { font-size: 18px; margin: 0 0 4px; color:#58a6ff; }
  .sub { color:#8b949e; font-size:12px; margin-bottom:10px; }
  .grid { display:grid; grid-template-columns: 1fr 340px; gap:12px; max-width:1200px; }
  .card { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:10px; }
  .card h2 { font-size:13px; margin:0 0 6px; color:#8b949e; text-transform:uppercase; letter-spacing:.5px; }
  canvas { width:100%; display:block; background:#0d1117; border-radius:4px; }
  #banner { font-size:24px; font-weight:700; padding:10px; border-radius:8px; text-align:center; margin-bottom:10px; }
  .wake { background:#1a7f37; color:#fff; }
  .listen { background:#30363d; color:#c9d1d9; }
  .probrow { display:flex; align-items:center; margin:6px 0; }
  .probname { width:80px; font-size:13px; }
  .probbarwrap { flex:1; background:#0d1117; border-radius:4px; height:22px; position:relative; overflow:hidden; }
  .probbar { height:100%; width:0%; background:#1f6feb; transition:width .15s; }
  .probval { width:56px; text-align:right; font-size:13px; font-variant-numeric:tabular-nums; }
  .thr { width:100%; }
  .thrlabel { font-size:12px; color:#8b949e; }
  #logbox { height:180px; overflow-y:auto; font-family:Consolas,monospace; font-size:11px; background:#0d1117; padding:6px; border-radius:4px; }
  button { background:#21262d; color:#c9d1d9; border:1px solid #30363d; border-radius:6px; padding:6px 10px; cursor:pointer; font-size:12px; margin:2px; }
  button:hover { background:#30363d; }
  #status { font-size:12px; color:#8b949e; margin-top:8px; white-space:pre-wrap; }
  .err { color:#f85149; }
  .ok { color:#3fb950; }
  .statsline { font-size:12px; color:#8b949e; margin-top:4px; }
</style>
</head>
<body>
<h1>Gate 1 Wake-Word Monitor — gate1v2 (148-frame, exact trained stack)</h1>
<div class="sub">rolling 5.92 s window &middot; inference every 1 s (server-side, exact TFLite + numpy preprocessing) &middot; fully local</div>
<div id="banner" class="listen">STARTING…</div>
<div class="grid">
  <div>
    <div class="card"><h2>Waveform (last ~0.25 s)</h2><canvas id="wave" width="760" height="120"></canvas></div>
    <div class="card" style="margin-top:10px"><h2>Mic level history (dB, ~30 s)</h2><canvas id="level" width="760" height="120"></canvas></div>
    <div class="card" style="margin-top:10px"><h2>Log</h2>
      <div id="logbox"></div>
      <div style="margin-top:6px">
        <button id="saveCsv">Download CSV</button>
        <button id="saveJson">Download JSON</button>
        <button id="clearLog">Clear log</button>
      </div>
      <div class="statsline" id="statsline">windows scored: 0 &middot; wakes: 0</div>
    </div>
  </div>
  <div>
    <div class="card"><h2>Class probabilities</h2><div id="probs"></div></div>
    <div class="card" style="margin-top:10px"><h2>Wake thresholds (per word)</h2>
      <div id="thrs"></div>
      <div class="thrlabel" style="margin-top:6px">Thresholds persist in localStorage and sync to the server. Wake = any wake word prob &ge; its threshold.</div>
    </div>
    <div class="card" style="margin-top:10px"><h2>Runtime</h2>
      <div id="modelinfo" class="thrlabel">connecting…</div>
      <div id="status" class="thrlabel">idle</div>
    </div>
  </div>
</div>
<script>
const SR = 16000;
const WIN_S = 5.92;
const WIN_SAMPLES = 94720;
const LABELS = ["Nova", "Piattos", "Negative"];
const WAKE = ["Nova", "Piattos"];

let ws = null;
let streamAcc = new Float32Array(0);
let rollFilled = 0;
let waveRing = new Float32Array(4096);
let ctxSR = 16000;
let actx = null;
let rmsHist = [];
let lastProbs = [0, 0, 0];
let wakeCount = 0;

let thr = { Nova: 0.5, Piattos: 0.5 };
try { const s = localStorage.getItem("gate1_thr"); if (s) thr = JSON.parse(s); } catch (e) {}
function saveThr() { try { localStorage.setItem("gate1_thr", JSON.stringify(thr)); } catch (e) {} }

const probsDiv = document.getElementById("probs"), thrsDiv = document.getElementById("thrs");
function buildBars() {
  probsDiv.innerHTML = "";
  LABELS.forEach(function (l) {
    const row = document.createElement("div"); row.className = "probrow";
    const nm = document.createElement("div"); nm.className = "probname"; nm.textContent = l;
    const wrap = document.createElement("div"); wrap.className = "probbarwrap";
    const bar = document.createElement("div"); bar.className = "probbar"; bar.id = "bar_" + l;
    wrap.appendChild(bar);
    const val = document.createElement("div"); val.className = "probval"; val.id = "val_" + l; val.textContent = "0.000";
    row.appendChild(nm); row.appendChild(wrap); row.appendChild(val); probsDiv.appendChild(row);
    if (l in thr) {
      const thrLabel = document.createElement("div"); thrLabel.className = "thrlabel";
      thrLabel.textContent = l + " wake threshold: " + thr[l].toFixed(2);
      const sl = document.createElement("input"); sl.type = "range"; sl.min = "0.05"; sl.max = "0.95"; sl.step = "0.01";
      sl.value = thr[l]; sl.className = "thr"; sl.id = "thr_" + l;
      sl.oninput = function () {
        thr[l] = parseFloat(sl.value);
        thrLabel.textContent = l + " wake threshold: " + thr[l].toFixed(2);
        saveThr(); drawLastProbs();
        if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "thr", thr: thr }));
      };
      thrsDiv.appendChild(thrLabel); thrsDiv.appendChild(sl);
    }
  });
}
function drawLastProbs() {
  LABELS.forEach(function (l, i) {
    const bar = document.getElementById("bar_" + l);
    bar.style.width = (lastProbs[i] * 100).toFixed(1) + "%";
    document.getElementById("val_" + l).textContent = lastProbs[i].toFixed(3);
    const isWake = WAKE.indexOf(l) >= 0 && lastProbs[i] >= thr[l];
    bar.style.background = isWake ? "#2ea043" : "#1f6feb";
  });
}

const logRows = [];
function addLog(ts, p, result) {
  logRows.push({ ts: ts, nova: p[0], piattos: p[1], negative: p[2], result: result });
  const box = document.getElementById("logbox");
  const d = document.createElement("div");
  d.textContent = ts + "  Nova=" + p[0].toFixed(3) + "  Piattos=" + p[1].toFixed(3) + "  Neg=" + p[2].toFixed(3) + "  -> " + result;
  if (result.indexOf("WAKE") === 0) d.style.color = "#3fb950";
  box.insertBefore(d, box.firstChild);
  while (box.childNodes.length > 300) box.removeChild(box.lastChild);
  const wakes = logRows.filter(function (r) { return r.result.indexOf("WAKE") === 0; }).length;
  document.getElementById("statsline").textContent = "windows scored: " + logRows.length + " · wakes: " + wakes;
}
function download(name, text) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  a.download = name; a.click();
}
document.getElementById("saveCsv").onclick = function () {
  let t = "timestamp,nova,piattos,negative,result\n";
  logRows.forEach(function (r) { t += r.ts + "," + r.nova.toFixed(6) + "," + r.piattos.toFixed(6) + "," + r.negative.toFixed(6) + "," + r.result + "\n"; });
  download("gate1_log.csv", t);
};
document.getElementById("saveJson").onclick = function () { download("gate1_log.json", JSON.stringify(logRows, null, 1)); };
document.getElementById("clearLog").onclick = function () { logRows.length = 0; document.getElementById("logbox").innerHTML = ""; };

const waveC = document.getElementById("wave").getContext("2d");
const levelC = document.getElementById("level").getContext("2d");
function drawWave() {
  const W = waveC.canvas.width, H = waveC.canvas.height;
  waveC.fillStyle = "#0d1117"; waveC.fillRect(0, 0, W, H);
  waveC.strokeStyle = "#1f6feb"; waveC.lineWidth = 1; waveC.beginPath();
  const tail = 4096;
  for (let x = 0; x < W; x++) {
    const idx = streamAcc.length - Math.floor((x / W) * tail);
    const v = streamAcc[Math.max(0, idx)];
    const y = H / 2 - v * (H / 2) * 4;
    if (x === 0) waveC.moveTo(x, Math.max(0, Math.min(H, y))); else waveC.lineTo(x, Math.max(0, Math.min(H, y)));
  }
  waveC.stroke();
}
function drawLevel() {
  const W = levelC.canvas.width, H = levelC.canvas.height;
  levelC.fillStyle = "#0d1117"; levelC.fillRect(0, 0, W, H);
  levelC.strokeStyle = "#30363d"; levelC.beginPath();
  [-60, -50, -40, -30, -20, -10].forEach(function (db) {
    const y = H - (db + 60) / 60 * H; levelC.moveTo(0, y); levelC.lineTo(W, y);
  });
  levelC.stroke();
  if (rmsHist.length > 1) {
    levelC.strokeStyle = "#2ea043"; levelC.lineWidth = 1.5; levelC.beginPath();
    rmsHist.forEach(function (db, i) {
      const x = i / (rmsHist.length - 1) * W; const y = H - (db + 60) / 60 * H;
      if (i === 0) levelC.moveTo(x, y); else levelC.lineTo(x, y);
    });
    levelC.stroke();
  }
}

const statusEl = document.getElementById("status");
function setStatus(t, isErr) {
  statusEl.textContent += t + "\n";
  statusEl.className = "thrlabel" + (isErr ? " err" : "");
  statusEl.scrollTop = statusEl.scrollHeight;
}

function pushAudio(f32) {
  if (ctxSR !== SR) {
    const ratio = ctxSR / SR;
    const out = new Float32Array(Math.floor(f32.length / ratio));
    for (let i = 0; i < out.length; i++) {
      const p = i * ratio; const i0 = Math.floor(p); const fr = p - i0;
      out[i] = f32[i0] * (1 - fr) + (f32[i0 + 1] || 0) * fr;
    }
    f32 = out;
  }
  const merged = new Float32Array(streamAcc.length + f32.length);
  merged.set(streamAcc); merged.set(f32, streamAcc.length);
  streamAcc = merged.slice(-WIN_SAMPLES);
  rollFilled = streamAcc.length;
  const r = rms(f32);
  rmsHist.push(20 * Math.log10(Math.max(r, 1e-10)));
  if (rmsHist.length > 120) rmsHist.shift();
}
function rms(x) { let s = 0; for (let i = 0; i < x.length; i++) s += x[i] * x[i]; return Math.sqrt(s / x.length); }

function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(proto + "://" + location.host + "/ws");
  ws.binaryType = "arraybuffer";
  ws.onopen = function () {
    setStatus("server connected. streaming mic…");
    ws.send(JSON.stringify({ type: "thr", thr: thr }));
  };
  ws.onmessage = function (ev) {
    let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
    if (d.type === "probs") {
      lastProbs = [d.nova, d.piattos, d.negative];
      let local = null;
      if (lastProbs[0] >= thr.Nova) local = "Nova";
      else if (lastProbs[1] >= thr.Piattos) local = "Piattos";
      const result = d.wake ? ("WAKE: " + d.wake) : "no-wake";
      addLog(d.ts, lastProbs, result);
      if (d.wake) {
        wakeCount++;
        banner.className = "wake";
        banner.textContent = "WAKE DETECTED: " + d.wake + " (" + Math.max(lastProbs[0], lastProbs[1]).toFixed(2) + ")";
      } else {
        banner.className = "listen";
        banner.textContent = "LISTENING FOR WAKE WORD…";
      }
      drawLastProbs();
    } else if (d.type === "status") {
      setStatus(d.text);
      if (d.text.indexOf("filling") === 0) banner.textContent = "FILLING FIRST WINDOW…";
    }
  };
  ws.onclose = function () {
    setStatus("server disconnected — retrying in 2s…");
    banner.className = "listen"; banner.textContent = "SERVER DISCONNECTED";
    setTimeout(connectWS, 2000);
  };
  ws.onerror = function () {};
}

const banner = document.getElementById("banner");
const modelinfo = document.getElementById("modelinfo");

async function startMic() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 }
  });
  actx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
  ctxSR = actx.sampleRate;
  modelinfo.textContent = "server-side inference: gate1v3_float32.tflite · 148-frame features (v3 stats) · " + actx.sampleRate + " Hz capture";
  const src = actx.createMediaStreamSource(stream);
  const proc = actx.createScriptProcessor(4096, 1, 1);
  proc.onaudioprocess = function (ev) {
    const inp = ev.inputBuffer.getChannelData(0);
    pushAudio(new Float32Array(inp));
    if (ws && ws.readyState === 1) ws.send(new Float32Array(inp));
  };
  src.connect(proc);
  proc.connect(actx.destination);
  setStatus("microphone live (" + ctxSR + " Hz). rolling " + WIN_S + "s window; inference every 1s.");
  setInterval(function () { drawWave(); drawLevel(); }, 100);
}

async function boot() {
  buildBars(); drawLastProbs();
  connectWS();
  try {
    await startMic();
  } catch (e) {
    setStatus("MIC ERROR: " + e.message, true);
    banner.textContent = "MIC ERROR";
  }
  if (actx && actx.state === "suspended") {
    const b = document.createElement("button");
    b.textContent = "Click to start audio";
    b.onclick = function () { actx.resume(); b.remove(); };
    document.body.insertBefore(b, banner);
  }
}

boot();
</script>
</body>
</html>
"""

out = HERE / "gate1_monitor.html"
out.write_text(HTML, encoding="utf-8")
print("wrote", out, f"({out.stat().st_size} bytes)")
