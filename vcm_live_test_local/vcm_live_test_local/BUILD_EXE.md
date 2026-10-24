# Building VCM_OneShot.exe

The desktop app is packaged with **PyInstaller** (installed as 6.22.3):

```powershell
py -3.12 -m pip install pyinstaller          # once
cd "C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2b/vcm_live_test_local/vcm_live_test_local"
py -3.12 -m PyInstaller --noconfirm --clean --onefile --windowed --name VCM_OneShot --icon vcm_pipeline.ico VCM_OneShot_App.py
copy dist\VCM_OneShot.exe .
```

Result: **VCM_OneShot.exe, ~16.9 MB**, beside `gate1_server.py`.

## Windows may refuse to run it: Smart App Control

On a machine with **Smart App Control** enabled (Windows Security -> App & browser control),
Windows blocks freshly built unsigned executables. Double-clicking the exe then does nothing at
all, and the Code Integrity log shows why:

```text
Microsoft-Windows-CodeIntegrity/Operational, event 3077 / 3033
"Code Integrity determined that a process ... attempted to load
 ...VCM_OneShot.exe that did not meet the ... signing level requirements"
```

Check the state first:

```powershell
(Get-CimInstance -Namespace root/Microsoft/Windows/Defender -ClassName MSFT_MpComputerStatus).SmartAppControlState
```

If it reports `On`, launch the app with the **Desktop shortcut or `Start_VCM_OneShot.bat`**
instead: they run `pythonw.exe VCM_OneShot_App.py`, and `pythonw.exe` is signed by the Python
Software Foundation, so it is allowed to run. **The Desktop shortcut "VCM One-Shot" was
retargeted to `pythonw.exe VCM_OneShot_App.py` for exactly this reason**, so a double-click works
on this PC. The exe is kept for machines without Smart App Control; there, point a shortcut at
`VCM_OneShot.exe` (or keep using the .bat, which works everywhere Python 3 is installed).


## What the exe is

A **launcher**, not a sealed bundle. The exe contains the app window (pywebview) and its Python
dependencies; the pipeline itself stays external and is used from this folder:

| Required beside the exe | Why |
| --- | --- |
| `gate1_server.py` | the pipeline server the app starts and stops |
| `gate1_web/` | the dashboard pages, including `oneshot.html` |
| `vcm8/`, models | Gate 1 / Gate 2 weights and specs |
| a Python 3 install on PATH | the server runs under Python (`py -3.12` is tried first) |

The app resolves the app folder by looking beside the exe and then one level up, so it works
whether the exe sits in the app folder or in `dist/`.

Embedding everything (models ~100 MB + web assets ~32 MB) would produce a several-hundred-MB exe
that unpacks itself on every launch, so the launcher split is deliberate.

## Verify a build

```powershell
py -3.12 VCM_OneShot_App.py --selftest   # opens the window, closes it after 5 s (works anywhere)
.\VCM_OneShot.exe --selftest             # same, but blocked where Smart App Control is on
```

A good build shows `[app] starting server`, `[app] server ready`, `SELFTEST=WINDOW_OK`, then
`[app] stopping the server this app started`. With `--windowed` there is no console; use the
console build to see those lines:

```powershell
py -3.12 -m PyInstaller --noconfirm --clean --onefile --console --name VCM_OneShot_dbg VCM_OneShot_App.py
.\dist\VCM_OneShot_dbg.exe --selftest
```

## Verified launchers (checked 2026-10-25)

Every row below was launched for real and watched in the process table and the window list; the
window was then closed by posting `WM_CLOSE` to it, which is identical to clicking the X.

| Launcher | Window | While open | After close |
| --- | --- | --- | --- |
| Desktop shortcut "VCM One-Shot" (`pythonw.exe` + `VCM_OneShot_App.py`) | `VCM One-Shot - wake gates a single 5 s Gate 2 capture`, ready in ~6 s | app 1, server 1 | app 0, server 0, no pidfile |
| `Start_VCM_OneShot.bat` | same title, ready in ~6 s | app 2, server 1 | app 0, server 0, `OK: no pipeline processes remain.` |
| `VCM_OneShot.exe` | blocked by Windows before launch on this PC | - | - |

The app writes `_oneshot_app.log` beside itself (mode, server start/stop, failures), which is the
only way to see what a windowed launch did. `_verify_app_window.ps1` re-runs the shortcut check:

```powershell
powershell -ExecutionPolicy Bypass -File .\_verify_app_window.ps1 "<app folder>"
```

## Clean exit

Closing the window stops the server **this app started**. If it reused a server that was already
running, use `Stop_VCM_OneShot.bat` (or the launcher, which sweeps every pipeline process on exit).
