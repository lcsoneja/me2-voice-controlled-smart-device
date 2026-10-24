# VCM Pipeline Dashboard - Raspberry Pi Handoff
*Deployed: 2026-10-24*

## What is running

- **Server**: `gate1_server.py` at `~/Exercise2/vcm_live_test_local/vcm_live_test_local/` on port **8765**
- **Dashboard**: http://127.0.0.1:8765/pipeline_all_in_one.html
- **Models**: 56 Gate 2 models (incl. V77 speech-OOS NEG, V72/V76 layer stacks) + 13 Gate 1 variants
- **Best combination**: G1 v3_f32 x G2 v64p_paired_owner | raw | v1 (91.2% fully-correct)

## Desktop icons

| Icon | What it does |
|------|-------------|
| **VCM Pipeline Dashboard** | Starts the server if down + opens the dashboard |
| **VCM Gates Dashboard** | The older DemoApp dashboard (port 8768) |
| **VCM Room Simulation** | Opens the room simulator page |
| **restart_vcm.sh** | Kills + restarts the server, then opens the dashboard |

## How to restart

Click **restart_vcm.sh** on the Desktop, or from a terminal:
```bash
~/Desktop/restart_vcm.sh
```

## Key paths

| Item | Path |
|------|------|
| Server code | `~/Exercise2/vcm_live_test_local/vcm_live_test_local/gate1_server.py` |
| Web assets | `~/Exercise2/vcm_live_test_local/vcm_live_test_local/gate1_web/` |
| Model packages | `~/Exercise2/Shipping/` |
| Server log | `~/Exercise2/vcm_live_test_local/vcm_live_test_local/server.log` |

## Demo flow

1. Click **VCM Pipeline Dashboard** on the Desktop
2. The dashboard opens in the browser
3. Click the star-1 bookmark to apply the best combination
4. Speak: "Nova" or "Piattos" (wake) + your command
5. The pipeline detects + executes the action

## Troubleshooting

- **Server will not start**: check `tail -20 ~/Exercise2/vcm_live_test_local/vcm_live_test_local/server.log`
- **Port 8765 busy**: run `pkill -f gate1_server` then restart
- **Models missing**: the Shipping packages must be at `~/Exercise2/Shipping/`
- **Full reset**: run `~/Desktop/restart_vcm.sh`

---

*SSH access: key-based (ED25519, no password) from the laptop via `ssh lcsoneja@192.168.1.75`*