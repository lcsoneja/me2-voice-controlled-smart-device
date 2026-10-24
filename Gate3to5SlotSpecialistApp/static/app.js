const APP_BASE = window.location.pathname.startsWith("/gate3to5/") ? "/gate3to5" : "";
const ui = {
  gate: document.getElementById("gate"),
  ratio: document.getElementById("ratio"),
  audio: document.getElementById("audio"),
  fileName: document.getElementById("file-name"),
  maxDuration: document.getElementById("max-duration"),
  run: document.getElementById("run"),
  status: document.getElementById("status"),
  result: document.getElementById("result"),
  selected: document.getElementById("selected"),
  stateBadge: document.getElementById("state-badge"),
  rejectAlert: document.getElementById("reject-alert"),
  topLabel: document.getElementById("top-label"),
  topScore: document.getElementById("top-score"),
  scores: document.getElementById("scores"),
  resultNote: document.getElementById("result-note")
};
let config = null;

function setStatus(message, isError) {
  ui.status.textContent = message;
  ui.status.classList.toggle("error", Boolean(isError));
}

function updateRunButton() {
  ui.run.disabled = !config || !ui.gate.value || !ui.ratio.value || !ui.audio.files || !ui.audio.files.length;
}

function clearResult() {
  ui.result.hidden = true;
  ui.scores.replaceChildren();
  ui.rejectAlert.hidden = true;
  ui.stateBadge.textContent = "Waiting";
  ui.topLabel.textContent = "—";
  ui.topScore.textContent = "—";
  ui.resultNote.textContent = "";
}

function renderResult(result) {
  ui.result.hidden = false;
  ui.selected.textContent = result.gate + " · " + result.ratio;
  ui.stateBadge.textContent = result.top_label === "REJECT" ? "REJECT" : "Classified";
  ui.stateBadge.classList.toggle("reject", result.top_label === "REJECT");
  ui.rejectAlert.hidden = result.top_label !== "REJECT";
  ui.topLabel.textContent = result.top_label;
  ui.topLabel.classList.toggle("reject", result.top_label === "REJECT");
  ui.topScore.textContent = Number(result.top_score).toFixed(6);
  ui.scores.replaceChildren();
  result.class_scores.forEach(function (item) {
    const row = document.createElement("div");
    row.className = "score-row" + (item.label === "REJECT" ? " reject" : "") + (item.label === result.top_label ? " top" : "");
    const label = document.createElement("span"); label.className = "score-label"; label.textContent = item.label;
    const track = document.createElement("div"); track.className = "score-track";
    const fill = document.createElement("div"); fill.className = "score-fill";
    fill.style.width = Math.max(0, Math.min(100, Number(item.score) * 100)) + "%";
    track.appendChild(fill);
    const score = document.createElement("span"); score.className = "score-value"; score.textContent = Number(item.score).toFixed(6);
    row.append(label, track, score);
    ui.scores.appendChild(row);
  });
  ui.resultNote.textContent = result.score_interpretation + " · " + Number(result.clip_duration_seconds).toFixed(2) + " s clip · " + Number(result.window_seconds).toFixed(2) + " s model window.";
}

async function loadConfig() {
  const response = await fetch(APP_BASE + "/api/config", { cache: "no-store" });
  if (!response.ok) throw new Error("Local app configuration unavailable (HTTP " + response.status + ")");
  config = await response.json();
  config.gates.forEach(function (gate) {
    const option = document.createElement("option");
    option.value = gate.id;
    option.textContent = gate.name;
    ui.gate.appendChild(option);
  });
  config.ratios.forEach(function (ratio) {
    const option = document.createElement("option");
    option.value = ratio;
    option.textContent = ratio + " · candidate";
    ui.ratio.appendChild(option);
  });
  ui.maxDuration.textContent = Number(config.max_clip_seconds).toFixed(2) + " seconds";
  setStatus("Choose a gate, a candidate ratio, and one WAV clip. No candidate is preselected.");
  updateRunButton();
}

async function submitInference(event) {
  event.preventDefault();
  const file = ui.audio.files && ui.audio.files[0];
  if (!ui.gate.value || !ui.ratio.value || !file) {
    setStatus("Explicitly select a gate, ratio, and WAV file before running.", true);
    return;
  }
  clearResult();
  ui.run.disabled = true;
  setStatus("Loading the selected Keras candidate and classifying one clip locally…");
  const body = new FormData();
  body.append("gate", ui.gate.value);
  body.append("ratio", ui.ratio.value);
  body.append("audio", file, file.name);
  try {
    const response = await fetch(APP_BASE + "/api/infer", { method: "POST", body: body, cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Inference failed (HTTP " + response.status + ")");
    renderResult(result);
    setStatus("Inference complete. Uploaded audio was processed in memory and discarded.");
  } catch (error) {
    setStatus(error.message || String(error), true);
  } finally {
    ui.audio.value = "";
    ui.fileName.textContent = "No clip selected.";
    updateRunButton();
  }
}

ui.gate.addEventListener("change", function () { clearResult(); updateRunButton(); });
ui.ratio.addEventListener("change", function () { clearResult(); updateRunButton(); });
ui.audio.addEventListener("change", function () {
  ui.fileName.textContent = ui.audio.files && ui.audio.files[0] ? ui.audio.files[0].name : "No clip selected.";
  clearResult();
  updateRunButton();
});
document.getElementById("inference-form").addEventListener("submit", submitInference);
void loadConfig().catch(function (error) { setStatus(error.message || String(error), true); });
