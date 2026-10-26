# Voice Studio — offline single-file recorder

`VoiceStudio.html` is one self-contained file: double-click it, allow microphone access, and record. No server, no install, no network. Works from a USB stick, another laptop, or Raspberry Pi (Chromium).

## Launch

- Normal: double-click `VoiceStudio.html` (opens in your browser via `file://`).
- If a browser ever blocks the microphone on `file://`, either allow it in the site-permission prompt or serve the folder once:
  ```powershell
  py -3.12 -m http.server 8900
  # then open http://localhost:8900/VoiceStudio.html
  ```
  The app detects the situation and shows a clear message; `localhost` is always a trusted context.

## Recording workflow

1. Pick the **next take label** from the phrase dropdown (93 example phrases across the 19 Gate 2 intents; your selection auto-labels the take).
2. **Record** → speak → **Pause** if you need a breath/think break (the paused gap is cut out of the audio) → **Stop & save**.
3. The take appears in the list with a waveform thumbnail; **Play** to hear it, **Delete** or **Download WAV** per take.
4. **Export CSV log** (file, intent, phrase, label, timestamp, duration, rate) or **Export ZIP folder** (`recordings/<INTENT>/<file>.wav` + `manifest.csv` + `README.txt`) when a session is done.

Takes persist in this browser (IndexedDB) across reloads. File names are canonical: `gate2_<INTENT>__<phrase>__<timestamp>.wav` — the inline rename field only changes the display name, so dataset file names stay consistent. Every WAV is mono 48 kHz PCM16.

## Buttons and shortcuts

| State | Record | Pause/Resume | Stop/save | Play | Delete | Download |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| Idle | ● | – | – | – | – | – |
| Recording | – | ● pause | ● | – | – | – |
| Paused | – | ● resume | ● | – | ● discard | – |
| Stopped | ● | – | – | ● | ● | ● |
| Playing | ● (auto-stops playback) | ● | ● (stop playback) | – | ● | ● |

Shortcuts: `R` record · `P` pause/resume · `Space` stop-save or play/pause · `Delete` delete · `Up`/`Down` select take. Ignored while typing in a field.

## Privacy and storage

Audio is captured in memory, stored only in this browser's IndexedDB, and exported only when you click. No cloud services, analytics, or uploads; deleting a take (or all takes) removes it from the browser. Downloaded files live wherever your browser saves downloads.

## Raspberry Pi

Runs in Chromium on Raspberry Pi OS with no Python dependencies. Redraws are throttled to 20 fps and thumbnails are precomputed peaks, so the Pi only draws small canvases. Storage and exports behave the same. If you later want a headless Pi recorder that writes straight to disk folders, that would be a separate Python variant — this file needs only a browser.

## Limitations

- One recording at a time; playback and recording do not overlap.
- Recording longer than 10 minutes auto-stops (safety cap).
- Recognition/quality of the audio is not evaluated by this tool — it records and organizes takes only.
- No TFLite/models are involved here; this is the data-collection front end.

## Tests

From the `VoiceStudio` folder:

```powershell
py -3.12 -m unittest discover -s tests -t . -v
```

`tests/test_contract.py` verifies the file is fully self-contained (no external scripts, links, or network calls), the transport state machine, WAV/ZIP/CRC builders, and the inline 93-phrase data. `tests/test_browser.py` runs a real browser from `file://` with a synthetic mic through the whole workflow (record/pause-cut/resume/stop, playback, exports, persistence, shortcuts) — synthetic audio only, no private recordings.
