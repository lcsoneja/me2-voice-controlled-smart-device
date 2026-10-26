# Gate 2 RNNoise A/B Test Page

## Approved scope
Build a standalone page at `/gate2_rnnoise_test.html`, linked from the existing monitor, to compare raw Gate 2 against RNNoise-cleaned Gate 2 simultaneously. Scope is Gate 2 only: do not alter the normal monitor's audio graph, Gate 1, or pipeline behavior.

## Data flow
Capture the microphone once in the browser. Fork the same mono audio into two independent branches:

- **Raw**: resample to 16 kHz Float32 and send over its own WebSocket to the existing server in `mode=gate2`.
- **RNNoise**: process at RNNoise's 48 kHz / 480-sample (10 ms) frame contract in a browser AudioWorklet using a locally hosted WASM bundle; resample the denoised result to 16 kHz Float32 and send over a second Gate 2 WebSocket.

Both branches use the same live Gate 2 v2 default, have independent server rolling windows, and update independently. WASM and its Apache-2.0 license are hosted locally; no CDN or audio upload is used. Candidate package: `@jitsi/rnnoise-wasm@0.2.1`, whose sync build is specifically intended for AudioWorklet use.

## Page behavior
Two aligned panels show branch status, top intent, confidence, and probability bars for all 19 intents. A shared expected-intent selector reports each branch's match separately. Show input/output RMS and processing state so changes are visible even when the model's top intent is unchanged. Show clear permission/WASM/WebSocket errors and a stop button that closes both sockets, audio nodes, and mic tracks.

## Performance and safety
Two Gate 2 streams approximately double Gate 2 inference work while the test page is open. RNNoise adds frame buffering/processing latency; display the observed branch timing rather than claiming zero latency. Browser-only A/B test; do not change server model or production Gate 1 path. Each WebSocket gets its own Gate 2 mode and rolling buffer.

## Validation plan
1. A failing test first checks the route, page, local RNNoise asset/license, separate raw/processed Gate 2 streams, and 480-frame processing contract.
2. Run a headless browser smoke test with fake microphone input: confirm permission/start, local WASM initialization, two active Gate 2 streams, inference updates in both panels, and clean stop.
3. Run Gate 2 v2 and Gate 1 integration suites; verify normal monitor page remains unchanged and server endpoints return HTTP 200.
