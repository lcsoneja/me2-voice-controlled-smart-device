@echo off
setlocal
set "ROOT=%~dp0"
set "VCM_DIR=%ROOT%vcm_live_test_local\vcm_live_test_local"
set "PAGE=http://127.0.0.1:8765/pipeline_all_in_one.html"
netstat -ano | findstr /R /C:":8765 .*LISTENING" >nul
if not errorlevel 1 (
  start "" "%PAGE%"
  exit /b 0
)
where pyw >nul 2>nul
if errorlevel 1 goto fallback
start "" pyw -3.12 "%ROOT%vcm_monitor_app.py"
timeout /t 12 /nobreak >nul
exit /b 0
:fallback
start "VCM Monitor server" /min cmd /k "cd /d "%VCM_DIR%" && py -3.12 gate1_server.py"
timeout /t 12 /nobreak >nul
start "" "%PAGE%"
