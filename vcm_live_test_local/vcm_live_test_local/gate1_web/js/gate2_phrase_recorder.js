import { Gate2PhraseAudio } from "/js/gate2_phrase_lab_audio.js?v=phrase-lab-2";
import {
  clearLogs, deleteRecording, downloadBlob, encodePcmWav, getLogs, getRecordings,
  logsToCsv, phraseSlug, saveLog, saveRecording, wavFilename
} from "/js/gate2_phrase_lab_storage.js?v=phrase-lab-2";

const ui = {
  status: document.getElementById("status"),
  label: document.getElementById("recording-label"),
  stopRecord: document.getElementById("stop-recording"),
  stopMic: document.getElementById("stop-mic"),
  phraseList: document.getElementById("phrase-list"),
  recordings: document.getElementById("recordings-list"),
  logs: document.getElementById("log-list"),
  importWav: document.getElementById("wav-import"),
  importPhrase: document.getElementById("import-phrase"),
  interval: document.getElementById("interval"),
  rawTop: document.getElementById("raw-top"), rawConf: document.getElementById("raw-conf"), rawMatch: document.getElementById("raw-match"),
  cleanTop: document.getElementById("clean-top"), cleanConf: document.getElementById("clean-conf"), cleanMatch: document.getElementById("clean-match"),
  exportLog: document.getElementById("export-log"), clearLog: document.getElementById("clear-log")
};
const audio = new Gate2PhraseAudio({ onStatus: setStatus });
let phrases = [];
let logCache = [];
let activePhrase = null;
let recordTimer = null;
let busyTesting = false;

function setStatus(text, isError) {
  ui.status.textContent = text;
  ui.status.classList.toggle("error", Boolean(isError));
}

function setRecordingLabel(text) { ui.label.textContent = text; }

function renderPhraseList() {
  ui.phraseList.replaceChildren();
  const groups = new Map();
  phrases.forEach(function (phrase) {
    if (!groups.has(phrase.group)) groups.set(phrase.group, []);
    groups.get(phrase.group).push(phrase);
  });
  groups.forEach(function (items, groupName) {
    const section = document.createElement("section"); section.className = "phrase-group";
    const title = document.createElement("h3"); title.textContent = groupName; section.appendChild(title);
    items.forEach(function (phrase) {
      const row = document.createElement("div"); row.className = "phrase-row";
      const text = document.createElement("div");
      const main = document.createElement("span"); main.className = "phrase-text"; main.textContent = phrase.phrase;
      const intent = document.createElement("span"); intent.className = "phrase-intent"; intent.textContent = phrase.intent;
      text.append(main, intent);
      const button = document.createElement("button"); button.className = "record-phrase primary";
      button.dataset.phrase = phrase.phrase; button.textContent = "Record";
      button.disabled = busyTesting || Boolean(activePhrase);
      button.addEventListener("click", function () { void startRecording(phrase); });
      row.append(text, button); section.appendChild(row);
    });
    ui.phraseList.appendChild(section);
  });
}

function setPhraseButtonsDisabled(disabled) {
  ui.phraseList.querySelectorAll(".record-phrase").forEach(function (button) { button.disabled = disabled; });
}

async function startRecording(phrase) {
  if (activePhrase || busyTesting) return;
  activePhrase = phrase;
  setPhraseButtonsDisabled(true);
  setRecordingLabel("Recording label: " + phrase.intent + " · “" + phrase.phrase + "”");
  ui.stopRecord.disabled = true;
  setStatus("Requesting microphone and starting the labeled recording…");
  try {
    await audio.startRecording();
    ui.stopRecord.disabled = false;
    ui.stopMic.disabled = false;
    setStatus("Recording “" + phrase.phrase + "”. Say it clearly, then press Stop & download WAV.");
    recordTimer = window.setTimeout(function () { void stopRecording(); }, 8000);
  } catch (error) {
    activePhrase = null;
    await audio.close();
    setRecordingLabel("Click Record beside a phrase to begin.");
    setPhraseButtonsDisabled(false);
    setStatus(error.message || String(error), true);
  }
}

