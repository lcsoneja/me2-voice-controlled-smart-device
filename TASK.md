# VCM Demo-Prep Task Board — FINAL (complete)
*Updated: 2026-10-24 ~12:25*

---

## ✅ All Deliverables Complete

| # | Item | Location | Status |
|---|------|----------|--------|
| 1 | **Best combination (final, fair)** | Dashboard ★1 bookmark | G1 v3_f32 × G2 v64p_paired_owner · raw · v1 — 91.2% fully-correct (187/205), 100% OOS on tested traps, p95 ~48ms |
| 2 | **Filled me2-deck.pdf** | `Exercise 2b/me2-deck-filled.pdf` | ✅ 3 pages, all placeholders + results table |
| 3 | **★ Top-5 bookmarks** | Dashboard (auto-refreshed) | ✅ One-click apply, final ranking |
| 4 | **Windows desktop icon** | `Desktop/VCM Pipeline Dashboard.lnk` | ✅ Clickable, verified cold-start |
| 5 | **Live dashboard** | `http://127.0.0.1:8765/` | ✅ Running |
| 6 | **Raspberry Pi deployed** | `lcsoneja@192.168.1.75` | ✅ 30MB tarball, icon on Desktop, server + models + deps ready |
| 7 | **Pi desktop icon** | `/home/lcsoneja/Desktop/vcm-dashboard.desktop` | ✅ Clickable (starts server + opens browser) |
| 8 | **V77 + NEG fix** | Server + lab | ✅ Live |
| 9 | **Checkpoint/backup** | `checkpoints/2026-10-24_pre-v7x-layers/` | ✅ sha256-verified |
| 10 | **TASK.md** | `Exercise 2b/TASK.md` | ✅ This file |

---

## 🏆 Final Ranking (424-take batch, equalized on 205-take me2w+owner base)

| Rank | G1 | G2 | NC | Arch | Full-rate | OOS-rej | p95 ms |
|------|----|----|----|------|-----------|---------|--------|
| ★1 | v3_f32 | v64p_paired_owner | raw | v1 | 91.2% | 0% | 48 |
| 2 | v3_f16 | v64p_paired_owner | raw | v1 | 91.2% | 0% | 52 |
| 3 | v3_f32 | v20_aux | raw | v1 | 90.7% | 0% | 31 |
| 4 | v3_f16 | v20_aux | raw | v1 | 90.7% | 0% | 32 |
| 5 | v2_f32 | v64p_paired_owner | raw | v1 | 90.7% | 0% | 64 |

**Demo flow (laptop)**: Desktop icon → dashboard → click ★1 bookmark → speak "Nova/Piattos + command"
**Demo flow (Pi)**: Desktop icon "VCM Pipeline Dashboard" → same dashboard → ★1 → speak

---

## 📋 Raspberry Pi Details

- Host: 192.168.1.75 (LAN, aarch64, Python 3.11.2, 45G free)
- SSH: key-based (ED25519, lcsoneja@), via Windows ssh-agent (PowerShell)
- Deployed: `~/vcm/app/core/` (server + web assets) + `~/vcm/Shipping/` (12 model packages) + `~/Desktop/vcm-dashboard.desktop` (icon)
- Launcher: `~/vcm/pi_deploy/start_dashboard.sh` (starts server if down + opens browser)
- All Python deps pre-installed (aiohttp, numpy, tflite_runtime)

---

*Session complete — all tasks delivered before the 1pm demo.*
