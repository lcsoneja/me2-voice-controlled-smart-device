@echo off
setlocal
set "PI_HOST=lcsoneja@192.168.1.75"
set "LOCAL_PORT=8766"
set "DASHBOARD_URL=http://localhost:8766/pipeline_all_in_one.html"

where ssh.exe >nul 2>&1
if errorlevel 1 goto no_ssh

powershell -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort %LOCAL_PORT% -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo Starting secure SSH tunnel to the Raspberry Pi...
  start "Pi Gates dashboard tunnel" /min ssh.exe -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L %LOCAL_PORT%:127.0.0.1:8765 %PI_HOST%
)

set /a ATTEMPT=0
:wait_for_dashboard
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing 'http://localhost:%LOCAL_PORT%/pipeline_all_in_one.html' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>&1
if not errorlevel 1 goto open_dashboard
set /a ATTEMPT+=1
if %ATTEMPT% GEQ 15 goto tunnel_error
timeout /t 1 /nobreak >nul
goto wait_for_dashboard

:open_dashboard
echo Opening the Pi's all-gates single-view dashboard.
echo Allow microphone access when your browser asks.
echo Audio comes from this computer's browser microphone; inference runs on the Pi.
start "" "%DASHBOARD_URL%"
exit /b 0

:no_ssh
echo Windows OpenSSH was not found. Install the OpenSSH Client optional feature.
pause
exit /b 1

:tunnel_error
echo Could not reach the dashboard through SSH.
echo Check that the Pi is on at 192.168.1.75 and SSH key access works.
pause
exit /b 1
