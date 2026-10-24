const DB_NAME = "gate2-phrase-lab";
const DB_VERSION = 1;
let dbPromise = null;

export function openPhraseLabDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise(function (resolve, reject) {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = function () {
      const db = request.result;
      if (!db.objectStoreNames.contains("recordings")) db.createObjectStore("recordings", { keyPath: "id" });
      if (!db.objectStoreNames.contains("logs")) db.createObjectStore("logs", { keyPath: "id" });
    };
    request.onsuccess = function () { resolve(request.result); };
    request.onerror = function () { reject(request.error || new Error("Could not open local recording database")); };
  });
  return dbPromise;
}

function storeRequest(storeName, mode, requestFactory) {
  return openPhraseLabDb().then(function (db) {
    return new Promise(function (resolve, reject) {
      const transaction = db.transaction(storeName, mode);
      const request = requestFactory(transaction.objectStore(storeName));
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error || new Error("Local database request failed")); };
      transaction.onabort = function () { reject(transaction.error || new Error("Local database transaction aborted")); };
    });
  });
}

export function saveRecording(recording) {
  return storeRequest("recordings", "readwrite", function (store) { return store.put(recording); });
}

export function deleteRecording(id) {
  return storeRequest("recordings", "readwrite", function (store) { return store.delete(id); });
}

export function getRecordings() {
  return storeRequest("recordings", "readonly", function (store) { return store.getAll(); });
}

export function saveLog(entry) {
  return storeRequest("logs", "readwrite", function (store) { return store.put(entry); });
}

export function getLogs() {
  return storeRequest("logs", "readonly", function (store) { return store.getAll(); });
}

export function clearLogs() {
  return storeRequest("logs", "readwrite", function (store) { return store.clear(); });
}

export function encodePcmWav(samples, sampleRate) {
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

export function phraseSlug(phrase) {
  return phrase.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

export function wavFilename(intent, phrase, date) {
  const stamp = date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  return "gate2_" + intent + "_" + phraseSlug(phrase) + "_" + stamp + ".wav";
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
}

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return '"' + text.replace(/"/g, '""') + '"';
}

export function logsToCsv(rows) {
  const columns = ["tested_at", "recording_file", "phrase", "expected_intent", "interval_seconds", "raw_intent", "raw_confidence", "raw_expected_score", "rnnoise_intent", "rnnoise_confidence", "rnnoise_expected_score"];
  const records = rows.slice().sort(function (a, b) { return a.testedAt.localeCompare(b.testedAt); });
  return [columns.join(",")].concat(records.map(function (row) {
    return [row.testedAt, row.fileName, row.phrase, row.intent, row.intervalS, row.rawTop, row.rawConf, row.rawExpectedConf, row.cleanTop, row.cleanConf, row.cleanExpectedConf].map(csvCell).join(",");
  })).join("\r\n");
}
