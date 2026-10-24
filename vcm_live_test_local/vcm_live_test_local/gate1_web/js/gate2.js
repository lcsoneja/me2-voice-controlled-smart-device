(function () {
  "use strict";

  const G2_INTENTS_FALLBACK = [
    "PLAY_MUSIC",
    "WEATHER",
    "TIME",
    "LIGHT_ON",
    "LIGHT_OFF",
    "PAUSE",
    "STOP",
    "NEXT",
    "VOLUME_UP",
    "VOLUME_DOWN",
    "CALL",
    "MESSAGE",
    "LIST_REMINDERS",
    "TIMER",
    "ALARM",
    "TEMPERATURE",
    "BRIGHTNESS",
    "COLOR",
    "CREATE_REMINDER"
  ];

  let subscribed = false;
  let windowsScored = 0;

  // ---- Compact confidence-over-time chart (threshold-anchored) ----
  const G2_CHART_MAX = 180; // 3 minutes at 1 inference/second
  const g2History = [];

  function selectedChartPhrase() {
    const sel = document.getElementById("g2phrase");
    return sel && sel.value ? sel.value : null;
  }

  function pushG2Reading(message) {
    const probs = message && message.probs ? Object.assign({}, message.probs) : {};
    if (!Object.keys(probs).length) return;
    g2History.push({ probs: probs, top: message.top || null });
    if (g2History.length > G2_CHART_MAX) g2History.shift();
  }

  function chartY(v, H) { return H - 7 - Math.max(0, Math.min(1, v)) * (H - 14); }

  function drawG2ChartOn(canvas, phrase, phraseThr, globalThr) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.fillStyle = "#0d1117";
    ctx.fillRect(0, 0, W, H);
    [0, 0.25, 0.5, 0.75, 1].forEach(function (v) {
      const y = chartY(v, H);
      ctx.strokeStyle = "#21262d";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
      ctx.fillStyle = "#8b949e";
      ctx.font = "9px Consolas,monospace";
      ctx.textAlign = "left";
      ctx.fillText(v.toFixed(2), 2, Math.max(9, y - 2));
    });
    // Dashed thresholds: red = selected phrase's activation threshold,
    // amber = global Gate 2 min confidence fallback.
    ctx.setLineDash([4, 4]);
    if (Number.isFinite(globalThr)) {
      ctx.strokeStyle = "#d29922";
      ctx.beginPath(); ctx.moveTo(0, chartY(globalThr, H)); ctx.lineTo(W, chartY(globalThr, H)); ctx.stroke();
    }
    if (Number.isFinite(phraseThr)) {
      ctx.strokeStyle = "#f85149";
      ctx.beginPath(); ctx.moveTo(0, chartY(phraseThr, H)); ctx.lineTo(W, chartY(phraseThr, H)); ctx.stroke();
    }
    ctx.setLineDash([]);
    if (g2History.length >= 2) {
      [["__top__", "#1f6feb"], [phrase || "__none__", "#a371f7"]].forEach(function (item) {
        const key = item[0];
        ctx.strokeStyle = item[1];
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        let started = false;
        for (let i = 0; i < g2History.length; i++) {
          const probs = g2History[i].probs;
          let v;
          if (key === "__top__") {
            v = g2History[i].top ? (Number(probs[g2History[i].top]) || 0) : null;
          } else {
            const raw = probs[key];
            v = raw === undefined || raw === null ? null : (Number(raw) || 0);
          }
          if (v === null) { started = false; continue; }
          const x = W - (g2History.length - 1 - i) / (G2_CHART_MAX - 1) * W;
          const y = chartY(v, H);
          if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
        }
        ctx.stroke();
      });
    }
    ctx.font = "9px Consolas,monospace";
    ctx.textAlign = "right";
    let lx = W - 4;
    const legend = [["top", "#1f6feb"]];
    if (phrase) legend.push([phrase, "#a371f7"]);
    legend.forEach(function (item) {
      ctx.fillStyle = item[1];
      ctx.fillText(item[0], lx, 9);
      lx -= ctx.measureText(item[0]).width + 12;
    });
  }

  function drawG2Charts() {
    const phrase = selectedChartPhrase();
    const globalThr = (window.VCM && window.VCM.thr && Number.isFinite(window.VCM.thr.gate2MinConf))
      ? window.VCM.thr.gate2MinConf : null;
    const phraseThr = (phrase && window.VCM && typeof window.VCM.getThrG2 === "function")
      ? window.VCM.getThrG2(phrase) : null;
    ["g2chart", "g2chart_pipe"].forEach(function (id) {
      drawG2ChartOn(document.getElementById(id), phrase, phraseThr, globalThr);
    });
  }

  function syncPhraseSlider() {
    const sel = document.getElementById("g2phrase");
    const slider = document.getElementById("thr_g2phrase");
    if (!sel || !slider || !sel.value) return;
    const value = (window.VCM && typeof window.VCM.getThrG2 === "function") ? window.VCM.getThrG2(sel.value) : 0.5;
    slider.value = String(value);
  }

  function selectChartPhrase(intent) {
    const sel = document.getElementById("g2phrase");
    if (!sel || !intent) return;
    sel.value = intent;
    syncPhraseSlider();
    drawG2Charts();
  }

  function bindChartControls() {
    const sel = document.getElementById("g2phrase");
    if (sel && sel.dataset.bound !== "1") {
      sel.dataset.bound = "1";
      getUniqueIntents().forEach(function (intent) {
        const opt = document.createElement("option");
        opt.value = intent;
        opt.textContent = intent;
        sel.appendChild(opt);
      });
      sel.addEventListener("change", function () { syncPhraseSlider(); drawG2Charts(); });
    }
    const slider = document.getElementById("thr_g2phrase");
    if (slider && slider.dataset.bound !== "1") {
      slider.dataset.bound = "1";
      slider.addEventListener("input", function () {
        const sel2 = document.getElementById("g2phrase");
        if (sel2 && sel2.value && window.VCM && typeof window.VCM.setThrG2 === "function") {
          window.VCM.setThrG2(sel2.value, parseFloat(slider.value));
          drawG2Charts();
        }
      });
    }
    const exp = window.VCM && window.VCM.expect ? window.VCM.expect.gate2 : null;
    if (exp && exp.intent) selectChartPhrase(exp.intent);
  }

  function getUniqueIntents() {
    const phrases = (window.VCM && window.VCM.PHRASES && Array.isArray(window.VCM.PHRASES.G2))
      ? window.VCM.PHRASES.G2
      : null;
    if (!phrases) return G2_INTENTS_FALLBACK.slice();

    const unique = [];
    for (let i = 0; i < phrases.length; i++) {
      const intent = phrases[i][1];
      if (intent && unique.indexOf(intent) === -1) {
        unique.push(intent);
      }
    }
    return unique.length ? unique : G2_INTENTS_FALLBACK.slice();
  }

  function makeBar(intent) {
    const row = document.createElement("div");
    row.className = "probrow";

    const name = document.createElement("div");
    name.className = "probname";
    name.textContent = intent;

    const wrap = document.createElement("div");
    wrap.className = "probbarwrap";

    const bar = document.createElement("div");
    bar.className = "probbar";
    bar.id = "bar_" + intent;
    wrap.appendChild(bar);

    const val = document.createElement("div");
    val.className = "probval";
    val.id = "val_" + intent;
    val.textContent = "0.000";

    row.appendChild(name);
    row.appendChild(wrap);
    row.appendChild(val);
    return row;
  }

  function renderBars() {
    const container = document.getElementById("g2bars");
    if (!container) return;
    container.innerHTML = "";
    const intents = getUniqueIntents();
    for (let i = 0; i < intents.length; i++) {
      container.appendChild(makeBar(intents[i]));
    }
  }

  function updateExpected(intent) {
    if (intent === undefined) {
      const exp = window.VCM && window.VCM.expect ? window.VCM.expect.gate2 : null;
      intent = exp && exp.intent ? exp.intent : null;
    }

    const expEl = document.getElementById("g2expected");
    if (expEl) {
      expEl.textContent = intent || "none";
    }

    const verdictEl = document.getElementById("g2verdict");
    if (!verdictEl) return;

    if (!intent) {
      verdictEl.className = "verdict v-idle";
      verdictEl.textContent = "no phrase selected";
      return;
    }

    if (window.VCM && window.VCM.state && window.VCM.state.lastP2) {
      const last = window.VCM.state.lastP2;
      const top = last.top || "";
      const conf = (typeof last.conf === "number") ? last.conf : Number(last.conf) || 0;
      let minConf = 0.5;
      if (window.VCM && typeof window.VCM.getThrG2 === "function" && intent) minConf = window.VCM.getThrG2(intent);
      else if (window.VCM && window.VCM.thr && typeof window.VCM.thr.gate2MinConf === "number") minConf = window.VCM.thr.gate2MinConf;

      let v = "FAIL";
      let cls = "v-fail";
      if (top === intent) {
        if (conf >= minConf) {
          v = "PASS";
          cls = "v-pass";
        } else {
          v = "LOW";
          cls = "v-low";
        }
      }
      verdictEl.className = "verdict " + cls;
      verdictEl.textContent = v;
    }
  }

  function renderChips() {
    const container = document.getElementById("g2chips");
    if (!container) return;
    container.innerHTML = "";

    const phrases = (window.VCM && window.VCM.PHRASES && Array.isArray(window.VCM.PHRASES.G2))
      ? window.VCM.PHRASES.G2
      : [];

    const exp = window.VCM && window.VCM.expect ? window.VCM.expect.gate2 : null;
    const currentIntent = exp && exp.intent ? exp.intent : null;
    let selectedFound = false;

    for (let i = 0; i < phrases.length; i++) {
      const pair = phrases[i];
      const phrase = pair[0];
      const intent = pair[1];

      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = phrase;

      if (currentIntent && intent === currentIntent && !selectedFound) {
        chip.classList.add("sel");
        selectedFound = true;
      }

      chip.addEventListener("click", function () {
        const all = container.querySelectorAll(".chip");
        for (let j = 0; j < all.length; j++) {
          all[j].classList.remove("sel");
        }
        chip.classList.add("sel");

        if (window.VCM && typeof window.VCM.setExpect === "function") {
          window.VCM.setExpect("gate2", { intent: intent });
        }
        updateExpected(intent);
        selectChartPhrase(intent);
      });

      container.appendChild(chip);
    }

    const clearChip = document.createElement("span");
    clearChip.className = "chip";
    clearChip.textContent = "Clear";
    clearChip.addEventListener("click", function () {
      const all = container.querySelectorAll(".chip");
      for (let j = 0; j < all.length; j++) {
        all[j].classList.remove("sel");
      }

      if (window.VCM && typeof window.VCM.setExpect === "function") {
        window.VCM.setExpect("gate2", null);
      }
      updateExpected(null);
    });
    container.appendChild(clearChip);
  }

  function bindSlider() {
    const slider = document.getElementById("thr_g2");
    if (!slider) return;

    const currentVal = (window.VCM && window.VCM.thr && typeof window.VCM.thr.gate2MinConf === "number")
      ? window.VCM.thr.gate2MinConf
      : 0.5;
    slider.value = String(currentVal);

    if (slider.dataset.bound === "1") return;
    slider.dataset.bound = "1";

    function onSliderChange() {
      const val = parseFloat(slider.value);
      if (window.VCM && typeof window.VCM.setThr === "function") {
        window.VCM.setThr("gate2MinConf", val);
      }
      updateExpected();
    }

    slider.addEventListener("input", onSliderChange);
    slider.addEventListener("change", onSliderChange);
  }

  function bindControls() {
    const saveCsv = document.getElementById("g2saveCsv");
    if (saveCsv) {
      saveCsv.onclick = function () {
        if (window.VCM && typeof window.VCM.exportLog === "function") {
          window.VCM.exportLog("gate2", "csv");
        }
      };
    }

    const saveJson = document.getElementById("g2saveJson");
    if (saveJson) {
      saveJson.onclick = function () {
        if (window.VCM && typeof window.VCM.exportLog === "function") {
          window.VCM.exportLog("gate2", "json");
        }
      };
    }

    const clearBtn = document.getElementById("g2clear");
    if (clearBtn) {
      clearBtn.onclick = function () {
        const box = document.getElementById("g2log");
        if (box) box.innerHTML = "";
        windowsScored = 0;
        const statsEl = document.getElementById("g2stats");
        if (statsEl) statsEl.textContent = "windows scored: 0";
      };
    }
  }

  var g2LatchKey = null;
  var g2LatchText = null;
  var g2LatchCls = null;

  function handleProbs2(message) {
    if (!message || typeof message !== "object") return;

    let top = message.top;
    let conf = (typeof message.conf === "number") ? message.conf : Number(message.conf);
    const probs = message.probs || {};

    if (!top && message.probs) {
      let maxP = -1;
      const keys = Object.keys(probs);
      for (let i = 0; i < keys.length; i++) {
        const p = Number(probs[keys[i]]) || 0;
        if (p > maxP) {
          maxP = p;
          top = keys[i];
          conf = p;
        }
      }
    }
    top = top || "—";
    if (!Number.isFinite(conf)) conf = 0;

    const intents = getUniqueIntents();
    for (let i = 0; i < intents.length; i++) {
      const intent = intents[i];
      const p = (typeof probs[intent] === "number") ? probs[intent] : Number(probs[intent]) || 0;
      const bar = document.getElementById("bar_" + intent);
      const val = document.getElementById("val_" + intent);
      if (bar) {
        bar.style.width = Math.min(100, Math.max(0, p * 100)).toFixed(1) + "%";
        bar.style.background = (intent === top) ? "#2ea043" : "#1f6feb";
      }
      if (val) {
        val.textContent = p.toFixed(3);
      }
    }

    pushG2Reading(message);
    drawG2Charts();

    const topEl = document.getElementById("g2top");
    if (topEl) {
      topEl.textContent = "TOP: " + top + " (" + conf.toFixed(2) + ")";
    }

    const exp = window.VCM && window.VCM.expect ? window.VCM.expect.gate2 : null;
    const expectedIntent = exp && exp.intent ? exp.intent : null;
    let minConf = 0.5;
    if (window.VCM && typeof window.VCM.getThrG2 === "function" && expectedIntent) minConf = window.VCM.getThrG2(expectedIntent);
    else if (window.VCM && window.VCM.thr && typeof window.VCM.thr.gate2MinConf === "number") minConf = window.VCM.thr.gate2MinConf;

    const expKey = expectedIntent ? JSON.stringify(exp) : null;
    if (expKey !== g2LatchKey) { g2LatchKey = expKey; g2LatchText = null; g2LatchCls = null; }

    let verdict = "no phrase selected";
    let verdictCls = "v-idle";

    if (!expectedIntent) {
      verdict = "no phrase selected";
      verdictCls = "v-idle";
    } else if (top === expectedIntent) {
      if (conf >= minConf) {
        verdict = "PASS";
        verdictCls = "v-pass";
      } else {
        verdict = "LOW";
        verdictCls = "v-low";
      }
    } else if (conf >= minConf) {
      verdict = "wrong: " + top;
      verdictCls = "v-fail";
    } else {
      verdict = "scanning… (top " + top + ")";
      verdictCls = "v-idle";
    }

    // Latch: the sliding 74-frame crop only centers an utterance for a few
    // ticks, so once the expected intent is detected the verdict stays PASS.
    // Latch only PASS: a latched LOW would mask later failures; LOW is per-tick.
    if (verdictCls === "v-pass") {
      g2LatchText = verdict;
      g2LatchCls = verdictCls;
    }
    if (g2LatchText) {
      verdict = g2LatchText;
      verdictCls = g2LatchCls;
    }

    const verdictEl = document.getElementById("g2verdict");
    if (verdictEl) {
      verdictEl.className = "verdict " + verdictCls;
      verdictEl.textContent = verdict;
    }

    const ts = message.ts || new Date().toISOString();
    const logLine = ts + " top=" + top + " conf=" + conf.toFixed(3) + " -> " + verdict;
    const logCls = (verdict === "PASS") ? "ok" : ((verdict === "FAIL") ? "err" : "");
    if (window.VCM && typeof window.VCM.log === "function") {
      window.VCM.log("gate2", logLine, logCls);
    }

    windowsScored++;
    const statsEl = document.getElementById("g2stats");
    if (statsEl) {
      statsEl.textContent = "windows scored: " + windowsScored;
    }
  }

  function init() {
    renderBars();
    renderChips();
    bindSlider();
    bindChartControls();
    bindControls();
    updateExpected();

    if (!subscribed && window.VCM && typeof window.VCM.on === "function") {
      window.VCM.on("probs2", handleProbs2);
      subscribed = true;
    }
  }

  window.VCMG2 = {
    init: init,
    drawCompact: function (pipeMsg) {
      const g2 = pipeMsg && pipeMsg.g2;
      if (g2 && Array.isArray(g2.probs) && g2.probs.length) {
        const labels = Array.isArray(g2.labels) ? g2.labels : [];
        const probs = {};
        labels.forEach(function (label, i) { probs[label] = Number(g2.probs[i]) || 0; });
        pushG2Reading({ probs: probs, top: g2.current_intent || g2.intent || null });
      }
      drawG2Charts();
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