async function stopRecording() {
  if (!activePhrase) return;
  if (recordTimer) { window.clearTimeout(recordTimer); recordTimer = null; }
  ui.stopRecord.disabled = true;
  const phrase = activePhrase;
  activePhrase = null;
  try {
    const capture = await audio.stopRecording();
    const createdAt = new Date().toISOString();
    const fileName = wavFilename(phrase.intent, phrase.phrase, new Date(createdAt));
    const wavBlob = encodePcmWav(capture.samples, 48000);
    const record = {
      id: crypto.randomUUID(), phrase: phrase.phrase, intent: phrase.intent, group: phrase.group,
      createdAt: createdAt, duration: capture.duration, sampleRate: 48000, fileName: fileName, wavBlob: wavBlob
    };
    await saveRecording(record);
    downloadBlob(wavBlob, fileName);
    await refreshRecordings();
    setStatus("Saved and downloaded " + fileName + ". Choose Test A/B beside it to replay the same WAV through both Gate 2 paths.");
  } catch (error) {
    setStatus(error.message || String(error), true);
  } finally {
    setRecordingLabel("Click Record beside a phrase to begin.");
    setPhraseButtonsDisabled(busyTesting);
    ui.stopRecord.disabled = true;
  }
}

async function stopMicrophone() {
  if (activePhrase) await stopRecording();
  await audio.close();
  ui.stopMic.disabled = true;
  setStatus("Microphone stopped. Existing WAVs remain saved and can still be tested.");
}

function fillComparison(name, result, expectedIntent) {
  const isRaw = name === "raw";
  const top = isRaw ? ui.rawTop : ui.cleanTop;
  const confidence = isRaw ? ui.rawConf : ui.cleanConf;
  const match = isRaw ? ui.rawMatch : ui.cleanMatch;
  const score = Number((result.probs || {})[expectedIntent] || 0);
  top.textContent = result.top || "—";
  confidence.textContent = Number(result.conf).toFixed(3);
  const correct = result.top === expectedIntent;
  match.textContent = (correct ? "MATCH" : "MISMATCH") + " · expected score " + score.toFixed(3);
  match.className = correct ? "match" : "mismatch";
}

async function testRecording(record) {
  if (activePhrase || busyTesting) return;
  busyTesting = true;
  setPhraseButtonsDisabled(true);
  ui.importWav.disabled = true;
  setStatus("Replaying the centered 5.92-second sample through raw and RNNoise Gate 2…");
  try {
    const intervalS = Number(ui.interval.value);
    const results = await audio.testRecording(record, intervalS);
    fillComparison("raw", results.raw, record.intent);
    fillComparison("clean", results.clean, record.intent);
    const log = {
      id: crypto.randomUUID(), testedAt: new Date().toISOString(), recordingId: record.id,
      fileName: record.fileName, phrase: record.phrase, intent: record.intent, intervalS: intervalS,
      rawTop: results.raw.top, rawConf: Number(results.raw.conf).toFixed(6),
      rawExpectedConf: Number((results.raw.probs || {})[record.intent] || 0).toFixed(6),
      cleanTop: results.clean.top, cleanConf: Number(results.clean.conf).toFixed(6),
      cleanExpectedConf: Number((results.clean.probs || {})[record.intent] || 0).toFixed(6)
    };
    await saveLog(log);
    await refreshLogs();
    setStatus("Test complete: " + record.fileName + ". Both results were logged.");
  } catch (error) {
    setStatus(error.message || String(error), true);
  } finally {
    busyTesting = false;
    ui.importWav.disabled = false;
    setPhraseButtonsDisabled(Boolean(activePhrase));
    await refreshRecordings();
  }
}

function renderRecordings(records) {
  ui.recordings.replaceChildren();
  if (!records.length) { ui.recordings.innerHTML = '<div class="empty">No recordings saved yet.</div>'; return; }
  records.sort(function (a, b) { return b.createdAt.localeCompare(a.createdAt); });
  records.forEach(function (record) {
    const row = document.createElement("div"); row.className = "recording-row";
    const phrase = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = record.phrase;
    const details = document.createElement("div"); details.className = "muted"; details.textContent = record.intent + " · " + new Date(record.createdAt).toLocaleString() + (record.duration ? " · " + record.duration.toFixed(2) + " s" : "");
    const filename = document.createElement("div"); filename.className = "muted"; filename.textContent = record.fileName;
    phrase.append(title, details, filename);
    const test = document.createElement("button"); test.className = "test-recording primary"; test.textContent = "Test A/B"; test.disabled = busyTesting || Boolean(activePhrase);
    test.addEventListener("click", function () { void testRecording(record); });
    const download = document.createElement("button"); download.textContent = "Download WAV";
    download.addEventListener("click", function () { downloadBlob(record.wavBlob, record.fileName); });
    const remove = document.createElement("button"); remove.textContent = "Delete";
    remove.addEventListener("click", async function () { await deleteRecording(record.id); await refreshRecordings(); });
    const actions = document.createElement("div"); actions.className = "rec-actions"; actions.append(test, download, remove);
    row.append(phrase, actions); ui.recordings.appendChild(row);
  });
}

