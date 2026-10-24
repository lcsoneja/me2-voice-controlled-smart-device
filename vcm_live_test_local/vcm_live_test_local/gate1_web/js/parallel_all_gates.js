/* VCM Live Monitor — All Gates Parallel test page. */
(function () {
  "use strict";

  var initialized = false;

  function el(id) { return document.getElementById(id); }

  function commandExamples() {
    var examples = Object.create(null);
    var pairs = window.VCM && VCM.PHRASES && Array.isArray(VCM.PHRASES.G2) ? VCM.PHRASES.G2 : [];
    pairs.forEach(function (pair) {
      var phrase = pair[0];
      var intent = pair[1];
      if (intent && !Object.prototype.hasOwnProperty.call(examples, intent)) examples[intent] = phrase;
    });
    return examples;
  }

  function buildActionCards() {
    var grid = el("parallel-cards");
    if (!grid || grid.dataset.built === "1") return;
    grid.dataset.built = "1";
    var examples = commandExamples();
    Object.keys(examples).forEach(function (intent) {
      var card = document.createElement("div");
      card.className = "parallel-action";
      card.id = "parallel-card-" + intent;
      var light = document.createElement("span");
      light.className = "parallel-led";
      light.id = "parallel-led-" + intent;
      var title = document.createElement("strong");
      title.textContent = intent;
      var phrase = document.createElement("div");
      phrase.className = "statsline";
      phrase.textContent = 'example: "' + examples[intent] + '"';
      var state = document.createElement("div");
      state.className = "thrlabel";
      state.id = "parallel-state-" + intent;
      state.textContent = "idle";
      card.appendChild(light);
      card.appendChild(title);
      card.appendChild(phrase);
      card.appendChild(state);
      grid.appendChild(card);
    });
  }

  function setBranch(id, result, routed) {
    var node = el(id);
    if (!node) return;
    node.classList.toggle("route", !!routed);
    if (!result) {
      node.textContent = node.id.replace("parallel-", "") + ": waiting for Gate 1 wake";
      return;
    }
    node.textContent = node.id.replace("parallel-", "") + ": " + result.top + " (" + Number(result.conf || 0).toFixed(3) + ")" + (routed ? " · ROUTED VALUE" : "");
  }

  function clearLights() {
    var examples = commandExamples();
    Object.keys(examples).forEach(function (intent) {
      var card = el("parallel-card-" + intent);
      var light = el("parallel-led-" + intent);
      var state = el("parallel-state-" + intent);
      if (card) card.classList.remove("selected");
      if (light) light.classList.remove("on");
      if (state) state.textContent = "idle";
    });
  }

  function update(message) {
    if (!message || typeof message !== "object") return;
    window.VCMPARALLEL.lastMessage = message;
    buildActionCards();
    var g1 = message.g1 || {};
    var g1El = el("parallel-g1");
    if (g1El) {
      if (g1.active && g1.wake) {
        g1El.className = "verdict v-pass";
        var wakeConf = g1.confidence == null ? g1.conf : g1.confidence;
        g1El.textContent = "WAKE ACTIVE: " + g1.wake + " (" + Number(wakeConf || 0).toFixed(3) + ") · " + Number(g1.remaining_s || 0).toFixed(1) + "s" + (g1.rms == null ? "" : " · rms " + Number(g1.rms).toFixed(3) + "/" + Number(g1.floor || 0).toFixed(3));
      } else if (g1.candidate) {
        g1El.className = "verdict v-low";
        g1El.textContent = "candidate " + g1.candidate + " · votes " + (g1.votes || 0) + "/2 — waiting for confirmation" + (g1.rms == null ? "" : " · rms " + Number(g1.rms).toFixed(3) + " / floor " + Number(g1.floor || 0).toFixed(3));
      } else {
        g1El.className = "verdict v-idle";
        g1El.textContent = "waiting for a wake word (Nova / Piattos)" + (g1.rms == null ? "" : " · rms " + Number(g1.rms).toFixed(3) + " / floor " + Number(g1.floor || 0).toFixed(3));
      }
    }

    var g2 = message.gate2 || null;
    var g2El = el("parallel-g2");
    if (g2El) {
      if (g2) {
        g2El.className = "verdict " + (g2.conf >= g2.threshold ? "v-pass" : "v-low");
        g2El.textContent = (g2.model || "Gate 2") + ": " + g2.intent + " (" + Number(g2.conf || 0).toFixed(3) + ") · threshold " + Number(g2.threshold || 0).toFixed(2);
      } else {
        g2El.className = "verdict v-idle";
        g2El.textContent = "not running — Gate 1 wake required";
      }
    }

    var specialists = message.specialists || {};
    var action = message.action || null;
    ["gateN", "gate4", "gate5"].forEach(function (gate) {
      setBranch("parallel-" + gate, specialists[gate], !!(action && action.route === gate && action.active));
    });

    clearLights();
    var actionStatus = el("parallel-action-status");
    var slot = el("parallel-slot-value");
    if (action && action.active && action.intent) {
      var card = el("parallel-card-" + action.intent);
      var light = el("parallel-led-" + action.intent);
      var state = el("parallel-state-" + action.intent);
      if (card) card.classList.add("selected");
      if (light && action.light) light.classList.add("on");
      if (state) state.textContent = action.light ? "ACTION LIGHT — TRIGGERED" : "intent accepted · waiting for new event";
      if (actionStatus) {
        actionStatus.className = action.light ? "verdict v-pass" : "verdict v-low";
        actionStatus.textContent = action.light ? ("LIGHT ON: " + action.intent + " · new activation") : ("GATE OVERLAP: " + action.intent + " · waiting for new event");
      }
      if (slot) {
        slot.textContent = action.route ? (action.gate + " → " + (action.value || "no slot value") + (action.slot_conf == null ? "" : " (" + Number(action.slot_conf).toFixed(3) + ")")) : "No Gate 3–5 value needed — Gate 2 intent only";
      }
    } else {
      if (actionStatus) {
        actionStatus.className = "verdict v-idle";
        actionStatus.textContent = "no action light — waiting for confirmed Gate1 + Gate2";
      }
      if (slot) slot.textContent = "—";
    }
    var stage = el("parallel-stage");
    if (stage) stage.textContent = message.stage || "parallel monitor ready";
  }

  function init() {
    if (initialized || !window.VCM || typeof VCM.on !== "function") return;
    initialized = true;
    buildActionCards();
    VCM.on("parallel", update);
  }

  window.VCMPARALLEL = { init: init, update: update, lastMessage: null };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
