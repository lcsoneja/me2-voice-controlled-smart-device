(function () {
  "use strict";

  const SAMPLE_RATE = 16000;
  const WINDOW_SAMPLES = 94720;
  const thrDefaults = { Nova: 0.5, Piattos: 0.5, gate2MinConf: 0.5 };
  const listeners = Object.create(null);
  const logRows = { gate1: [], gate2: [], pipe: [] };
  let ws = null;
  let actx = null;

  function readJSON(key, fallback) {
    try {
      const value = localStorage.getItem(key);
      return value === null ? fallback : JSON.parse(value);
    } catch (e) {
      console.error("vcm: failed to read " + key + " from localStorage:", e);
      return fallback;
    }
  }

  function persist(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {
      console.error("vcm: failed to persist " + key + ":", e);
    }
  }

  const savedThr = readJSON("vcm_thr", {});
  const thr = Object.assign({}, thrDefaults);
  Object.keys(thrDefaults).forEach(function (key) {
    // Clamp restored thresholds to the valid slider range so a corrupt or
    // out-of-range saved value cannot disable wake/intent detection.
    if (savedThr && Number.isFinite(savedThr[key])) {
      thr[key] = Math.min(0.95, Math.max(0.05, savedThr[key]));
    }
  });

  const savedExpect = readJSON("vcm_expect", {});
  const expect = {
    gate2: savedExpect && Object.prototype.hasOwnProperty.call(savedExpect, "gate2") ? savedExpect.gate2 : null,
    pipe: savedExpect && Object.prototype.hasOwnProperty.call(savedExpect, "pipe") ? savedExpect.pipe : null
  };

  // Per-phrase Gate 2 activation thresholds (Option A): each intent's own
  // threshold opens its 4-second G2 window; phrases without a custom value
  // fall back to the global gate2MinConf.
  const thrG2 = (function () {
    const saved = readJSON("vcm_thr_g2", {});
    const out = {};
    Object.keys(saved || {}).forEach(function (key) {
      const value = Number(saved[key]);
      if (Number.isFinite(value)) out[key] = Math.min(0.95, Math.max(0.05, value));
    });
    return out;
  })();

  const state = {
    streamAcc: new Float32Array(0),
    ctxSR: SAMPLE_RATE,
    rmsHist: [],
    g1Hist: [],
    lastP1: null,
    lastP2: null,
    lastPipe: null,
    lastGated: null
  };

  const PHRASES = {
    G2: [["play some music", "PLAY_MUSIC"], ["what's the weather today", "WEATHER"], ["what time is it", "TIME"], ["turn on the lights", "LIGHT_ON"], ["turn off the lights", "LIGHT_OFF"], ["pause the music", "PAUSE"], ["stop", "STOP"], ["next song", "NEXT"], ["turn the volume up", "VOLUME_UP"], ["turn the volume down", "VOLUME_DOWN"], ["call mom", "CALL"], ["send a message to john", "MESSAGE"], ["list my reminders", "LIST_REMINDERS"], ["set a timer for 10 seconds", "TIMER"], ["set a timer for 30 seconds", "TIMER"], ["set a timer for 1 minute", "TIMER"], ["set an alarm for 6 am", "ALARM"], ["set an alarm for 8 am", "ALARM"], ["set an alarm for 9 pm", "ALARM"], ["set the temperature to 18 degrees", "TEMPERATURE"], ["set the temperature to 22 degrees", "TEMPERATURE"], ["set the temperature to 26 degrees", "TEMPERATURE"], ["set brightness to 20 percent", "BRIGHTNESS"], ["set brightness to 60 percent", "BRIGHTNESS"], ["set brightness to 100 percent", "BRIGHTNESS"], ["make the lights red", "COLOR"], ["make the lights blue", "COLOR"], ["make the lights green", "COLOR"], ["remind me to drink water", "CREATE_REMINDER"], ["remind me to study", "CREATE_REMINDER"], ["remind me to exercise", "CREATE_REMINDER"]],
    PIPE_WAKE: [["Nova", "Nova"], ["Piattos", "Piattos"]],
    PIPE_CMDS: [["play some music", "PLAY_MUSIC", ""], ["what's the weather today", "WEATHER", ""], ["what time is it", "TIME", ""], ["turn on the lights", "LIGHT_ON", ""], ["turn off the lights", "LIGHT_OFF", ""], ["pause the music", "PAUSE", ""], ["stop", "STOP", ""], ["next song", "NEXT", ""], ["turn the volume up", "VOLUME_UP", ""], ["turn the volume down", "VOLUME_DOWN", ""], ["call mom", "CALL", ""], ["send a message to john", "MESSAGE", ""], ["list my reminders", "LIST_REMINDERS", ""], ["set a timer for 10 seconds", "TIMER", "10 seconds"], ["set a timer for 30 seconds", "TIMER", "30 seconds"], ["set a timer for 1 minute", "TIMER", "1 minute"], ["set an alarm for 6 am", "ALARM", "6 AM"], ["set an alarm for 8 am", "ALARM", "8 AM"], ["set an alarm for 9 pm", "ALARM", "9 PM"], ["set the temperature to 18 degrees", "TEMPERATURE", "18 degrees"], ["set the temperature to 22 degrees", "TEMPERATURE", "22 degrees"], ["set the temperature to 26 degrees", "TEMPERATURE", "26 degrees"], ["set brightness to 20 percent", "BRIGHTNESS", "20 percent"], ["set brightness to 60 percent", "BRIGHTNESS", "60 percent"], ["set brightness to 100 percent", "BRIGHTNESS", "100 percent"], ["make the lights red", "COLOR", "Red"], ["make the lights blue", "COLOR", "Blue"], ["make the lights green", "COLOR", "Green"], ["remind me to drink water", "CREATE_REMINDER", "Drink water"], ["remind me to study", "CREATE_REMINDER", "Study"], ["remind me to exercise", "CREATE_REMINDER", "Exercise"]]
  };

  function send(obj) {
    if (!ws || ws.readyState !== 1) return false;
    try {
      ws.send(JSON.stringify(obj));
      return true;
    } catch (e) {
      console.error("vcm: ws.send failed:", e);
      return false;
    }
  }

  function on(type, fn) {
    if (typeof fn !== "function") return function () {};
    (listeners[type] || (listeners[type] = [])).push(fn);
    return function () {
      const group = listeners[type];
      if (!group) return;
      const index = group.indexOf(fn);
      if (index >= 0) group.splice(index, 1);
    };
  }

  function emit(type, message) {
    (listeners[type] || []).slice().forEach(function (fn) {
      try { fn(message); } catch (e) { console.error(e); }
    });
  }

  function setThr(key, value) {
    if (!Object.prototype.hasOwnProperty.call(thr, key)) return;
    const next = Number(value);
    if (!Number.isFinite(next)) return;
    thr[key] = next;
    persist("vcm_thr", thr);
    const slider = document.getElementById("thr_" + key);
    if (slider) slider.value = String(next);
    send({ type: "thr", thr: thr });
    drawG1Chart();
  }

  function getThrG2(intent) {
    const value = thrG2[intent];
    return Number.isFinite(value) ? value : thr.gate2MinConf;
  }

  function setThrG2(intent, value) {
    const next = Number(value);
    if (!intent || !Number.isFinite(next)) return;
    thrG2[intent] = Math.min(0.95, Math.max(0.05, next));
    persist("vcm_thr_g2", thrG2);
    send({ type: "thr", thr: Object.assign({}, thr, { g2thr: thrG2 }) });
  }

  function setExpect(tab, value) {
    if (tab !== "gate2" && tab !== "pipe") return;
    expect[tab] = value === null ? null : Object.assign({}, value);
    persist("vcm_expect", expect);
  }

  function setStatus(text, isErr) {
    const status = document.getElementById("status");
    if (!status) return;
    const line = document.createElement("div");
    line.textContent = String(text);
    if (isErr) line.className = "err";
    status.appendChild(line);
    status.scrollTop = status.scrollHeight;
  }

  function log(tab, text, cls) {
    if (!Object.prototype.hasOwnProperty.call(logRows, tab)) return;
    const row = { ts: new Date().toISOString(), text: String(text), cls: cls || "" };
    logRows[tab].push(row);
    const box = document.getElementById(tab === "gate1" ? "g1log" : tab === "gate2" ? "g2log" : "pipelog");
    if (!box) return;
    const line = document.createElement("div");
    line.textContent = row.text;
    if (row.cls) line.className = row.cls;
    box.insertBefore(line, box.firstChild);
  }

  function download(name, text, mime) {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    anchor.click();
    setTimeout(function () { URL.revokeObjectURL(url); }, 0);
  }

  function exportLog(tab, fmt) {
    const rows = logRows[tab];
    if (!rows || (fmt !== "csv" && fmt !== "json")) return;
    let body;
    if (fmt === "json") {
      body = JSON.stringify(rows, null, 2);
    } else {
      function csv(value) { return '"' + String(value).replace(/"/g, '""') + '"'; }
      body = "timestamp,text,class\n" + rows.map(function (row) {
        return [row.ts, row.text, row.cls].map(csv).join(",");
      }).join("\n");
      if (rows.length) body += "\n";
    }
    download(tab + "_log." + fmt, body, fmt === "csv" ? "text/csv" : "application/json");
  }

  const VCM = {
    send: send,
    on: on,
    thr: thr,
    setThr: setThr,
    getThrG2: getThrG2,
    setThrG2: setThrG2,
    pushG1Reading: null, // bound below, after the chart engine is defined
    drawG1Chart: null,
    expect: expect,
    setExpect: setExpect,
    log: log,
    exportLog: exportLog,
    setStatus: setStatus,
    PHRASES: PHRASES,
    state: state
  };
  VCM.inject = function (samples) {
    pushAudio(samples);
    if (ws && ws.readyState === 1) {
      ws.send(samples);
    }
  };
  window.VCM = VCM;

  function makeBar(label) {
    const row = document.createElement("div");
    row.className = "probrow";
    const name = document.createElement("div");
    name.className = "probname";
    name.textContent = label;
    const wrap = document.createElement("div");
    wrap.className = "probbarwrap";
    const bar = document.createElement("div");
    bar.className = "probbar";
    bar.id = "bar_" + label;
    wrap.appendChild(bar);
    const value = document.createElement("div");
    value.className = "probval";
    value.id = "val_" + label;
    value.textContent = "0.000";
    row.appendChild(name);
    row.appendChild(wrap);
    row.appendChild(value);
    return row;
  }

  function getLatestRms() {
    if (state.streamAcc && state.streamAcc.length > 0) {
      return rms(state.streamAcc);
    }
    if (state.rmsHist && state.rmsHist.length > 0) {
      var recent = state.rmsHist.slice(-23);
      var sumPower = 0;
      for (var i = 0; i < recent.length; i++) {
        sumPower += Math.pow(10, recent[i] / 10);
      }
      return Math.sqrt(sumPower / Math.max(1, recent.length));
    }
    return 0;
  }

  function deriveGate1State(message) {
    var hasProbs = message && (Number.isFinite(Number(message.nova)) || Number.isFinite(Number(message.negative)));
    if (!hasProbs) {
      if (state.lastGated) return "SILENCE";
      return "—";
    }
    // The server's wake field is already energy-gated and 2-of-3 latched.
    // Do not infer WAKE directly from a high raw probability here: v8 has no
    // silence class and can score Nova highly on silence.
    var floor = (message && Number.isFinite(Number(message.floor))) ? Number(message.floor)
      : ((state.lastGated && Number.isFinite(state.lastGated.floor)) ? state.lastGated.floor : 0.005);
    var winRms = (message && Number.isFinite(Number(message.rms))) ? Number(message.rms) : getLatestRms();

    if (winRms < floor) {
      return "SILENCE";
    }
    if (message.wake) {
      return "WAKE";
    }

    // Above floor but no server-confirmed wake: this is unclassified audio.
    return "AUDIO (unclassified)";
  }

  function updateGate1Derived(status) {
    var chip = document.getElementById("g1derived");
    if (!chip) return;
    chip.setAttribute("data-state", status);
    if (status === "WAKE") {
      chip.className = "chip sel ok";
      chip.style.background = "#1a7f37";
      chip.style.borderColor = "#2ea043";
      chip.style.color = "#fff";
      chip.textContent = "WAKE";
    } else if (status === "SPEECH (rejected)") {
      chip.className = "chip err";
      chip.style.background = "#21262d";
      chip.style.borderColor = "#f85149";
      chip.style.color = "#f85149";
      chip.textContent = "SPEECH (rejected)";
    } else if (status === "SILENCE") {
      chip.className = "chip";
      chip.style.background = "#21262d";
      chip.style.borderColor = "#30363d";
      chip.style.color = "#8b949e";
      chip.textContent = "SILENCE";
    } else {
      chip.className = "chip";
      chip.style.background = "#21262d";
      chip.style.borderColor = "#30363d";
      chip.style.color = "#8b949e";
      chip.textContent = status || "—";
    }
  }

  function makeDerivedRow() {
    var row = document.createElement("div");
    row.className = "probrow";
    row.id = "row_g1derived";
    row.style.marginTop = "6px";
    row.style.paddingTop = "6px";
    row.style.borderTop = "1px solid #21262d";

    var name = document.createElement("div");
    name.className = "probname thrlabel";
    name.style.width = "125px";
    name.textContent = "SILENCE / SPEECH";

    var wrap = document.createElement("div");
    wrap.id = "val_g1derived";
    wrap.style.flex = "1";
    wrap.style.display = "flex";
    wrap.style.alignItems = "center";

    var chip = document.createElement("span");
    chip.id = "g1derived";
    chip.className = "chip";
    chip.style.margin = "0";
    chip.style.cursor = "default";
    chip.textContent = "—";

    wrap.appendChild(chip);
    row.appendChild(name);
    row.appendChild(wrap);
    return row;
  }

  function renderGate1() {
    const bars = document.getElementById("g1bars");
    if (!bars) return;
    bars.innerHTML = "";
    ["Nova", "Piattos", "Negative"].forEach(function (label) { bars.appendChild(makeBar(label)); });
    // Gate 1 model chooser: version x precision (server swap via {type:"model"}).
    const modelSel = document.getElementById("g1model");
    if (modelSel && !modelSel.dataset.bound) {
      modelSel.dataset.bound = "1";
      ["v8", "v2", "v3", "v4", "v5"].forEach(function (ver) {
        ["f32", "f16"].forEach(function (prec) {
          const opt = document.createElement("option");
          opt.value = "gate1" + ver + "_" + prec;
          opt.textContent = "Gate 1 " + ver.toUpperCase() + (ver === "v8" ? " · main" : "") + " · " + (prec === "f32" ? "float32" : "float16");
          modelSel.appendChild(opt);
        });
      });
      modelSel.value = "gate1v8_f32";
      modelSel.addEventListener("change", function () {
        VCM.send({ type: "model", model: modelSel.value });
        const info = document.getElementById("g1modelinfo");
        if (info) info.textContent = "requested: " + modelSel.value;
        g1Hist.length = 0;
        drawG1Chart();
      });
    }
    bars.appendChild(makeDerivedRow());

    ["Nova", "Piattos"].forEach(function (key) {
      const slider = document.getElementById("thr_" + key);
      if (!slider) return;
      slider.value = String(thr[key]);
      slider.addEventListener("input", function () { setThr(key, slider.value); });
    });

    const values = state.lastP1 || {};
    drawGate1(values);
    [
      ["g1saveCsv", "csv"], ["g1saveJson", "json"]
    ].forEach(function (item) {
      const button = document.getElementById(item[0]);
      if (button) button.addEventListener("click", function () { exportLog("gate1", item[1]); });
    });
    const clear = document.getElementById("g1clear");
    if (clear) clear.addEventListener("click", function () {
      logRows.gate1.length = 0;
      const box = document.getElementById("g1log");
      if (box) box.innerHTML = "";
    });
  }

  function drawGate1(message) {
    // Dynamic label set: 3-class variants (Nova/Piattos/Negative) vs 2-class
    // (v5: Nova/Piattos). Rows for labels absent from the active model hide.
    const activeLabels = (message.labels && message.labels.length) ? message.labels : ["Nova", "Piattos", "Negative"];
    const values = [Number(message.nova) || 0, Number(message.piattos) || 0, Number(message.negative) || 0];
    ["Nova", "Piattos", "Negative"].forEach(function (label, index) {
      const bar = document.getElementById("bar_" + label);
      const value = document.getElementById("val_" + label);
      if (!bar || !value) return;
      const row = bar.closest(".probrow");
      if (row) row.style.display = activeLabels.indexOf(label) !== -1 ? "" : "none";
      bar.style.width = (values[index] * 100).toFixed(1) + "%";
      bar.style.background = label !== "Negative" && values[index] >= thr[label] ? "#2ea043" : "#1f6feb";
      value.textContent = values[index].toFixed(3);
    });
    const modelEl = document.getElementById("g1modelinfo");
    if (modelEl) modelEl.textContent = "active model: " + (message.model || "gate1v5_f32");
    updateGate1Derived(deriveGate1State(message));
  }

  // ---- Probability-over-time line chart (threshold-anchored) ----
  const G1_CHART_MAX = 180; // 3 minutes at 1 inference/second
  const g1Hist = state.g1Hist; // exposed on state for test probing
  function pushG1Hist(message) {
    g1Hist.push({
      nova: Number(message.nova) || 0,
      piattos: Number(message.piattos) || 0,
      negative: message.negative == null ? null : Number(message.negative) || 0
    });
    if (g1Hist.length > G1_CHART_MAX) g1Hist.shift();
  }
  function chartY(value, height) {
    return height - 7 - Math.max(0, Math.min(1, value)) * (height - 14);
  }
  function drawG1Chart() {
    ["g1chart", "g1chart_pipe"].forEach(function (id) {
      const canvas = document.getElementById(id);
      if (canvas) drawG1ChartOn(canvas);
    });
  }

  function drawG1ChartOn(canvas) {
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.fillStyle = "#0d1117";
    ctx.fillRect(0, 0, W, H);
    // Horizontal grid with 0..1 axis labels
    [0, 0.25, 0.5, 0.75, 1].forEach(function (v) {
      const y = chartY(v, H);
      ctx.strokeStyle = "#21262d";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.stroke();
      ctx.fillStyle = "#8b949e";
      ctx.font = "10px Consolas,monospace";
      ctx.textAlign = "left";
      ctx.fillText(v.toFixed(2), 2, Math.max(10, y - 2));
    });
    // Dashed threshold lines — move live with the sliders
    ctx.setLineDash([4, 4]);
    [["Nova", "#f85149"], ["Piattos", "#d29922"]].forEach(function (item) {
      const y = chartY(thr[item[0]], H);
      ctx.strokeStyle = item[1];
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.stroke();
    });
    ctx.setLineDash([]);
    // Probability series (right-aligned, scrolling left)
    if (g1Hist.length >= 2) {
      [["negative", "#8b949e"], ["piattos", "#a371f7"], ["nova", "#1f6feb"]].forEach(function (item) {
        const key = item[0];
        ctx.strokeStyle = item[1];
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        let started = false;
        for (let i = 0; i < g1Hist.length; i++) {
          const v = g1Hist[i][key];
          if (v == null) { started = false; continue; }
          const x = W - (g1Hist.length - 1 - i) / (G1_CHART_MAX - 1) * W;
          const y = chartY(v, H);
          if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
        }
        ctx.stroke();
      });
    }
    // Legend (top-right)
    ctx.font = "10px Consolas,monospace";
    ctx.textAlign = "right";
    let lx = W - 4;
    [["Nova", "#1f6feb"], ["Piattos", "#a371f7"], ["Negative", "#8b949e"]].forEach(function (item) {
      ctx.fillStyle = item[1];
      ctx.fillText(item[0], lx, 10);
      lx -= ctx.measureText(item[0]).width + 14;
    });
  }

  VCM.pushG1Reading = pushG1Hist;
  VCM.drawG1Chart = drawG1Chart;

  function updateBanner(wake, message) {
    const banner = document.getElementById("banner");
    if (!banner) return;
    if (wake) {
      const confidence = wake === "Nova" ? Number(message.nova) || 0 : Number(message.piattos) || 0;
      banner.className = "wake";
      banner.textContent = "WAKE DETECTED: " + wake + " (" + confidence.toFixed(2) + ")";
    } else {
      banner.className = "listen";
      banner.textContent = "LISTENING FOR WAKE WORD…";
    }
  }

  function handleMessage(message) {
    if (!message || typeof message !== "object") return;
    if (message.type === "status") {
      setStatus(message.text);
      emit("status", message);
    } else if (message.type === "probs") {
      state.lastP1 = message;
      drawGate1(message);
      pushG1Hist(message);
      drawG1Chart();
      updateBanner(message.wake, message);
      const outcome = message.wake ? "WAKE: " + message.wake : "no-wake";
      const text = String(message.ts || new Date().toISOString()) + "  Nova=" + (Number(message.nova) || 0).toFixed(3) + "  Piattos=" + (Number(message.piattos) || 0).toFixed(3) + "  Neg=" + (Number(message.negative) || 0).toFixed(3) + "  -> " + outcome;
      log("gate1", text, message.wake ? "ok" : "");
      emit("probs", message);
    } else if (message.type === "probs2") {
      state.lastP2 = message;
      emit("probs2", message);
    } else if (message.type === "pipe") {
      state.lastPipe = message;
      const banner = document.getElementById("banner");
      const g1 = message.g1 || {};
      if (banner) {
        if (g1.label && String(g1.label).toLowerCase().indexOf("calibrat") >= 0) {
          banner.className = "listen";
          banner.textContent = "CALIBRATING ROOM — PLEASE STAY QUIET";
        } else if (g1.active && (g1.activation_label || g1.wake)) {
          banner.className = "wake";
          banner.textContent = "WAKE ACTIVE: " + (g1.activation_label || g1.wake) + " (" + Number(g1.activation_conf || 0).toFixed(2) + ")";
        } else if (g1.label && String(g1.label).indexOf("gated") === 0) {
          banner.className = "listen";
          banner.textContent = "QUIET ROOM — LISTENING FOR WAKE WORD";
        } else {
          banner.className = "listen";
          banner.textContent = "LISTENING FOR WAKE WORD…";
        }
      }
      emit("pipe", message);
    } else if (message.type === "gated") {
      state.lastGated = message;
      updateGate1Derived("SILENCE");
      emit("gated", message);
    } else {
      emit(message.type, message);
    }
  }

  function serverModeForTab(mode) {
    if (mode === "pipe") return "both";
    if (mode === "pipe2") return "both";
    if (mode === "parallel") return "parallel";
    if (mode === "gate2") return "gate2";
    return "gate1";
  }

  function activeServerMode() {
    const active = document.querySelector(".tab[data-tab].active");
    const mode = active ? active.getAttribute("data-tab") : "gate1";
    return serverModeForTab(mode);
  }

  function bindTabs() {
    document.querySelectorAll(".tab[data-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        const mode = tab.getAttribute("data-tab");
        document.querySelectorAll(".tab[data-tab]").forEach(function (item) {
          item.classList.toggle("active", item === tab);
        });
        ["gate1", "gate2", "pipe", "pipe2", "parallel", "metrics", "gate3to5"].forEach(function (name) {
          const section = document.getElementById("sec-" + name);
          if (section) section.classList.toggle("active", name === mode);
        });
        send({ type: "mode", mode: serverModeForTab(mode) });
      });
    });
  }

  const waveCanvas = document.getElementById("wave");
  const levelCanvas = document.getElementById("level");

  function drawWave() {
    if (!waveCanvas) return;
    const context = waveCanvas.getContext("2d");
    if (!context) return;
    const width = waveCanvas.width;
    const height = waveCanvas.height;
    context.fillStyle = "#0d1117";
    context.fillRect(0, 0, width, height);
    context.strokeStyle = "#1f6feb";
    context.lineWidth = 1;
    context.beginPath();
    const samples = state.streamAcc.subarray(Math.max(0, state.streamAcc.length - 4096));
    for (let x = 0; x < width; x++) {
      const index = samples.length ? Math.min(samples.length - 1, Math.floor(x / Math.max(1, width - 1) * samples.length)) : 0;
      const sample = samples.length ? samples[index] : 0;
      const y = Math.max(0, Math.min(height, height / 2 - sample * height * 2));
      if (x === 0) context.moveTo(x, y); else context.lineTo(x, y);
    }
    context.stroke();
  }

  function drawLevel() {
    if (!levelCanvas) return;
    const context = levelCanvas.getContext("2d");
    if (!context) return;
    const width = levelCanvas.width;
    const height = levelCanvas.height;
    context.fillStyle = "#0d1117";
    context.fillRect(0, 0, width, height);
    context.strokeStyle = "#30363d";
    context.lineWidth = 1;
    context.beginPath();
    [-60, -50, -40, -30, -20, -10, 0].forEach(function (db) {
      const y = height - (db + 60) / 60 * height;
      context.moveTo(0, y);
      context.lineTo(width, y);
    });
    context.stroke();
    if (state.rmsHist.length < 2) return;
    context.strokeStyle = "#2ea043";
    context.lineWidth = 1.5;
    context.beginPath();
    state.rmsHist.forEach(function (db, index) {
      const x = index / (state.rmsHist.length - 1) * width;
      const y = height - (Math.max(-60, Math.min(0, db)) + 60) / 60 * height;
      if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
    });
    context.stroke();
  }

  function rms(samples) {
    if (!samples.length) return 0;
    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    return Math.sqrt(sum / samples.length);
  }

  function to16k(samples) {
    if (state.ctxSR === SAMPLE_RATE) return new Float32Array(samples);
    const ratio = state.ctxSR / SAMPLE_RATE;
    const count = Math.floor(samples.length / ratio);
    const output = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const position = i * ratio;
      const left = Math.floor(position);
      const fraction = position - left;
      const right = Math.min(left + 1, samples.length - 1);
      output[i] = samples[left] * (1 - fraction) + samples[right] * fraction;
    }
    return output;
  }

  function pushAudio(samples) {
    const chunk = to16k(samples);
    const joined = new Float32Array(state.streamAcc.length + chunk.length);
    joined.set(state.streamAcc);
    joined.set(chunk, state.streamAcc.length);
    state.streamAcc = joined.length > WINDOW_SAMPLES ? joined.slice(joined.length - WINDOW_SAMPLES) : joined;
    const db = 20 * Math.log10(Math.max(rms(chunk), 1e-10));
    state.rmsHist.push(db);
    if (state.rmsHist.length > 120) state.rmsHist.shift();
    return chunk;
  }

  let initializedG2 = false;
  let initializedPipe = false;
  let initializedParallel = false;
  let openedOnce = false;

  function initializeDependents() {
    if (!initializedG2 && window.VCMG2 && typeof window.VCMG2.init === "function") {
      window.VCMG2.init();
      initializedG2 = true;
    }
    if (!initializedPipe && window.VCMPIPE && typeof window.VCMPIPE.init === "function") {
      window.VCMPIPE.init();
      initializedPipe = true;
    }
    if (!initializedParallel && window.VCMPARALLEL && typeof window.VCMPARALLEL.init === "function") {
      window.VCMPARALLEL.init();
      initializedParallel = true;
    }
  }

  function connectWS() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    try {
      ws = new WebSocket(protocol + "//" + window.location.host + "/ws");
      ws.binaryType = "arraybuffer";
    } catch (error) {
      setStatus("WebSocket error: " + error.message, true);
      setTimeout(connectWS, 2000);
      return;
    }

    ws.onopen = function () {
      setStatus("server connected. streaming mic…");
      updateBanner(null, {});
      send({ type: "thr", thr: Object.assign({}, thr, { g2thr: thrG2 }) });
      send({ type: "mode", mode: activeServerMode() });
      const modelSel = document.getElementById("g1model");
      if (modelSel && modelSel.value) send({ type: "model", model: modelSel.value });
      if (!openedOnce) {
        openedOnce = true;
        try { initializeDependents(); } catch (error) { setStatus("Tab initialization error: " + error.message, true); }
      }
    };
    ws.onmessage = function (event) {
      try { handleMessage(JSON.parse(event.data)); } catch (error) {
        console.error("vcm: failed to handle server message:", error, event.data);
      }
    };
    ws.onclose = function () {
      setStatus("server disconnected — retrying in 2s…");
      const banner = document.getElementById("banner");
      if (banner) {
        banner.className = "listen";
        banner.textContent = "SERVER DISCONNECTED";
      }
      setTimeout(connectWS, 2000);
    };
    ws.onerror = function () {};
  }

  async function startMic() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 }
    });
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    actx = new AudioContextClass({ sampleRate: SAMPLE_RATE });
    state.ctxSR = actx.sampleRate;
    const source = actx.createMediaStreamSource(stream);
    const processor = actx.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = function (event) {
      const chunk = pushAudio(event.inputBuffer.getChannelData(0));
      if (ws && ws.readyState === 1) ws.send(chunk.buffer);
    };
    source.connect(processor);
    processor.connect(actx.destination);
    setStatus("microphone live (" + state.ctxSR + " Hz). rolling 5.92s window; inference every 1s.");
    if (actx.state === "suspended") {
      const button = document.createElement("button");
      button.textContent = "Click to start audio";
      button.addEventListener("click", function () {
        actx.resume();
        button.remove();
      });
      document.body.insertBefore(button, document.getElementById("banner"));
    }
  }

  renderGate1();
  bindTabs();
  connectWS();
  setInterval(function () {
    drawWave();
    drawLevel();
  }, 100);
  startMic().catch(function (error) {
    setStatus("MIC ERROR: " + error.message, true);
    const banner = document.getElementById("banner");
    if (banner) {
      banner.className = "listen";
      banner.textContent = "MIC ERROR";
    }
  });
})();
