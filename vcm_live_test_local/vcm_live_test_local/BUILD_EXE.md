# Building VCM_OneShot.exe

The desktop app is packaged with **PyInstaller** (installed as 6.22.3):

```powershell
py -3.12 -m pip install pyinstaller          # once
cd "C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2b/vcm_live_test_local/vcm_live_test_local"
py -3.12 -m PyInstaller --noconfirm --clean --onefile --windowed --name VCM_OneShot --icon vcm_pipeline.ico VCM_OneShot_App.py
copy dist\VCM_OneShot.exe .
```

Result: **VCM_OneShot.exe, ~16.9 MB**, beside `gate1_server.py`.

## What the exe is

A **launcher**, not a sealed bundle. The exe contains the app window (pywebview) and its Python
dependencies; the pipeline itself stays external and is used from this folder:

| Required beside the exe | Why |
|---|---|
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
.\VCM_OneShot.exe --selftest     # opens the window, closes it after 5 s
```

A good build shows `[app] starting server`, `[app] server ready`, `SELFTEST=WINDOW_OK`, then
`[app] stopping the server this app started`. With `--windowed` there is no console; use the
console build to see those lines:

```powershell
py -3.12 -m PyInstaller --noconfirm --clean --onefile --console --name VCM_OneShot_dbg VCM_OneShot_App.py
.\dist\VCM_OneShot_dbg.exe --selftest
```

## Clean exit

Closing the window stops the server **this app started**. If it reused a server that was already
running, use `Stop_VCM_OneShot.bat` (or the launcher, which sweeps every pipeline process on exit).
