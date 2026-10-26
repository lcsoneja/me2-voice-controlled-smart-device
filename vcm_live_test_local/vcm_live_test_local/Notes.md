# Agent Notes — VCM Live Test Local

_Generated 2026-10-22 · agent: Pi / GPT-6 Luna · workspace: `vcm_live_test_local/vcm_live_test_local`_

## Purpose
Live voice-command pipeline testbed (Gate 1 wake + Gate 2 intent, TFLite) with a browser dashboard, plus a model-testing workflow for the newly shipped Gate 2 packages.

## Environment
- Windows laptop, Python 3.12 (`py -3.12`). Local server: `http://127.0.0.1:8765/pipeline_all_in_one.html` (also served as `.thml`).
- Deployment target: Raspberry Pi 5 `192.168.1.75`, user `lcsoneja`, service `vcm-gates.service`, app at `/home/lcsoneja/Exercise2/vcm_live_test_local/vcm_live_test_local/`. **SSH was unreachable in the latest sessions — all recent changes are laptop-local only, NOT deployed.**
- Live probes that target `ws://127.0.0.1:8766` (Pi tunnel) fail while the tunnel/Pi is down.

## Key files
- `gate1_server.py` — aiohttp WS server (port 8765) + full pipeline logic.
- `gate1_web/pipeline_all_in_one.html` (+ byte-identical `.thml` mirror) — the one-page dashboard.
- `gate1_web/pipeline_frames.py` — 20 s ring buffer of 1 s frames; 6-frame (~5.92 s) scoring window.
- `gate1_web/_*.py` — pytest suites and one-shot probes.
- `Exercise 2b/HTML_AND_MODELS_CATALOG.md` — catalog of dashboards/models (open in VS Code for the user).
- `research_reports/nc-benchmark-20261017.md` — noise-canceller benchmark report.

## Architecture (server)
- WS `/ws`; a per-connection `ticker` closure drives evaluation. `tick_interval` selectable 1/2/3/6 s (default **1 s** per user request); skip-ticks toggle and pipeline reset are dashboard options.
- Mic frames accumulate into the 20-second memory ring (20 × 1 s); the scoring window stays 6 one-second frames (~5.92 s), exactly as before — only the evaluation cadence changed.
- Gate 1 wake (2/3 vote window, 5 s cooldown) latches `PipelineActivationWindows` (8 s/4 s); Gate 2 scores the active window with the selected variant's runner adapter.
- Gate 2 adapters load shipped TFLite packages from `Shipping/`; slide-window builds use `_slide_window_features` with per-family offsets {1: (), 5: (-50,-25,0,25,50), 9: (-50..50), 17: (-100..100)}; `_resize_area` area-resizes features; shared pad value -0.14782163.
- **V56 champion** (`gate2v56_v54`, `gate2v56_v54b`): V46 9-window backbone + shipped streaming PID calibration. Per-connection PID state, reset on silence/mode/reset/stop/action. Configs in `GATE2_PID_CONFIGS`: v54 {tau 0.4, kp 0.4, ki 0.05, kd 0.1, kc 0.0}, v54b {tau 0.25, kp 0.6, ki 0.02, kd 0.1, kc 2.0}.
- **Delay indicator (new):** every pipe tick reports `scheduler.eval_ms` (tick scoring time) and `scheduler.late` (eval > interval). Dashboard shows "eval N ms · ⚠ DELAYED" in red when late.
- Noise canceller: tracked ambient profile + spectral subtraction (owner-voice retention ~93% median, 3.8 dB attenuation on real silence). Wiener alternative benchmarked better (98.96%/96.37% retention, 3.60 dB) but is not wired in — see benchmark report.

## Dashboard
- All-in-one page: 20 s memory ring, action lights, Gate/Gate2 trigger Gantt chart, embedded VCM room simulation (left column), noise-canceller switch and memory choice persist across reconnects.
- Scheduler status line: interval, skipped_ticks (ON/OFF toggle), eval_ms, DELAYED badge; reset button re-syncs pipeline state; interval selector 1/2/3/6 s.
- `.thml` mirror must stay byte-identical — re-sync with PowerShell `Copy-Item` (a truncated `pi.read` once corrupted it; hash check now guards this).

