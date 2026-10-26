# Gate 2 Phrase Recorder and Replay Lab

## Approved scope
Add a separate Gate 2 Phrase Lab page. Keep the existing 1s and 2s RNNoise A/B pages' behavior unchanged. The main monitor links to each page, and each child page has a clear return-to-monitor link; the A/B pages also link to the Phrase Lab.

## Recorder workflow
The page lists the canonical 31 Gate 2 spoken examples with their 19 intent labels. Each phrase row has its own Record button, so starting a recording immediately assigns the matching phrase and intent. Stop saves and downloads a mono PCM16 WAV at 48 kHz. Filename format: gate2_<INTENT>_<phrase_slug>_<UTC timestamp>.wav.

Store recordings locally in browser IndexedDB so they survive reloads and can be tested repeatedly. Also permit importing a labeled WAV from disk. No audio is uploaded to a cloud service or written to the server.

## Replay/test and logs
A saved/imported clip is padded with silence to the existing 5.92-second context and centered, then passed through independent raw and RNNoise Gate 2 v2 streams. RNNoise uses its normal 48 kHz / 480-sample frames; both model branches receive 16 kHz PCM. Show raw/filtered intent and confidence, and record timestamp, expected intent, branch results, and match status in a local test log. Provide CSV export and clear-log controls.

## Validation
- Test-first contract test for the separate route, phrase data, WAV labeling/download, IndexedDB replay, A/B run, log export, and navigation.
- Browser smoke test using a fake microphone: record a labeled WAV, verify file header/name, store and replay it, observe both real Gate 2 outputs, verify one log row/CSV export, then stop/cleanup.
- Re-run Gate 1, Gate 2 v2, RNNoise page, and live 2s cadence tests; verify all page routes and navigation return links with HTTP 200.