async function refreshRecordings() { renderRecordings(await getRecordings()); }

function renderLogs(logs) {
  logCache = logs.slice();
  ui.logs.replaceChildren();
  if (!logs.length) { ui.logs.innerHTML = '<div class="empty">No tests logged yet.</div>'; return; }
  logCache.sort(function (a, b) { return b.testedAt.localeCompare(a.testedAt); });
  logCache.forEach(function (entry) {
    const row = document.createElement("div"); row.className = "log-row";
    const date = document.createElement("span"); date.textContent = new Date(entry.testedAt).toLocaleString();
    const label = document.createElement("span"); label.textContent = entry.phrase + " · " + entry.intent + " · " + entry.intervalS + "s";
    const raw = document.createElement("span"); raw.textContent = entry.rawTop + " " + entry.rawConf + " (expected " + entry.rawExpectedConf + ")"; raw.className = entry.rawTop === entry.intent ? "match" : "mismatch";
    const clean = document.createElement("span"); clean.textContent = entry.cleanTop + " " + entry.cleanConf + " (expected " + entry.cleanExpectedConf + ")"; clean.className = entry.cleanTop === entry.intent ? "match" : "mismatch";
    row.append(date, label, raw, clean); ui.logs.appendChild(row);
  });
}

async function refreshLogs() { renderLogs(await getLogs()); }

function findPhraseFromFilename(filename) {
  const lower = filename.toLowerCase();
  return phrases.find(function (item) { return lower.includes(phraseSlug(item.phrase)); }) || null;
}

async function importWav(file) {
  let phrase = findPhraseFromFilename(file.name);
  if (!phrase && ui.importPhrase.value) phrase = phrases.find(function (item) { return item.phrase === ui.importPhrase.value; });
  if (!phrase) { setStatus("This WAV filename has no known phrase label; choose a label in the import menu first.", true); return; }
  const record = {
    id: crypto.randomUUID(), phrase: phrase.phrase, intent: phrase.intent, group: phrase.group,
    createdAt: new Date().toISOString(), duration: null, sampleRate: null, fileName: file.name, wavBlob: file
  };
  await saveRecording(record);
  await refreshRecordings();
  setStatus("Imported and labeled " + file.name + ". It is stored locally and ready to test again.");
  ui.importWav.value = "";
}

function exportLogCsv() {
  setStatus("Preparing CSV test log…");
  downloadBlob(new Blob(["\uFEFF", logsToCsv(logCache)], { type: "text/csv;charset=utf-8" }), "gate2_phrase_test_log.csv");
  setStatus("CSV test log downloaded.");
}

async function initialize() {
  try {
    const response = await fetch("/data/gate2_phrases.json");
    if (!response.ok) throw new Error("Could not load Gate 2 phrase list (HTTP " + response.status + ")");
    phrases = await response.json();
    renderPhraseList();
    ui.importPhrase.innerHTML = '<option value="">Choose phrase label…</option>';
    phrases.forEach(function (phrase) {
      const option = document.createElement("option"); option.value = phrase.phrase; option.textContent = phrase.intent + " · " + phrase.phrase; ui.importPhrase.appendChild(option);
    });
    ui.stopRecord.addEventListener("click", function () { void stopRecording(); });
    ui.stopMic.addEventListener("click", function () { void stopMicrophone(); });
    ui.importWav.addEventListener("change", function () {
      const file = ui.wavImport.files && ui.wavImport.files[0];
      if (file) void importWav(file).catch(function (error) { setStatus(error.message || String(error), true); });
    });
    ui.exportLog.addEventListener("click", function () {
      try { exportLogCsv(); } catch (error) { setStatus(error.message || String(error), true); }
    });
    ui.clearLog.addEventListener("click", async function () {
      if (window.confirm("Clear the saved Gate 2 phrase test log?")) { await clearLogs(); await refreshLogs(); }
    });
    await Promise.all([refreshRecordings(), refreshLogs()]);
    setStatus("Ready. Choose a phrase, record it, then test its saved WAV against both Gate 2 paths.");
  } catch (error) {
    setStatus(error.message || String(error), true);
  }
}

window.addEventListener("pagehide", function () { void audio.close(); });
void initialize();