## Models — Gate 2 registry
- **55 registered packages, all of which load** (`py -3.12 _check_gate2_models.py` load-checks every one and exits non-zero on a failure). 15 documented exclusions in `GATE2_DISABLED_CANDIDATES`, each with its reason.
- Newest check (2026-10-25): the V66 experiment family. `gate2v66m_mutation` is a complete 9-channel package (integrity verified against its SHA256SUMS) and is now registered. `gate2v66a_3extra` (12-ch), `gate2v66d_2extra` (11-ch) and `gate2v66c_4extra` (13-ch) ship complete files but their specs build extra channels from the DGX-side `extra_channels_a/_d/_c` configs, which the packages do not include - feeding them an invented recipe would silently produce meaningless scores, so they are disabled until those definitions arrive. `Gate2V54B_PIDReject` is a PID layer for base models, not a standalone model.
- Server default is still `gate2v21p`; the one-shot page overrides it per connection with the first row of the ranking file, which is now `gate2v64d_expandedneg` (see the ranking note below).
- Includes `gate2v22` (user-requested) and the champion pair `gate2v56_v54` (accuracy winner) / `gate2v56_v54b` (rejection winner).
- **2026-10-25/26 DGX batch wired in.** Eleven V64d-derived models shipped TFLite but no spec/labels; they reuse the V64d package through the runner's `spec_dir` fallback, and a new output-size guard fails loudly if a package's head does not match its labels (before it would silently score near zero). Measured on the 86 real-voice clips: **V108 (owner-FT of V93b), V109 (owner-FT of V96c) and V96c (V93b re-run) all reach 93.0% (80/86)**, above the previous best V64d / V64p / V56-V54 at 91.9%.
- The rejection pair is the interesting trade-off: **V82b speech-OOS w0.35 = 90.7% real at 87.5% OOS reject** and **V82 speech-OOS = 88.4% at 93.8%**, against V64d's 37.5% at 91.9%. If trap rejection matters in the demo, V82b costs only 2 clips of command accuracy and rejects 14 of 16 traps instead of 6.
- Their own owner-280 verdicts (V96a 87.86 FAIL, V110 overfit) do not reproduce on the holdout (both score 91.9% here): owner-280 is a fit metric on V64d's training distribution, not an independent test.
- 16 further new packages are documented as disabled with reasons (rank-5 Conv3D input, single-output binary heads, 167-output phoneme heads, 18-channel distance frontend, 148x549 compact layout, or no TFLite exported at all).
- **Ranking basis (2026-10-25): real voices only.** `_bench_gate2_holdout.py` splits the ME2 holdout into 86 real-voice clips, 100 synthetic clips and 16 OOS clips. Nearly every model scores 100% on the synthetic tier, which is why the old 186-clip number was compressed and misleading; the dropdown now sorts and labels by `acc_real` and the caption states that synthetic and OOS are excluded. Ties keep the file's order (combined accuracy, then OOS rejection).
- Known parameter counts (manifests): v2/v6 415,635; v16/v18/v19/v19p 246,035; v21/v21p 246,100; v22/v22s 378,708. V46/V56 counts live in the package manifests.
- `gate2v6` TFLite needs Flex ops (unavailable locally) — documented in the catalog.

## Models — Gate 1 wake registry (2026-10-22)
- **Default switched from `gate1v8_f32` to `gate1v12_f16`** (`DEFAULT_G1_MODEL`; V8 stays registered, selectable, and first in the fallback chain). Measured on the two synthetic wake clips + two command clips (script: `_probe_wake_models.py`):

| Clip | V8 f32 (old default) | V12 f16 (new default) |
|---|---|---|
| wake Nova | Nova 0.879 ✓ | Nova 0.996 ✓ |
| wake Piattos | **Nova 0.915 ✗ (persona wrong)** | Piattos 1.000 ✓ |
| command "Call" | Negative 1.000 ✓ | Negative 0.922 ✓ |
| command "Stop" | **Nova 0.943 ✗ (false wake)** | Negative 0.815 ✓ |

- V12 ships **no `feature_stats` file**; it rides the V8 train-only stats (`feature_stats_v8_148.npz`, mean 0.02904 / std 0.22909). That choice is measured, not assumed: under all five shipped candidates (v3/v4/v5/v8/v10) the wake clips score >0.99 for their persona and the command clips stay Negative, with differences in the 3rd decimal (`_probe_v12_stats.py`).
- **Gate1V8C is staged but DISABLED** (`GATE1_DISABLED_CANDIDATES`): its input is (1,49,40,1), so it needs a 49×40 wake frontend adapter. Its report is the strongest wake evidence in the tree (pure TC-ResNet, 224,259 params, 468 KB f16, sealed 19/20 — Nova 9/10, Piattos 10/10) and it is BUILTINS-only, so it is the best next wake candidate once the frontend recipe (DGX-side, `dataset_v8_2/features_v8_2`) is available. Model file staged at `gate1_web/gate1v8c_float16.tflite`.
- V10 remains selectable, never default (sealed-benchmark failure: on the synthetic Nova clip it returns Negative 0.739).

