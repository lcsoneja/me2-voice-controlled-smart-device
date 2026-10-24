# Gate3–Gate5 Slot-Specialist Candidate App

A local HTML frontend with a Python/TensorFlow backend for one short WAV clip at a time. The app loads the read-only candidates from `../Shipping/Gate3to5_SlotSpecialists_Candidates_20261009`; it does not copy or modify model weights, reports, or training data.

## Unified one-server launch

From the Exercise 2b folder, run:

```bat
run_all_local.bat
```

Or run `run_local.bat` from this app folder; it forwards to the same launcher. It starts **one** server process inside a **native desktop window** ("VCM Monitor — Gate 1–5") with standard minimize/maximize/close buttons: the window IS the app, and closing it exits the server. The unified Gate1/Gate2 server serves **127.0.0.1:8765** with this isolated Gate3–Gate5 backend mounted under `/gate3to5/`; select **GATES 3–5 · slot candidates** in the tab bar. The monitor tab and candidate app link back to each other. No second port or second server is used. If the native window is unavailable, the launcher falls back to the console + default browser. To end it, close the server window (or press Ctrl+C in it), or double-click `stop_all_local.bat` in the Exercise 2b folder. The server is an ordinary Windows app you start and stop yourself — it does not need this coding session to be open.

No cloud service, external API, CDN, analytics, or remote storage is used. The candidate code and assets remain in this isolated app directory; the main server mounts its routes without copying or modifying shipped weights.


## Runtime

Use 64-bit Python 3.12 with TensorFlow 2.21 / Keras, librosa, NumPy, soundfile, and aiohttp. The bundle README specifies TensorFlow 2.21.0, NumPy 2.5.3, librosa 1.0.0, and soundfile 0.14.0. The local compatibility smoke passed with TensorFlow 2.21.0, Keras 3.15.1, NumPy 2.2.6, librosa 1.0.0, and soundfile 0.14.0. The app uses the shipped `infer.py` preprocessing contract and reads normalization statistics and output order from the bundle assets.

If the bundle is elsewhere, set `GATE3TO5_BUNDLE_DIR` to its directory before launch. The bundle path is read-only from this app.

## Select gates and ratios

The page supports only:

- Gate3a Timer
- Gate3b Alarm
- Gate3c Temperature
- Gate3d Brightness
- Gate5 Reminder Content

Gate4 Color and Gate2v8 are not included. You must select both a gate and a ratio (`neg1x` or `neg2x`) before running inference. Neither ratio is promoted; the app does not choose one automatically. Output labels and their order come from the shipped `labels.json`.

## Audio and scores

Upload one WAV clip. It is decoded in memory, resampled to 16 kHz mono if needed, and preprocessed as the shipped Gate2v6 contract: 148×60 log-Mel features with the bundle's scalar normalization. The model's input window is **5.92 seconds**. A longer clip is rejected with a message; the app does not stream it or silently truncate it. Short clips are padded as in `infer.py`.

The page shows the selected gate/ratio, top label, and all class scores. Scores are explicitly labelled **uncalibrated model scores, not confidence**. `REJECT` is displayed clearly as a class; no calibrated rejection threshold is applied.

Uploaded bytes are held in memory for inference only. The app creates no audio temp files and does not save or log audio. The app does not collect predictions into a persistent log.

## Tests

Run from the Exercise 2b folder:

```powershell
py -3.12 -m unittest discover -s Gate3to5SlotSpecialistApp/tests -t . -v
```

The browser smoke test is separate and uses only a generated synthetic WAV:

```powershell
py -3.12 Gate3to5SlotSpecialistApp/tests/test_browser.py
```

The smoke input is generated synthetic audio and checks model loading, preprocessing, and output shape only. It is **not** a recognition-accuracy test. No MEX2 test audio, Owner150 audio, or private/evaluation examples are used.

This is a local candidate-inspection tool, not a final consolidated model. No ratio is promoted. Raspberry Pi or production readiness is not claimed; no Pi benchmark or real-microphone test has been performed.
