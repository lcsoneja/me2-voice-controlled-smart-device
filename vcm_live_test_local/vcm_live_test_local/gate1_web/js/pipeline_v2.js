/* PIPELINE v2 — pseudo-code layout renderer (same live "pipe" feed as pipeline.js).
   Stages: memory -> G1 (every tick) -> G2 (only while wake latched) ->
   ACTION LIGHT (first) -> G3/4/5 slot value -> PATH/accuracy. */
(function () {
  "use strict";

  var WCM = window.VCM || null;
  if (!WCM && !(window.VCMPIPE2_PHRASES && window.VCMPIPE2_PHRASES.G2)) return;

  var initialized = false;
  var accuracy = { attempts: 0, matches: 0, last: "\u2014" };
  var prevWakeHit = false;
  var accExpKey = null;
  var lastKnown = { g2: null, slot: null, atMs: 0 };

  function el(id) { return document.getElementById(id); }

  function ageText() {
    var ageS = Math.round((Date.now() - lastKnown.atMs) / 1000);
    return "last known " + ageS + "s ago";
  }

  function phraseSource() {
    if (WCM && WCM.PHRASES && Array.isArray(WCM.PHRASES.G2)) return WCM.PHRASES.G2;
    if (window.VCMPIPE2_PHRASES && Array.isArray(window.VCMPIPE2_PHRASES.G2)) return window.VCMPIPE2_PHRASES.G2;
    return [];
  }

  function commandExamples() {
    var examples = Object.create(null);
    var pairs = phraseSource();
    pairs.forEach(function (pair) {
      var intent = pair[1];
      if (intent && !Object.prototype.hasOwnProperty.call(examples, intent)) examples[intent] = pair[0];
    });
    return examples;
  }

  function buildFrameCells() {
    var grid = el("pipe2-frames");
    if (!grid || grid.dataset.built === "1") return;
    grid.dataset.built = "1";
    for (var i = 0; i < 20; i++) {
      var cell = document.createElement("span");
      cell.className = "pipe2-frame";
      cell.id = "pipe2-frame-" + i;
      grid.appendChild(cell);
    }
  }

  function allPhrases() {
    var out = Object.create(null);
    phraseSource().forEach(function (pair) {
      var intent = pair[1];
      if (!intent) return;
      if (!Object.prototype.hasOwnProperty.call(out, intent)) out[intent] = [];
      out[intent].push(pair[0]);
    });
    return out;
  }

  var phraseTip = null;
  function showPhraseTip(card, intent) {
    if (!phraseTip) {
      phraseTip = document.createElement("div");
      phraseTip.id = "pipe2-phrase-tip";
      phraseTip.style.cssText = "position:absolute;display:none;z-index:60;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:6px 9px;font-size:11px;color:#e6edf3;max-width:280px;box-shadow:0 4px 14px rgba(0,0,0,.5);pointer-events:none;line-height:1.5";
      document.body.appendChild(phraseTip);
    }
    phraseTip.textContent = "";
    var head = document.createElement("div");
    head.style.cssText = "font-weight:700;color:#58a6ff;margin-bottom:2px";
    head.textContent = intent + " — say any of:";
    phraseTip.appendChild(head);
    (allPhrases()[intent] || []).forEach(function (p) {
      var row = document.createElement("div");
      row.textContent = "• " + p;
      phraseTip.appendChild(row);
    });
    phraseTip.style.display = "block";
    var rect = card.getBoundingClientRect();
    phraseTip.style.left = Math.max(4, Math.min(window.innerWidth - 292, rect.left)) + "px";
    phraseTip.style.top = (rect.bottom + 4) + "px";
  }
  function hidePhraseTip() { if (phraseTip) phraseTip.style.display = "none"; }

  function buildActionCards() {
    var grid = el("pipe2-cards");
    if (!grid || grid.dataset.built === "1") return;
    grid.dataset.built = "1";
    var examples = commandExamples();
    Object.keys(examples).forEach(function (intent) {
      var card = document.createElement("div");
      card.className = "parallel-action";
      card.id = "pipe2-card-" + intent;
      var light = document.createElement("span");
      light.className = "parallel-led";
      light.id = "pipe2-led-" + intent;
      var title = document.createElement("strong");
      title.textContent = intent;
      var phrase = document.createElement("div");
      phrase.className = "statsline";
      phrase.textContent = 'example: "' + examples[intent] + '"';
      var state = document.createElement("div");
      state.className = "statsline";
      state.id = "pipe2-state-" + intent;
      state.textContent = "idle";
      card.appendChild(light);
      card.appendChild(title);
      card.appendChild(phrase);
      card.appendChild(state);
      card.addEventListener("mouseenter", function () { showPhraseTip(card, intent); });
      card.addEventListener("mouseleave", hidePhraseTip);
      grid.appendChild(card);
    });
  }

  function clearCards() {
    var examples = commandExamples();
    Object.keys(examples).forEach(function (intent) {
      var card = el("pipe2-card-" + intent);
      var light = el("pipe2-led-" + intent);
      var state = el("pipe2-state-" + intent);
      if (card) card.classList.remove("selected");
      if (light) light.classList.remove("on");
      if (state) state.textContent = "idle";
    });
  }

  function specDisplay(gate) {
    if (gate === "gateN") return "G3";
    if (gate === "gate4") return "G4";
    if (gate === "gate5") return "G5";
    return gate;
  }

  function updateMemory(message) {
    var memEl = el("pipe2-memory");
    var framesEl = el("pipe2-frames");
    var mem = message.memory || null;
    var seconds = mem ? mem.seconds : 0;
    if (memEl) {
      memEl.textContent = mem
        ? "MEMORY: " + mem.seconds + "/" + mem.max + " s \u00b7 window = last " + mem.window_frames + " frame" + (mem.window_frames === 1 ? "" : "s") + " (" + mem.source + ")"
        : "MEMORY: \u2014";
    }
    if (framesEl) {
      var cells = framesEl.children;
      for (var i = 0; i < cells.length; i++) cells[i].classList.toggle("filled", i < seconds);
    }
  }

  function updateG1(message) {
    var g1 = message.g1 || {};
    var elG1 = el("pipe2-g1");
    if (!elG1) return;
    var rmsText = (g1.rms == null) ? "" : " \u00b7 rms " + Number(g1.rms).toFixed(3) + "/" + Number(g1.floor || 0).toFixed(3);
    if (g1.active && (g1.activation_label || g1.wake)) {
      elG1.className = "verdict v-pass";
      elG1.textContent = "WAKE: " + (g1.activation_label || g1.wake) + " (" + Number(g1.activation_conf || 0).toFixed(3) + ") \u00b7 votes " + (g1.votes || 0) + "/3 \u00b7 ACTIVE " + Number(g1.remaining_s || 0).toFixed(1) + "s" + rmsText;
    } else if (g1.candidate) {
      elG1.className = "verdict v-low";
      elG1.textContent = "WAKE: candidate " + g1.candidate + " \u00b7 votes " + (g1.votes || 0) + "/3 \u2014 waiting for confirmation" + rmsText;
    } else {
      elG1.className = "verdict v-idle";
      var gated = g1.label && g1.label.indexOf("gated") === 0;
      elG1.textContent = "WAKE: " + (gated ? g1.label : "listening for Nova / Piattos (Gate 1 runs every tick)") + rmsText;
    }
  }

  function updateG2(message) {
    var g2 = message.g2 || {};
    var elG2 = el("pipe2-g2");
    if (!elG2) return;
    if (g2.waiting) {
      elG2.className = "verdict v-idle";
      elG2.textContent = "INTENT: \u2014 parallel gate evaluation (2 s cadence)";
      return;
    }
    var conf = (g2.active && Number.isFinite(g2.activation_conf)) ? g2.activation_conf : (Number.isFinite(g2.conf) ? g2.conf : null);
    var name = g2.activation_intent || g2.intent || null;
    var thr = (g2.threshold != null) ? Number(g2.threshold) : null;
    if (g2.active && name) {
      elG2.className = "verdict v-pass";
      elG2.textContent = "INTENT: " + name + " (" + Number(conf || 0).toFixed(3) + ")" + (thr != null ? ((conf >= thr ? " PASS" : " fail") + " vs " + thr) : "") + " \u00b7 ACTIVE " + Number(g2.remaining_s || 0).toFixed(1) + "s";
    } else if (lastKnown.g2) {
      elG2.className = "verdict v-low";
      elG2.textContent = "INTENT: last: " + lastKnown.g2.name + " (" + Number(lastKnown.g2.conf || 0).toFixed(3) + ") \u00b7 " + ageText();
    } else {
      elG2.className = "verdict v-idle";
      elG2.textContent = "INTENT: no confident intent yet";
    }
    if (name && conf != null) lastKnown.g2 = { name: name, conf: conf };
  }

  function updateAction(message) {
    var actionGate = message.action_gate || {};
    var spec = message.spec || null;
    var status = el("pipe2-action");
    var slot = el("pipe2-slot");
    clearCards();
    var intent = actionGate.intent || null;
    if (actionGate.triggered && intent) {
      var card = el("pipe2-card-" + intent);
      var light = el("pipe2-led-" + intent);
      var state = el("pipe2-state-" + intent);
      if (card) card.classList.add("selected");
      if (light) light.classList.add("on");
      if (state) state.textContent = "ACTION LIGHT \u2014 TRIGGERED";
      if (status) {
        status.className = "verdict v-pass";
        status.textContent = "LIGHT ON: " + intent + " \u00b7 new activation (lights 1st)";
      }
    } else if (actionGate.active && intent) {
      if (status) {
        status.className = "verdict v-low";
        status.textContent = "GATE OVERLAP: " + intent + " \u00b7 waiting for new event";
      }
    } else if (status) {
      status.className = "verdict v-idle";
      status.textContent = "no light \u2014 waiting for confirmed Gate1 + Gate2";
    }
    if (slot) {
      if (spec && spec.label) {
        slot.textContent = specDisplay(spec.gate) + " \u2192 " + spec.label + (spec.conf != null ? " (" + Number(spec.conf).toFixed(3) + ")" : "") + " \u00b7 ROUTED VALUE";
      } else if (actionGate.triggered && intent) {
        slot.textContent = "No Gate 3\u20135 value needed \u2014 Gate 2 intent only";
      } else if (lastKnown.slot) {
        slot.textContent = "last: " + lastKnown.slot + " \u00b7 " + ageText();
      } else {
        slot.textContent = "\u2014";
      }
    }
    if (spec && spec.label) lastKnown.slot = specDisplay(spec.gate) + " \u2192 " + spec.label;
    lastKnown.atMs = Date.now();
  }

  function updatePath(message) {
    var elPath = el("pipe2-path");
    if (!elPath) return;
    var actionOn = !!(message.path && message.path.some(function (s) { return s.gate === "ACTION" && s.on; }));
    var anyOn = !!(message.path && message.path.some(function (s) { return s.on; }));
    elPath.textContent = "PATH: " + (message.path_text || "\u2014");
    elPath.className = "verdict " + (actionOn ? "v-pass" : (anyOn ? "v-low" : "v-idle"));
  }

  function updateSpecialists(message) {
    var wrap = el("pipe2-specialists");
    if (!wrap) return;
    var spec = message.spec || null;
    var routed = spec ? spec.gate : null;
    var specs = message.specialists || {};
    ["gateN", "gate4", "gate5"].forEach(function (name) {
      var line = el("pipe2-spec-" + name);
      if (!line) return;
      var s = specs[name];
      if (s && s.label) {
        line.className = "parallel-branch" + (routed === name ? " route" : "");
        line.textContent = specDisplay(name) + ": " + s.label + (s.conf != null ? " (" + Number(s.conf).toFixed(3) + ")" : "") + (routed === name ? " \u00b7 ROUTED VALUE" : "");
      } else {
        line.className = "parallel-branch";
        line.textContent = specDisplay(name) + ": waiting";
      }
    });
  }

  function updateAccuracy(message) {
    var accEl = el("pipe2-accuracy");
    if (!accEl) return;
    var g1 = message.g1 || {};
    var g2 = message.g2 || {};
    var spec = message.spec || null;
    var exp = (WCM && WCM.expect && WCM.expect.pipe) ? WCM.expect.pipe : null;
    var expKeyNow = exp ? JSON.stringify(exp) : null;
    if (expKeyNow !== accExpKey) {
      accExpKey = expKeyNow;
      accuracy = { attempts: 0, matches: 0, last: "\u2014" };
      prevWakeHit = false;
    }
    var verdictCls = message.verdictCls || null;
    if (exp && exp.intent && message.new_event) {
      accuracy.attempts += 1;
      if (verdictCls === "v-pass") { accuracy.matches += 1; accuracy.last = "MATCH"; }
      else accuracy.last = "MISS";
    }
    if (exp && exp.wake) {
      var wakeHit = !!(g1 && g1.wake === exp.wake);
      if (wakeHit && !prevWakeHit) {
        accuracy.attempts += 1;
        if (verdictCls === "v-pass") { accuracy.matches += 1; accuracy.last = "MATCH"; }
        else accuracy.last = "MISS";
      }
      prevWakeHit = wakeHit;
    }
    var g1pct = (g1.active && Number.isFinite(g1.activation_conf)) ? Math.round(g1.activation_conf * 100) + "%" : "\u2014";
    var g2pct = "\u2014";
    if (g2 && !g2.waiting) {
      var c2 = (g2.active && Number.isFinite(g2.activation_conf)) ? g2.activation_conf : (Number.isFinite(g2.conf) ? g2.conf : null);
      var t2 = (g2.threshold != null) ? Number(g2.threshold) : null;
      if (c2 != null) g2pct = Math.round(c2 * 100) + "%" + (t2 != null ? ((c2 >= t2 ? " PASS" : " fail") + " vs " + t2) : "");
    }
    var specPct = (spec && Number.isFinite(spec.conf)) ? Math.round(spec.conf * 100) + "%" : "\u2014";
    var summary = exp
      ? "ACCURACY: " + accuracy.matches + "/" + accuracy.attempts + " (" + (accuracy.attempts ? Math.round(100 * accuracy.matches / accuracy.attempts) : 0) + "%) \u00b7 last: " + accuracy.last
      : "ACCURACY: select an expected phrase to track accuracy";
    accEl.textContent = summary + " \u00b7 per test \u2014 G1 " + g1pct + " \u00b7 G2 " + g2pct + " \u00b7 spec " + specPct;
  }

  function bindOwnerVoice() {
    var ovBtn = el("pipe2ownervoiceRun");
    if (!ovBtn || ovBtn.dataset.bound === "1") return;
    ovBtn.dataset.bound = "1";
    ovBtn.addEventListener("click", function () {
      var summary = el("pipe2-ownervoice-summary");
      var perIntent = el("pipe2-ownervoice-perintent");
      var mismatches = el("pipe2-ownervoice-mismatches");
      if (summary) { summary.textContent = "scoring 280 recordings\u2026 (up to a minute)"; summary.className = "verdict v-idle"; }
      if (perIntent) perIntent.textContent = "\u2014";
      if (mismatches) mismatches.textContent = "\u2014";
      fetch("/api/owner-voice/evaluate", { method: "POST" }).then(function (r) { return r.json(); }).then(function (s) {
        if (s.error) {
          if (summary) { summary.textContent = "ERROR: " + s.error; summary.className = "verdict v-fail"; }
          return;
        }
        if (summary) {
          summary.textContent = "OVERALL: " + s.correct + "/" + s.total + " (" + (100 * s.accuracy).toFixed(1) + "%) \u00b7 model " + s.model;
          summary.className = "verdict " + (s.accuracy >= 0.9 ? "v-pass" : (s.accuracy >= 0.75 ? "v-low" : "v-fail"));
        }
        if (perIntent) {
          var rows = Object.keys(s.per_intent || {}).map(function (intent) {
            var b = s.per_intent[intent];
            return intent + " " + b.correct + "/" + b.total + " (" + (100 * b.accuracy).toFixed(0) + "%)";
          });
          perIntent.textContent = rows.join(" \u00b7 ") || "\u2014";
        }
        if (mismatches) {
          var mm = (s.mismatches || []).slice(0, 12).map(function (m) {
            return m.file.split("/").pop() + ": expected " + m.expected + " \u2260 " + m.predicted + " (" + Number(m.conf).toFixed(3) + ")";
          });
          mismatches.textContent = (s.mismatches || []).length ? mm.join("  |  ") : "no mismatches";
        }
      }).catch(function (err) {
        if (summary) { summary.textContent = "ERROR: " + err; summary.className = "verdict v-fail"; }
      });
    });
  }

  function update(message) {
    if (!message || typeof message !== "object") return;
    buildFrameCells();
    buildActionCards();
    window.VCMPIPE2.lastMessage = message;
    updateMemory(message);
    updateG1(message);
    updateG2(message);
    updateAction(message);
    updateSpecialists(message);
    updatePath(message);
    updateAccuracy(message);
  }

  function init() {
    if (initialized) return;
    initialized = true;
    buildFrameCells();
    buildActionCards();
    bindOwnerVoice();
    if (WCM && typeof WCM.on === "function") WCM.on("pipe", update);
  }

  window.VCMPIPE2 = { init: init, update: update, lastMessage: null };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
