/* METRICS tab: Gate 2 performance + t-SNE embeddings scatter (offline, canvas-based, DOM-API only). */
(function () {
  "use strict";

  var CLASS_COLORS = {};
  function classColor(cls) {
    if (!CLASS_COLORS[cls]) {
      var n = Object.keys(CLASS_COLORS).length;
      CLASS_COLORS[cls] = "hsl(" + Math.round(n * (360 / 19)) + ", 70%, 55%)";
    }
    return CLASS_COLORS[cls];
  }

  var hidden = {};      // class -> true (legend toggle)
  var showSyn = true, showReal = true;

  function el(id) { return document.getElementById(id); }

  function div(parent, cls, text) {
    var d = document.createElement("div");
    if (cls) d.className = cls;
    if (text !== undefined) d.textContent = text;
    parent.appendChild(d);
    return d;
  }

  function probRow(parent, nameText, pct, bg, valText) {
    var line = document.createElement("div"); line.className = "probrow";
    var nm = document.createElement("div"); nm.className = "probname"; nm.textContent = nameText; nm.title = nameText;
    var wrap = document.createElement("div"); wrap.className = "probbarwrap";
    var bar = document.createElement("div"); bar.className = "probbar";
    bar.style.width = Math.max(0, Math.min(100, pct)).toFixed(0) + "%";
    if (bg) bar.style.background = bg;
    wrap.appendChild(bar);
    var val = document.createElement("div"); val.className = "probval"; val.textContent = valText;
    line.appendChild(nm); line.appendChild(wrap); line.appendChild(val);
    parent.appendChild(line);
  }

  function summary() {
    var d = window.METRICS_DATA;
    var box = el("metricsSummary");
    box.replaceChildren();
    var items = [
      ["Synthetic validation", d.synthetic.accuracy, d.synthetic.total, "#2ea043", "same-domain TTS (leak-prone split)"],
      ["Owner real voice", d.realVoice.accuracy, d.realVoice.total, "#f85149", "sealed 150-command holdout - evaluated once"]
    ];
    items.forEach(function (it) {
      var card = document.createElement("div");
      card.className = "card"; card.style.marginBottom = "8px";
      div(card, "thrlabel", it[0]);
      var big = document.createElement("div");
      big.style.cssText = "font-size:26px;font-weight:700;color:" + it[3];
      big.textContent = (it[1] * 100).toFixed(2) + "%";
      card.appendChild(big);
      div(card, "thrlabel", it[2] + " clips · " + it[4]);
      box.appendChild(card);
    });
    div(box, "thrlabel", "The gap between the two numbers is the domain gap (TTS vs owner real voice) — the same gap the DGX handoff tracks.");
  }

  function perClass() {
    var d = window.METRICS_DATA;
    var wrap = el("metricsPerClass");
    wrap.replaceChildren();
    div(wrap, "thrlabel", "Real voice per-class accuracy (n per class)");
    d.perClassRV.slice(1).forEach(function (row) {
      var cls = row[0], n = row[1], acc = row[3] === "" ? null : parseFloat(row[3]);
      var pct = acc === null ? 0 : acc * 100;
      var bg = acc === null ? "#30363d" : (acc >= 0.5 ? "#2ea043" : acc > 0 ? "#9e6a03" : "#b62324");
      var val = acc === null ? "n=0" : (acc * 100).toFixed(0) + "% n=" + n;
      probRow(wrap, cls, pct, bg, val);
    });
    var h2 = div(wrap, "thrlabel", "Synthetic per-class F1");
    h2.style.marginTop = "10px";
    var synthPC = d.synthetic.per_class || {};
    var synthRows = Array.isArray(synthPC) ? synthPC : Object.keys(synthPC).map(function (k) {
      return { cls: k, f1: synthPC[k].f1 };
    });
    synthRows.forEach(function (row) {
      probRow(wrap, row.cls, Number(row.f1) * 100, "#1f6feb", Number(row.f1).toFixed(2));
    });
  }

  function confusionTable(container, rows, title) {
    div(container, "thrlabel", title);
    var tbl = document.createElement("table");
    tbl.style.width = "100%"; tbl.style.fontSize = "9px"; tbl.style.borderCollapse = "collapse";
    var maxCount = 1;
    rows.slice(1).forEach(function (r) { r.slice(1).forEach(function (c) { var v = parseInt(c, 10) || 0; if (v > maxCount) maxCount = v; }); });
    rows.forEach(function (r, i) {
      var tr = document.createElement("tr");
      r.forEach(function (cell, j) {
        var td = document.createElement(i === 0 ? "th" : "td");
        td.style.border = "1px solid #30363d"; td.style.padding = "2px";
        if (i === 0) { td.style.transform = "rotate(-60deg)"; td.style.height = "60px"; td.style.verticalAlign = "bottom"; td.style.border = "none"; }
        if (j === 0 && i > 0) { td.style.fontWeight = "700"; td.style.textAlign = "right"; td.style.border = "none"; }
        if (i > 0 && j > 0) {
          var v = parseInt(cell, 10) || 0;
          td.style.textAlign = "center";
          if (v > 0) {
            var inten = Math.round(v / maxCount * 70);
            td.style.background = (i - 1 === j - 1) ? "rgba(46,160,67," + (0.25 + inten / 100) + ")" : "rgba(31,111,235," + (0.15 + inten / 100) + ")";
            td.textContent = v;
            if (i - 1 === j - 1 && v > 0) td.style.outline = "1px solid #2ea043";
          }
        } else {
          td.textContent = cell;
        }
        tr.appendChild(td);
      });
      tbl.appendChild(tr);
    });
    container.appendChild(tbl);
  }

  function drawScatter() {
    var d = window.METRICS_DATA;
    var canvas = el("tsneCanvas");
    var W = canvas.width, H = canvas.height;
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = "#0d1117"; ctx.fillRect(0, 0, W, H);
    var pts = d.tsne.filter(function (p) {
      if (hidden[p.cls]) return false;
      if (p.ds === "synthetic" && !showSyn) return false;
      if (p.ds !== "synthetic" && !showReal) return false;
      return true;
    });
    if (!pts.length) { canvas._pts = []; return; }
    var minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
    pts.forEach(function (p) { minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y); });
    var pad = 30;
    function sx(x) { return pad + (x - minX) / (maxX - minX || 1) * (W - 2 * pad); }
    function sy(y) { return H - pad - (y - minY) / (maxY - minY || 1) * (H - 2 * pad); }
    pts.forEach(function (p) {
      var x = sx(p.x), y = sy(p.y);
      var col = classColor(p.cls);
      if (p.ds === "synthetic") {
        ctx.globalAlpha = 0.35;
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
      } else {
        var ok = p.correct === "true" || p.correct === "True";
        ctx.fillStyle = ok ? "#2ea043" : "#f85149";
        ctx.strokeStyle = "#fff"; ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, y - 5); ctx.lineTo(x + 5, y); ctx.lineTo(x, y + 5); ctx.lineTo(x - 5, y);
        ctx.closePath(); ctx.fill(); ctx.stroke();
      }
    });
    canvas._pts = pts; canvas._sx = sx; canvas._sy = sy;
  }

  function legend() {
    var d = window.METRICS_DATA;
    var leg = el("tsneLegend");
    leg.replaceChildren();
    var counts = {};
    d.tsne.forEach(function (p) { counts[p.cls] = (counts[p.cls] || 0) + 1; });
    Object.keys(counts).sort().forEach(function (cls) {
      var sw = document.createElement("span");
      sw.className = "chip";
      sw.style.borderColor = classColor(cls);
      sw.style.borderLeftWidth = "6px";
      sw.textContent = cls + " (" + counts[cls] + ")";
      if (hidden[cls]) sw.style.opacity = "0.35";
      sw.onclick = function () { hidden[cls] = !hidden[cls]; sw.style.opacity = hidden[cls] ? "0.35" : "1"; drawScatter(); };
      leg.appendChild(sw);
    });
    var lblSyn = document.createElement("label"); lblSyn.style.marginRight = "10px";
    var cbSyn = document.createElement("input"); cbSyn.type = "checkbox"; cbSyn.id = "dsSyn"; cbSyn.checked = true;
    lblSyn.appendChild(cbSyn); lblSyn.appendChild(document.createTextNode(" synthetic"));
    leg.appendChild(lblSyn);
    var lblReal = document.createElement("label");
    var cbReal = document.createElement("input"); cbReal.type = "checkbox"; cbReal.id = "dsReal"; cbReal.checked = true;
    lblReal.appendChild(cbReal); lblReal.appendChild(document.createTextNode(" real voice"));
    leg.appendChild(lblReal);
    cbSyn.onchange = function () { showSyn = cbSyn.checked; drawScatter(); };
    cbReal.onchange = function () { showReal = cbReal.checked; drawScatter(); };
  }

  function tooltip(mouseEvent) {
    var canvas = el("tsneCanvas");
    var rect = canvas.getBoundingClientRect();
    var mx = (mouseEvent.clientX - rect.left) * (canvas.width / rect.width);
    var my = (mouseEvent.clientY - rect.top) * (canvas.height / rect.height);
    var best = null, bestD = 1e9;
    (canvas._pts || []).forEach(function (p) {
      var dx = canvas._sx(p.x) - mx, dy = canvas._sy(p.y) - my;
      var dist = dx * dx + dy * dy;
      if (dist < bestD) { bestD = dist; best = p; }
    });
    var box = el("tsneTip");
    if (best && bestD < 400) {
      box.replaceChildren();
      var b = document.createElement("b"); b.textContent = best.cls; box.appendChild(b);
      box.appendChild(document.createTextNode(" · " + best.ds));
      if (best.file) {
        var br = document.createElement("br"); box.appendChild(br);
        box.appendChild(document.createTextNode(best.file.slice(0, 48)));
      }
      if (best.correct) {
        var br2 = document.createElement("br"); box.appendChild(br2);
        box.appendChild(document.createTextNode("correct: " + best.correct));
      }
      box.style.display = "block";
      box.style.left = (mx + 12) + "px"; box.style.top = (my + 8) + "px";
    } else {
      box.style.display = "none";
    }
  }

  function init() {
    if (!window.METRICS_DATA) {
      div(el("metricsSummary"), "err", "METRICS_DATA not loaded");
      return;
    }
    summary();
    perClass();
    var confWrap = el("metricsConfusion");
    confusionTable(confWrap, window.METRICS_DATA.confusionSyn, "Confusion matrix — synthetic validation (1806 clips)");
    div(confWrap, "thrlabel", "");
    confusionTable(confWrap, window.METRICS_DATA.confusionRV, "Confusion matrix — owner real voice (sealed 150-command holdout)");
    legend();
    drawScatter();
    var canvas = el("tsneCanvas");
    canvas.addEventListener("mousemove", tooltip);
    canvas.addEventListener("mouseleave", function () { el("tsneTip").style.display = "none"; });
  }

  window.VCMMETRICS = { init: init };
  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
