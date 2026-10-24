# VCM Pipeline Dashboard — Raspberry Pi Handoff

Updated: 2026-10-24  
Device: Raspberry Pi at 192.168.1.75 (`lcsoneja`)  
Dashboard: http://127.0.0.1:8765/

## What was wrong

Before this release, the Pi served the dashboard page with HTTP 200, but `GET /api/lab/models` returned 404. The Pi's `gate1_server.py` was the older 77,582-byte build; the current laptop build was 130,834 bytes and exposes the Gate 2 model API. That mismatch explains why the Pi dashboard's current model/Best Models controls could not work.

## Current release contents

- Latest dashboard server and all 161 non-cache web runtime files.
- The active 56 Gate 2 model IDs and their TFLite model, labels, and preprocessing assets, stored under the exact Linux case-sensitive package names.
- Current Gate 1 runtime assets, model registry, specialist app/runtime packages, and the latest one-word response pack.
- Desktop dashboard icon and Linux restart script.

The release excludes training datasets/checkpoints and does not replace Pi-local recordings, logs, or sessions. It packages runtime assets rather than copying the entire 3.1 GB `Shipping` tree. Pi-local Call_Sounds and LoFiRadio folders remain in place.

## Verification completed — 2026-10-24

- Raspberry Pi dashboard page returned HTTP 200; `/api/lab/models` returned HTTP 200 with **56 Gate 2** IDs and 12 Gate 1 variants.
- Pi `gate1_server.py` matches the laptop release exactly (SHA-256 `7ceeb6f1e1cd644b7592d2f90aca8faa30305f5e0845fe0af5adf75b738a5817`).
- Gate2 V64P (benchmark winner), V56 (server default), and V77 each loaded on the Pi TFLite backend and completed a finite zero-input forward pass. This checks runtime load/inference only, not recognition accuracy.
- The updated Desktop restart script was run over SSH and returned after validating the page/API. On the Pi Desktop it also opens the page when a graphical session is available.
- No live microphone/noisy-room false-trigger test or browser-driven visual test was completed.

## Start or restart

On Raspberry Pi OS, click **VCM Pipeline Dashboard** on the Desktop. Or run:

```bash
~/Desktop/restart_vcm.sh
```

The restart script treats both the dashboard page and `/api/lab/models` as health checks; it expects 56 Gate 2 entries and restarts only the exact `python3 gate1_server.py` process if the API is stale. It then opens the dashboard.

A Windows `.bat` file is not a Raspberry Pi OS launcher; use `restart_vcm.sh`.

## Verify the Pi service

From a Pi terminal:

```bash
curl -fsS http://127.0.0.1:8765/ >/dev/null && echo 'dashboard page: OK'
curl -fsS http://127.0.0.1:8765/api/lab/models | python3 -c 'import json,sys; d=json.load(sys.stdin); print("Gate2 models:", len(d.get("models", [])))'
```

Expected API count: **56 Gate 2 model IDs**. Server log: `~/Exercise2/vcm_live_test_local/vcm_live_test_local/server.log`.

## Backup and rollback

The installer keeps the replaced app, model packages, and Desktop launch files under `~/Exercise2/_backups/vcm-<UTC timestamp>/`. It preflights the release before stopping the current server and automatically restores the prior files if the page/API health check fails.

## Gate 2 caveat

Updating the dashboard repairs stale UI/API assets and puts the latest model packages on the Pi. It does **not** prove that a Gate 2 model will never false-trigger in a quiet room: the published model ranking is based on command-bearing test clips, not silent-room false-activation rate. No real-time microphone/noise-room false-trigger test is claimed here; test this on the Pi before relying on it in a noisy demo.

Best-combination bookmark from the laptop benchmark: **G1 v3_f32 × G2 v64p_paired_owner · raw · v1** (91.2% fully correct on that benchmark). This benchmark result is not a guarantee of zero false triggers.

## Other Pi limitations observed

- The optional Gate3–Gate5 candidate config route (`/gate3to5/api/config`) returned HTTP 500 because its `infer.py` imports TensorFlow, which is not installed on the Pi. This does not block the Gate 2 dashboard/API; no TensorFlow install was attempted.
- Pi `tflite-runtime` 2.14.0 cannot load the Gate1 V10 dynamic-range export (unsupported FULLY_CONNECTED opcode version 12), so 12 Gate1 variants are exposed. Gate2’s 56 model options and the three tested Gate2 runners loaded successfully.
