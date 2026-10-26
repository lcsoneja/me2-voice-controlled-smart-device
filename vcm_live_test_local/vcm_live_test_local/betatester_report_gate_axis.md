# Beta-tester report — recording-test frame: two-pane, summary digest, batch, gate-order axis

Date: 2026-10-24 · Target: http://127.0.0.1:8765/pipeline_all_in_one.html (server was already running; not restarted)
Take under test: `20261023_155245_2dd71e` (tags wake=`Piattos`, action=`Play_music`)
Tools: Playwright chromium (`channel=msedge`, headless, `--use-fake-*` media flags) + python urllib API probes. No app code modified.

## Verdict
**PASS** — all 6 checks (a–f) pass. Three low-severity cosmetic findings, no blockers.

## PASS/FAIL table

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| a | Two-pane frame side by side | **PASS** | `#rf-left` box x=22 w=520 (right edge 542); `#rf-right` x=556 → `right.left (556) >= left.right-2 (540)` = true; both exist after `#all-recframe-toggle`. |
| b | Summary digest after run (g1v10_dr × g2v16, nc=off, gate=both) | **PASS** | `#rf-summary`: "gate order A/B" ✓, "2 combinations · fully correct 0 · Gate 1 (wake) correct 0 · Gate 2 (action) correct 0" ✓, timeline strip present (1 element `height:36px` with 7 markers, e.g. `"wake fired 6.9s"`, `"intent TIME 5.9s (98%)"`) ✓, "Wake fired at:" ✓, "Intent fired at:" ✓. Lane picker change re-rendered the timeline (see note b). |
| b-picker | Lane picker changes the timeline on change | **PASS** | Exercised with nc=on (both gate-order lanes fire): picker had 2 options `G1v10_dr × G2v16 · NC on ✗` and `G1v10_dr × G2v16 · NC on · gated ✗` (combo name carries "· gated"); changing selection swapped the lane text `Wake fired at: 6.9s · Intent fired at: 5.9s TIME,…` into `… · gated · … Intent fired at: 7.9s TIME,…`. |
| c | `#rf-results` cards capped with digest note when many lanes ran | **PASS** | Run with 5 G1 × 3 G2, nc=off, gate=both = **30 lanes** → note present: "30 combinations ran — showing the 18 lanes that actually triggered; the summary above has the full digest." |
| d | Batch multi-take testing | **PASS** | Ticking 2 recpane checkboxes → `#rf-batchstart` reads "▶▶ Batch test (2 takes)"; click → `#rf-prog` = "batch done"; `#rf-results` children = [Batch header, section1, section2]; header = "Batch: 2/2 takes tested · gated lanes included — per-take summaries above"; 2 per-take sections (expected wake Nova/lights_on and Piattos/Play_music). |
| e | API gate-order axis | **PASS** | `POST /api/recordings/20261023_155245_2dd71e/test {"g1_models":["gate1v10_dr"],"models":["gate2v16"],"hop_s":1.0,"nc_modes":[true],"gated_modes":[false,true]}` → `job.gated_modes=[false,true]`, 2 four-tuple combos `[[…,true,false],[…,true,true]]`, 2 summaries with `gated` false/true, all 8 events carry `gated`; gated lane first g2 = **7.92s ≥** first g1 = **6.92s** (parallel lane g2 fires at 5.92s before g1 6.92s, as expected for always-on). |
| f | Regression `_probe_recframe.py` | **PASS** | `py -3.12 _probe_recframe.py` → exit 0; recframe display "block", 20 rec options, 25 result cards, prog "done in 0.28 s", no page/console/http errors. Say line confirms axis math: "running 6 pairs × 2 NC modes × 2 gate orders = 24 lanes…". |
| f+ | Regression `_probe_rf_controls.py` | **PASS** | exit 0; select-all "13×48=624 combinations", clear-all "0/0", quick-set "2/6", pause/resume/stop say-lines correct, no page errors. |

## Findings (low severity, no blockers)
1. **(b) picker under exact specified config.** With `nc=off` the listed variant `gate1v10_dr` never fires the wake on this take (confirmed by API: g1 events = 0 with nc off vs 1 with nc on), so the gated lane produces no events and the lane picker has only one option — the "change the timeline" behaviour cannot be observed in that exact configuration. It was verified with `nc=on`, where both gate-order lanes fire. Not a defect; a data/model-selection artifact of the suggested config.
2. **(d) per-take section heading is wiped.** `startBatch()` appends the per-take heading `"N. <label> · X combinations · gated lanes included"` to the section, then `rfSummary(job, sec)` starts with `host.textContent = ""`, erasing it. Sections survive and are distinguishable by their "Summary — expected wake/action" line, but the numeric/label heading is lost.
3. **(cosmetic) stale `#rf-lanecount`.** `updateCount()` is only bound to checkbox `change`; changing `#rf-ncmode` / `#rf-gatemode` alone leaves the displayed lane count stale (e.g. showed "4 gantt lanes" while the run used 2). The actual job payload is correct.

## Reproduction commands
- API (e): python urllib POST as above; poll `GET /api/jobs/{id}`.
- Browser (a–d): Playwright chromium(channel=msedge, headless, fake-media args) → open page, `#all-recframe-toggle`, set `#rf-rec`/`#rf-g1box`/`#rf-mbox`/`#rf-ncmode`/`#rf-gatemode`, click `#rf-start` or `#rf-batchstart`, read `#rf-summary`/`#rf-results`.
- Logs: `logs/live_2026102{2,3}.jsonl` — only `kind:"beta-probe"` synthetic entries, no real errors.
