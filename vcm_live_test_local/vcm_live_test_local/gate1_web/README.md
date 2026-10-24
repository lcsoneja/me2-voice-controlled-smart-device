# gate1_web — Gate 1 Wake-Word Web Monitor (gate1v2)

Live browser dashboard for the Gate 1 wake-word model: mic in, charts +
PASS/FAIL out, per-word thresholds, CSV/JSON log saving. Fully local.

## Files
- gate1_monitor.html — the app (UI only; inference runs server-side)
- gate1_server.py — local server: HTTP + WebSocket + exact gate1v2 TFLite inference
- gate1v2_float32.tflite — the Gate 1 v2 model (148-frame input, from the DGX shipping folder)
- mel_fb.npz — precomputed mel filterbank (60x513, matches the trained preprocessing)
- _generate_html.py — regenerates gate1_monitor.html
- _ws_inject_test.py — automated end-to-end test (injects WAVs over WS, checks banner)
- _screenshot.py — captures a WAKE-state screenshot
- gate1_forward_reference.py (project root) — numpy reference of the full gate1 forward pass

## Run

    python gate1_server.py
    # open http://127.0.0.1:8765/gate1_monitor.html
    # allow microphone access, then say "Nova" or "Piattos"

Requires: numpy, librosa, aiohttp, plus any TFLite runtime (tflite-runtime on the Pi,
ai-edge-litert or full TensorFlow on the laptop). Gate 2 v2 uses librosa for the
shipped log-Mel contract; inference remains local and server-side.

## How it works
Browser captures 16 kHz mono and streams PCM blocks over WebSocket. The server
maintains a rolling 5.92 s window (94,720 samples), computes 148-frame log-mel
features (same math as the trained pipeline; parity verified against
FeatureExtractor), runs gate1v2_float32.tflite every 1 s, and streams
{Nova, Piattos, Negative} probabilities back. Wake = any wake word prob >= its
threshold (sliders persist in localStorage and sync to the server).

## Why gate1v2 (not v1)
gate1v2 accepts the full 5.92 s window (148 frames) and fixes the v1 failure
mode where real/synthetic wake words were confidently rejected ("Negative" 1.0).
On the shipping validation set: Nova->Nova 1.000, Piattos->Piattos 1.000,
non-wake->Negative 1.000. The older terminal tool gate1_monitor.py still tests
v1 (74-frame) for comparison.

## Note for Raspberry Pi
The Gate 2 v2 TFLite model uses built-in operators only (no Select TF Ops/Flex).
The exact live preprocessing also requires librosa on the Pi; a lightweight
numpy-only Pi port has not been validated.
