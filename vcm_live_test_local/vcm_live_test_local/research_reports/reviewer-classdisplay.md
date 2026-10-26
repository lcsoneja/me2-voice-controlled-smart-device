# Class-display review

**Verdict — OK with a clarity note.** Three probability bars are correct: the v4 model/server labels are Nova, Piattos, Negative (`gate1_server.py:107`), and the UI renders those three values directly (`shared.js:195-226`). Per the verified v4 design, Negative includes silence/ambient; there is no fourth model output. Do not add a fourth *probability* bar. The Nova/Piattos sliders are wake thresholds, not class selectors (`vcm_monitor.html:59-61`).

## Findings
- **P2 — `gate1_web/vcm_monitor.html:46,59`; `gate1_web/js/shared.js:199,224-228`.** “Negative” does not plainly tell users that silence/ambient was merged into it, leaving the reason for three bars implicit. Clarify the bar/legend as **“Negative (silence/ambient; no separate silence output)”**. The positional field/ID mapping itself is consistent with the server output; no bar-mapping bug found.

## Recommended four-state operational display
Keep the three model-probability bars and add a separate, explicitly non-class status indicator. Exact rule, using server-owned values:
1. **SILENCE / BELOW FLOOR** iff the server's energy gate says `rms < floor` outside calibration (`gate1_server.py:219-228`). This is an energy-gated proxy, not a predicted class; the server skips inference here, so Negative probability is unavailable.
2. **Nova** or **Piattos** iff the server reports that wake as accepted. In `both` mode honor its 2-of-3 confirmation (`gate1_server.py:248-253`); in Gate 1-only mode honor the existing per-window threshold decision.
3. Otherwise, when `rms >= floor`, show **NO CONFIRMED WAKE / ENERGY PRESENT**. Do not call this “SPEECH-REJECTED”: RMS does not establish speech, and v4's known OOD-speech false-wake behavior makes that label especially misleading. A speech-rejected state requires a VAD/speech detector.

For consistent status across tabs, have the server emit a normalized status plus `rms`/`floor`; the current floor/gated event is only emitted in `both` mode, while Gate 1-only `probs` carries no RMS/floor (`gate1_server.py:205-212,226-228`). Do not derive silence from high Negative probability AND low RMS: the ordinary low-energy path skips model inference.

**Review limit:** `watchdog_diff` was not available in the registered tool surface; this is a source review, not a bounded working-tree-diff attestation. No tests run.