## Assistant replies — one-word pack + wake ack (2026-10-22)
- `/assistant-responses/` now serves **`Shipping/Gate2_AssistantResponses_ONEWORD_20261022`** (80 clips: 19 intents × 2 personas × 2 variants + `resp_<persona>_wake_<1|2>`), selected by `_select_assistant_pack()` with the 2026-10-17 verbose pack as fallback and `VCM_ASSISTANT_PACK` as override.
- Captions come from the pack's `responses_manifest.csv` (`ASSISTANT_TEXTS`): the dashboard subtitles the words it actually speaks ("On", "Yes?") instead of the old long sentences.
- **Wake ack:** on each Gate 1 latch the server attaches `wake_response` {url, persona, text, event_id, room_active} to that tick's pipe payload — one ack per latch (`guard["wake_ack_seq"]`). The dashboard plays `resp_<persona>_wake_1.wav` ("Yes?" Nova / "Hi" Piattos) and captions it; `room_sim.html` does the same when a room viewer owns the voice. Live proof: `py -3.12 gate1_web/_wake_ack_probe.py Nova gate1v12_f16`.
- The Pi demo app (`DemoApp`) now prefers its own one-word pack (`responses/oneword-sapi`, 78 clips, every reply one word): `PACK_ORDER`, `pi_runtime/config.json`, `demo.py` resolver, and `install.sh` staging all updated; CosyVoice/placeholder packs stay as fallbacks.

## Gate2 program handoff alignment (Shipping/HANDOFF_GATE2_MODELS_20261020.md)
- Handoff deployment pick for the AI231 ME2 live benchmark: **primary V46** (holdout champion 89.53% real / 95.16% cmd, 338k params, 0.562 ms host); **V46 + V54 PID** is the program record (96.24% / 91.86%). Alternative owner pick V41; Pi-budget pick V19.
- Rejection layer options: V22-NEG (~31% trap catch) or V54b margin-PID — now shipped in V56 (6.25% reject on V46, 43.75% on V22). A combined **V22 + V54b** selector entry does not exist yet.
- Handoff said "V54b designed, not run" — stale as of 2026-10-22; recorded in the handoff addendum (§9).
- Open items inherited from the handoff: ME2 benchmark logging to `~/vcm_benchmark/`, fresh owner session, INT8/Pi latency, S1b/S2/V55. `vcm8/training/holdout_check.py` is DGX-side and not present on this laptop.

