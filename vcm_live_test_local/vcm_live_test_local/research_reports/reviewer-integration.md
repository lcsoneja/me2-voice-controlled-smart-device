# Integration review

**Verdict: fix-first**

## Findings

- **P2 — `gate1_web/js/gate2.js:320-326`; `gate1_web/js/pipeline.js:196-202`** — Both tabs latch `LOW` as well as `PASS`. If a tick first matches the expected intent but is below threshold, then a later tick reports a high-confidence wrong intent, the newly computed `FAIL` is replaced by the latched `LOW`. That contradicts the live verdict rules in CONTRACT.md §§4/6; the accepted addition is PASS persistence. **Fix:** latch only `v-pass`; let LOW/FAIL/idle reflect each current tick.

- **P2 — `gate1_web/js/shared.js:25-28` (ranges in `vcm_monitor.html:59-60, 76`)** — Persisted thresholds are accepted if merely finite; they are not checked against the sliders' 0.05–0.95 range. For example, valid-but-corrupt `{"Nova":1.4}` is sent to the server, whose `probs[0] >= thr["Nova"]` comparison (`gate1_server.py:196, 208`) can never detect Nova, while the range input visually clamps to 0.95. **Fix:** reject out-of-range stored values or clamp/default and persist the sanitized values.

## Non-issues checked

- Shell IDs, deferred script order, VCM subscriptions, PHRASES counts/shape, and WS JSON/binary handling are consistent with the contract.
- WS `onopen` resends thresholds and the currently selected server mode; expectations/latches are per-tab and expectation-keyed, so tab switching/reconnect does not mix them.
- Missing or invalid-JSON localStorage falls back safely; mic rejection is surfaced, and suspended AudioContext gets a resume button.
- Static review only: E2E was not rerun (the supplied context reports it passed). `watchdog_diff` was not available in the registered review tools, so this is not an attestation of the bounded working-tree delta.
