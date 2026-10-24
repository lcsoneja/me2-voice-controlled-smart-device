(function () {
  "use strict";

  var WCM = window.VCM;
  if (!WCM || typeof WCM.PHRASES === "undefined") return;

  // Diagram highlight: boxes use class "lit", connector lines use class "lnlit".
  function setLit(id, on) {
    var el = document.getElementById(id);
    if (!el) return;
    if (el.tagName === "line") el.classList.toggle("lnlit", !!on);
    else el.classList.toggle("lit", !!on);
  }

  // Map a specialist route to a short display name (for the stage card).
  function specName(gate) {
    if (gate === "gateN") return "Gate N";
    if (gate === "gate4") return "Gate 4";
    if (gate === "gate5") return "Gate 5";
    return gate;
  }

  function setVerdict(text, cls) {
    var el = document.getElementById("pipeverdict");
    if (!el) return;
    el.textContent = text;
    el.className = "verdict " + cls;
  }

  function updateExpected() {
    var exp = WCM.expect.pipe;
    var el = document.getElementById("pipeexpected");
    if (!el) return;
    if (!exp) { el.textContent = "none"; return; }
    if (exp.wake) { el.textContent = "wake: " + exp.wake; return; }
    if (exp.intent) { el.textContent = exp.intent + (exp.value ? " [" + exp.value + "]" : ""); return; }
    el.textContent = "none";
  }

  function chip(text, onActivate) {
    var c = document.createElement("span");
    c.className = "chip";
    c.textContent = text;
    c.addEventListener("click", function () { onActivate(c); });
    return c;
  }

  function clearSel() {
    var wakeGroup = document.getElementById("pipechips-wake");
    var cmdGroup = document.getElementById("pipechips");
    if (wakeGroup) { var w = wakeGroup.children; for (var i = 0; i < w.length; i++) w[i].classList.remove("sel"); }
    if (cmdGroup) { var c = cmdGroup.children; for (var j = 0; j < c.length; j++) c[j].classList.remove("sel"); }
  }

  // Highlight the currently-selected chip based on current expect.
  function refreshSelection() {
    var exp = WCM.expect.pipe || null;
    var wakeGroup = document.getElementById("pipechips-wake");
    var cmdGroup = document.getElementById("pipechips");
    clearSel();
    if (exp && exp.wake && wakeGroup) {
      var wk = wakeGroup.children;
      for (var i = 0; i < wk.length; i++) {
        if (wk[i].getAttribute("data-wake") === exp.wake) { wk[i].classList.add("sel"); break; }
      }
    } else if (exp && exp.intent && cmdGroup) {
      var c2 = cmdGroup.children;
      for (var d = 0; d < c2.length; d++) {
        if (c2[d].getAttribute("data-intent") === exp.intent &&
            c2[d].getAttribute("data-value") === (exp.value || "")) { c2[d].classList.add("sel"); break; }
      }
    }
  }

  function init() {
    var wakeGroup = document.getElementById("pipechips-wake");
    var cmdGroup = document.getElementById("pipechips");
    if (wakeGroup) {
      WCM.PHRASES.PIPE_WAKE.forEach(function (pair) {
        var W = pair[1];
        var c = chip(pair[0], function (el) {
          WCM.setExpect("pipe", { wake: W });
          clearSel();
          el.classList.add("sel");
          updateExpected();
        });
        c.setAttribute("data-wake", W);
        wakeGroup.appendChild(c);
      });
    }
    if (cmdGroup) {
      WCM.PHRASES.PIPE_CMDS.forEach(function (row) {
        var I = row[1];
        var V = row[2];
        var label = row[0] + (V ? " (" + V + ")" : "");
        var c = chip(label, function (el) {
          WCM.setExpect("pipe", { intent: I, value: V });
          clearSel();
          el.classList.add("sel");
          updateExpected();
        });
        c.setAttribute("data-intent", I);
        c.setAttribute("data-value", V || "");
        cmdGroup.appendChild(c);
      });
    }
    // Clear chip (in the commands group) clears both wake + command expectations.
    var clear = document.createElement("span");
    clear.className = "chip";
    clear.textContent = "Clear";
    clear.addEventListener("click", function () {
      WCM.setExpect("pipe", null);
      clearSel();
      updateExpected();
    });
    if (cmdGroup) cmdGroup.appendChild(clear);

    updateExpected();
    refreshSelection();

    WCM.on("pipe", onPipe);

    var calBtn = document.getElementById("pipecal");
    if (calBtn) calBtn.addEventListener("click", function () {
      WCM.send({ type: "calibrate", seconds: 10 });
    });

    var ovBtn = document.getElementById("pipeownervoiceRun");
    if (ovBtn) ovBtn.addEventListener("click", function () {
      var summary = document.getElementById("pipe-ownervoice-summary");
      var perIntent = document.getElementById("pipe-ownervoice-perintent");
      var mismatches = document.getElementById("pipe-ownervoice-mismatches");
      if (summary) { summary.textContent = "scoring 280 recordings… (up to a minute)"; summary.className = "verdict v-idle"; }
      if (perIntent) perIntent.textContent = "—";
      if (mismatches) mismatches.textContent = "—";
      fetch("/api/owner-voice/evaluate", { method: "POST" }).then(function (r) { return r.json(); }).then(function (s) {
        if (s.error) {
          if (summary) { summary.textContent = "ERROR: " + s.error; summary.className = "verdict v-fail"; }
          return;
        }
        if (summary) {
          summary.textContent = "OVERALL: " + s.correct + "/" + s.total + " (" + (100 * s.accuracy).toFixed(1) + "%) · model " + s.model;
          summary.className = "verdict " + (s.accuracy >= 0.9 ? "v-pass" : (s.accuracy >= 0.75 ? "v-low" : "v-fail"));
        }
        if (perIntent) {
          var rows = Object.keys(s.per_intent || {}).map(function (intent) {
            var b = s.per_intent[intent];
            return intent + " " + b.correct + "/" + b.total + " (" + (100 * b.accuracy).toFixed(0) + "%)";
          });
          perIntent.textContent = rows.join(" · ") || "—";
        }
        if (mismatches) {
          var mm = (s.mismatches || []).slice(0, 12).map(function (m) {
            return m.file.split("/").pop() + ": expected " + m.expected + " ≠ " + m.predicted + " (" + Number(m.conf).toFixed(3) + ")";
          });
          mismatches.textContent = (s.mismatches || []).length ? mm.join("  |  ") : "no mismatches";
        }
      }).catch(function (err) {
        if (summary) { summary.textContent = "ERROR: " + err; summary.className = "verdict v-fail"; }
      });
    });

    WCM.on("gated", function (msg) {
      // The server now sends full pipe payloads during gated ticks, so this is
      // only a fallback for legacy servers.
      var el = document.getElementById("pipe-g1");
      if (el && window.VCMPipeHandledGated) return;
      if (el) el.textContent = "G1: below floor · gated (room " + msg.rms + " < floor " + msg.floor + ")";
    });

    WCM.on("calibrated", function (msg) {
      if (msg.thr && typeof msg.thr.Nova === "number") {
        WCM.setThr("Nova", msg.thr.Nova);
        WCM.setThr("Piattos", msg.thr.Piattos);
        var el = document.getElementById("pipe-g1");
        if (el) el.textContent = "G1: calibrated — wake thresholds set to " + msg.thr.Nova.toFixed(2);
      }
    });
  }

  var pipeLatchKey = null;
  var pipeLatchText = null;
  var pipeLatchCls = null;

  // Last-known stage values (shown with an age while nothing is live, so the
  // cards never fall back to bare dashes between events).
  var lastKnown = { g2: null, spec: null, final: null, atMs: 0 };
  var pipeAccuracy = { attempts: 0, matches: 0, last: "—" };
  var pipePrevWakeHit = false;
  var accExpKey = null;

  function rememberStageValues(g2, spec, final) {
    if (g2 && g2.intent && g2.intent !== "-") lastKnown.g2 = { intent: g2.intent, conf: g2.conf };
    if (spec && spec.label) lastKnown.spec = { gate: spec.gate, label: spec.label, conf: spec.conf };
    if (final && final !== "-") lastKnown.final = final;
    lastKnown.atMs = Date.now();
  }

  function ageText() {
    const ageS = Math.round((Date.now() - lastKnown.atMs) / 1000);
    return "last known " + ageS + "s ago";
  }

  function onPipe(msg) {
    if (!msg || typeof msg !== "object") return;
    var g1 = msg.g1 || null;
    var g2 = msg.g2 || null;
    var spec = msg.spec || null;
    var final = msg.final || null;
    var actionGate = msg.action_gate || null;

    // --- Frame memory + taken path (server-provided) ---
    var memEl = document.getElementById("pipe-memory");
    if (memEl) {
      var mem = msg.memory || null;
      memEl.textContent = mem
        ? "MEMORY: " + mem.seconds + "/" + mem.max + " s · window = last " + mem.window_frames + " frame" + (mem.window_frames === 1 ? "" : "s") + " (" + mem.source + ")"
        : "MEMORY: —";
    }
    var pathEl = document.getElementById("pipe-path");
    if (pathEl) {
      var actionOn = !!(msg.path && msg.path.some(function (s) { return s.gate === "ACTION" && s.on; }));
      var anyOn = !!(msg.path && msg.path.some(function (s) { return s.on; }));
      pathEl.textContent = "PATH: " + (msg.path_text || "—");
      pathEl.className = "verdict " + (actionOn ? "v-pass" : (anyOn ? "v-low" : "v-idle"));
    }

    function g1conf() {
      if (g1 && g1.active && Number.isFinite(g1.activation_conf)) return g1.activation_conf.toFixed(3);
      if (g1 && g1.wake && Array.isArray(g1.probs) && g1.probs.length) {
        var idx = g1.wake === "Piattos" ? 1 : 0;
        return g1.probs[idx] !== undefined ? g1.probs[idx].toFixed(3) : "—";
      }
      return "";
    }

    // --- Stage cards ---
    var g1el = document.getElementById("pipe-g1");
    var g1name = g1 ? (g1.activation_label || g1.wake || g1.label || "—") : "—";
    var g1activeText = g1 && g1.active ? " · ACTIVE " + Number(g1.remaining_s || 0).toFixed(1) + "s" : "";
    var g1confText = g1conf();
    if (g1 && g1.label && g1.label.indexOf("gated") === 0 && !g1confText) {
      g1el.textContent = "G1: below floor · " + g1name + g1activeText;
    } else {
      g1el.textContent = "G1: " + g1name + g1activeText + " (" + g1confText + ")";
    }

    var g2el = document.getElementById("pipe-g2");
    var g2name = null;
    var g2conf = null;
    if (g2) {
      g2name = g2.activation_intent || g2.current_intent || (g2.intent !== "-" ? g2.intent : null);
      if (g2.active && g2.activation_conf !== undefined) g2conf = g2.activation_conf;
      else if (g2.current_conf !== undefined && g2.current_conf > 0) g2conf = g2.current_conf;
      else if (g2.conf !== undefined && g2.conf > 0) g2conf = g2.conf;
    }
    if (g2 && g2.active && g2name) {
      g2el.textContent = "G2: " + g2name + " (" + Number(g2conf || 0).toFixed(3) + ") · ACTIVE " + Number(g2.remaining_s || 0).toFixed(1) + "s";
    } else if (lastKnown.g2) {
      g2el.textContent = "G2: last: " + lastKnown.g2.intent + " (" + Number(lastKnown.g2.conf || 0).toFixed(3) + ") · " + ageText();
    } else {
      g2el.textContent = "G2: no confident intent yet";
    }

    var actionel = document.getElementById("pipe-action");
    if (actionel) {
      if (actionGate && actionGate.triggered) actionel.textContent = "ACTION GATE: TRIGGERED → " + (actionGate.intent || g2name);
      else if (actionGate && actionGate.active) actionel.textContent = "ACTION GATE: ACTIVE · G1/G2 overlap" + (actionGate.intent ? " · " + actionGate.intent : "");
      else actionel.textContent = "ACTION GATE: waiting for G1/G2 overlap";
    }

    var specel = document.getElementById("pipe-spec");
    if (specel) {
      if (spec && spec.label) {
        var specialistConf = spec.conf !== undefined ? spec.conf.toFixed(3) : "—";
        specel.textContent = specName(spec.gate) + ": " + spec.label + " (" + specialistConf + ")";
      } else if (lastKnown.spec) {
        specel.textContent = "SPEC: last: " + specName(lastKnown.spec.gate) + ": " + lastKnown.spec.label + " (" + Number(lastKnown.spec.conf || 0).toFixed(3) + ") · " + ageText();
      } else {
        specel.textContent = "SPEC: none dispatched yet";
      }
    }

    var finel = document.getElementById("pipe-final");
    if (finel) {
      if (final && final !== "-") finel.textContent = "FINAL: " + final;
      else if (lastKnown.final) finel.textContent = "FINAL: last: " + lastKnown.final + " · " + ageText();
      else finel.textContent = "FINAL: none yet";
    }
    rememberStageValues(g2, spec, final);
    if (window.VCMG2 && typeof window.VCMG2.drawCompact === "function") window.VCMG2.drawCompact(msg);
    if (window.VCM && typeof window.VCM.drawG1Chart === "function") window.VCM.drawG1Chart();

    // --- SVG highlight ---
    var route = spec ? spec.gate : null;
    setLit("bx-g1", !!(g1 && g1.active));
    setLit("bx-g2", !!(g2 && g2.active));
    setLit("bx-action", !!(actionGate && actionGate.active));
    setLit("bx-gn", route === "gateN");
    setLit("bx-g4", route === "gate4");
    setLit("bx-g5", route === "gate5");
    setLit("bx-out", !!final);
    setLit("ln-mic-g1", !!g1);
    setLit("ln-mic-g2", !!(g2 && g2.current_intent));
    setLit("ln-g1-action", !!(g1 && g1.active));
    setLit("ln-g2-action", !!(g2 && g2.active));
    setLit("ln-action-gn", route === "gateN");
    setLit("ln-action-g4", route === "gate4");
    setLit("ln-action-g5", route === "gate5");
    setLit("ln-gn-out", route === "gateN" && !!final);
    setLit("ln-g4-out", route === "gate4" && !!final);
    setLit("ln-g5-out", route === "gate5" && !!final);

    // --- Verdict (contract section 6) ---
    var exp = WCM.expect.pipe || null;
    var verdictText, verdictCls;
    if (!exp) {
      verdictText = "no phrase selected";
      verdictCls = "v-idle";
    } else if (exp.wake) {
      if (g1 && g1.wake === exp.wake) { verdictText = "PASS"; verdictCls = "v-pass"; }
      else { verdictText = "listening for " + exp.wake + "…"; verdictCls = "v-idle"; }
    } else if (exp.intent) {
      var actionIntent = null;
      if (actionGate && actionGate.intent) actionIntent = actionGate.intent;
      else if (g2) actionIntent = g2.activation_intent || g2.intent || null;
      var actionConf = 0;
      if (g2 && g2.activation_conf !== undefined) actionConf = Number(g2.activation_conf);
      else if (g2 && g2.conf !== undefined) actionConf = Number(g2.conf);
      var specialistConfForVerdict = spec && spec.conf !== undefined ? Number(spec.conf) : 1;
      if (!actionGate || !actionGate.active) { verdictText = "waiting for G1/G2 activation overlap…"; verdictCls = "v-idle"; }
      else if (!actionGate.triggered) { verdictText = "activation overlap; waiting for a new G2 event…"; verdictCls = "v-idle"; }
      else if (actionIntent !== exp.intent) { verdictText = "FAIL (intent " + (actionIntent || "—") + " ≠ " + exp.intent + ")"; verdictCls = "v-fail"; }
      else if (exp.value && (!spec || spec.label !== exp.value)) { verdictText = "FAIL (value " + (spec ? spec.label : "—") + " ≠ " + exp.value + ")"; verdictCls = "v-fail"; }
      else if (Math.min(actionConf, specialistConfForVerdict) < WCM.thr.gate2MinConf) { verdictText = "LOW (conf below min)"; verdictCls = "v-low"; }
      else { verdictText = "PASS"; verdictCls = "v-pass"; }
    } else {
      verdictText = "no phrase selected";
      verdictCls = "v-idle";
    }

    // Latch: the sliding 74-frame crop centers an utterance only for a few
    // ticks, so once the expected chain is detected the verdict stays.
    var expKey = exp ? JSON.stringify(exp) : null;
    if (expKey !== pipeLatchKey) { pipeLatchKey = expKey; pipeLatchText = null; pipeLatchCls = null; }
    // Latch only PASS: a latched LOW would mask later failures; LOW is per-tick.
    if (verdictCls === "v-pass") {
      pipeLatchText = verdictText;
      pipeLatchCls = verdictCls;
    }
    if (pipeLatchText) {
      verdictText = pipeLatchText;
      verdictCls = pipeLatchCls;
    }
    setVerdict(verdictText, verdictCls);

    // --- Accuracy per test: per-stage scores + running expected-phrase accuracy ---
    var accEl = document.getElementById("pipe-accuracy");
    if (accEl) {
      var expNow = WCM.expect.pipe || null;
      var expKeyNow = expNow ? JSON.stringify(expNow) : null;
      if (expKeyNow !== accExpKey) { accExpKey = expKeyNow; pipeAccuracy = { attempts: 0, matches: 0, last: "—" }; pipePrevWakeHit = false; }
      if (expNow && expNow.intent && msg.new_event) {
        pipeAccuracy.attempts += 1;
        if (verdictCls === "v-pass") { pipeAccuracy.matches += 1; pipeAccuracy.last = "MATCH"; }
        else pipeAccuracy.last = "MISS";
      }
      if (expNow && expNow.wake) {
        var wakeHit = !!(g1 && g1.wake === expNow.wake);
        if (wakeHit && !pipePrevWakeHit) {
          pipeAccuracy.attempts += 1;
          if (verdictCls === "v-pass") { pipeAccuracy.matches += 1; pipeAccuracy.last = "MATCH"; }
          else pipeAccuracy.last = "MISS";
        }
        pipePrevWakeHit = wakeHit;
      }
      var g1pct = (g1 && g1.active && Number.isFinite(g1.activation_conf)) ? Math.round(g1.activation_conf * 100) + "%" : "—";
      var g2pct = "—";
      if (g2) {
        var c2 = g2.active && Number.isFinite(g2.activation_conf) ? g2.activation_conf : (g2.conf != null && Number.isFinite(g2.conf) ? g2.conf : null);
        var t2 = g2.threshold != null ? Number(g2.threshold) : null;
        if (c2 != null) g2pct = Math.round(c2 * 100) + "%" + (t2 != null ? (c2 >= t2 ? " PASS" : " fail") + " vs " + t2 : "");
      }
      var specPct = spec && Number.isFinite(spec.conf) ? Math.round(spec.conf * 100) + "%" : "—";
      var accSummary = expNow
        ? "ACCURACY: " + pipeAccuracy.matches + "/" + pipeAccuracy.attempts + " (" + (pipeAccuracy.attempts ? Math.round(100 * pipeAccuracy.matches / pipeAccuracy.attempts) : 0) + "%) · last: " + pipeAccuracy.last
        : "ACCURACY: select an expected phrase to track accuracy";
      accEl.textContent = accSummary + " · per test — G1 " + g1pct + " · G2 " + g2pct + " · spec " + specPct;
    }

    // --- Log (contract section 5) ---
    var ts = msg.ts || new Date().toISOString();
    var logG1 = g1 ? g1.label + "/" + g1conf() : "-";
    var logG2 = "-";
    if (g2) {
      var logG2Conf = g2.conf !== undefined ? g2.conf.toFixed(3) : "-";
      logG2 = g2.intent + "/" + logG2Conf;
    }
    var logSpec = "-";
    if (spec) {
      var logSpecConf = spec.conf !== undefined ? spec.conf.toFixed(3) : "-";
      logSpec = spec.label + "/" + logSpecConf;
    }
    WCM.log("pipe", ts + " g1=" + logG1 + " g2=" + logG2 + " spec=" + logSpec +
      " final=" + (final || "-") + " action=" + (actionGate && actionGate.triggered ? "triggered" : "waiting") +
      " -> " + verdictText);
  }

  window.VCMPIPE = { init: init };
})();