## Tests
- `py -3.12 -m pytest gate1_web/_gate2_today_models_test.py -q` (7) — shipped-options coverage.
- `py -3.12 -m pytest gate1_web/_delay_indicator_test.py -q` (4) — delay telemetry + THML sync.
- `_realtime_pipeline_test.py` (89) — live pipeline, cadence, Gantt, room sim, reset.
- `_oneword_assistant_pack_test.py` (15) — pack selection, clip formats, one-word captions, wake-ack wiring, THML sync.
- `_wake_model_registry_test.py` (7) — V12 default + contract, V8C disabled reason, wake/command verdicts, selector pinning.
- Baseline suite: **145 passed, 2 subtests** (`py -3.12 -m pytest gate1_web -q`). Smoke = plumbing only, **not accuracy**.
- pi-lens/pyright may briefly report `gate1_server` attributes as unknown; verified false at runtime (hasattr checks + green tests). Refresh with `extensions.lens_diagnostics({refreshRunners:'cheap'})` before trusting it.
- **Lint verification must run from the workspace root** (`Exercise 2b`, matching the checker's cwd): `ruff check --select I,SIM117,SIM118,E701,E702,F401 <relative paths>`. Ruff's first-party/third-party import classification depends on cwd — run from the app dir, `recording_lab`/`gate1_server` classify as first-party and the expected import order flips. ruff binary: `C:/Users/Leandro/AppData/Roaming/Python/Python314/Scripts/ruff.exe` (0.16.8).

## Recording Lab — capture → replay → trigger charts (2026-10-22)

- **Page:** `/recording_lab.html` (linked from the dashboard's "⏺ Save last 30 s" status line). Backend: `recording_lab.py` + routes in `gate1_server.py` (`/api/recordings*`, `/api/lab/models`, `/api/results*`, WS `save_capture`).
- **Capture:** the WS handler keeps a 30 s rolling ring of every streamed sample; the dashboard's "⏺ Save last 30 s" button snapshots it into `recordings/` and replies `capture_saved` with a link to the lab. Repeatable: every click saves a new timestamped take; the button re-enables on the reply, on any reconnect, and via an 8 s fallback so it cannot stick on "Saving…". Verified by the two-capture loop in `_lab_e2e_probe.py`.
- **Benchmark matrix (2026-10-22):** the lab replays one take through a matrix of (Gate 1 variant × Gate 2 model) combos — `start_test(rec_id, combos, runner_factory)`; wake is scored once per Gate 1 variant per tick and fanned to its Gate 2 combos; Gate 3 runs once per pending trigger. Events carry `g1_model` + `model`; summaries are per combination. Cancel: `POST /api/jobs/{id}/cancel` + Stop button. Lab page has Gate 1 + Gate 2 checkbox grids (quick sets) and per-combination charts ("v12 × v21p").
- **Dashboard benchmark toggle:** top-right "📊 Benchmark gantt" button switches the Trigger-Gantt panel between the live timeline and saved runs (dropdown from /api/results, per-combination G1/G2 lanes). Mic waveform + room sim stay live.
- **Intent phrase tooltips:** hovering an action-light card shows every phrase variant for that intent (from `VCMPIPE2_PHRASES.G2` via `allPhrases()` in pipeline_v2.js).
- **Skipped-window log + drift:** when an evaluation overruns the cadence, the server logs wall-clock moments (`scheduler.skipped_log`, last 12) and cumulative `drift_s` ("frames behind the realtime clock"); the dashboard scheduler line shows "behind realtime +Xs" (red > 2 s) and the skip list below it. Tests: `_delay_indicator_test.py` extended.
- **Replay:** one saved recording walks through every selected Gate 2 model with live-faithful semantics (5.92 s window stepping 1 s, 2-of-3 wake vote + 5 s cooldown, 12 s/8 s latches, 6 s wake-ordering grace, per-intent thresholds, V56 PID state reset per job). Gate 3: the routed specialist (gateN/gate4/gate5 legacy trio) scores the trailing 8 s window once per pending trigger.
- **Charts + history:** every finished job auto-saves to `recordings/results/<job>.json`; the lab page lists saved runs ("best: model (n triggers)") and re-draws the per-model Gate 1/Gate 2/Gate 3 trigger chart on demand. This is the trust-building A/B: the SAME audio through v21p vs v46 vs v56 (V46+PID) shows exactly which model fires.
- **Tests:** `gate1_web/_recording_lab_test.py` (7) — store round-trip, g1→g2→g3 flow, stale-command blocking, in-grace firing, confidence-dip re-arm, result persistence, specialist-error isolation. End-to-end proof: `gate1_web/_lab_e2e_probe.py` (stream 30 s → capture → 2-model replay → results) — PASS.
- **Lint convention:** verify from the workspace root: `ruff check --select I,SIM117,SIM118,E701,E702,F401 <relative paths>` (ruff 0.16.8 at `C:/Users/Leandro/AppData/Roaming/Python/Python314/Scripts/ruff.exe`). Import classification is cwd-dependent, so app-dir runs give false flags.

## Pending / next steps
1. **Deploy to Pi** when `192.168.1.75` is reachable: sync `gate1_server.py`, `gate1_web/pipeline_all_in_one.html` + `.thml`, and any missing `Shipping/` packages; restart `vcm-gates.service`; smoke-test 8766.
2. **Accuracy scoring:** run Score 280 recordings per Gate 2 variant, one session at a time, then restore `gate2v21p`; for the independent exam prefer the handoff holdout (`holdout_check.py`, DGX-side) over the reused owner-280 panel.
3. **ME2 benchmark logging** per handoff §7: Pi must log `{intent, slot, infer_ms, audio_ms}` to `~/vcm_benchmark/<id>_<datetime>.log` — not yet implemented in `gate1_server.py`.
4. Optional: wire Wiener noise cancellation (98.96%/96.37% retention, 3.60 dB attenuation) after operator sign-off.
5. Decide deployment default: handoff recommends V46 (or `gate2v56_v54` for the PID record) over the current `gate2v21p` default — operator decision.
6. **Wake gate open items:** (a) V12 has no sealed benchmark — needs a fresh recording session; (b) implement the 49×40 frontend adapter to unlock Gate1V8C (best wake evidence in the tree); (c) the new V12 default is laptop-side only until the Pi is reachable.
7. **Known environment issue:** running the whole `DemoApp/tests` directory in one pytest process dies with a native fault (0xc000001d / access violation) inside the TensorFlow/keras stack, while every file passes on its own (`test_actions` 5, `test_build_app` 2, `test_demo_server` 4, `test_pi_dashboard_launcher` 2, `test_pi_desktop_launcher` 4, `test_pi_runtime_installer_paths` 6, `test_responses_speak` 5, `test_response_pack` 6). Run them per file; not caused by the pack switch.