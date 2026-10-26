@echo off
title VCM Dashboard Launcher
cd /d "%~dp0"

rem --- Is the server already up? ---
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/pipeline_all_in_one.html -TimeoutSec 2) | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel%==0 goto :open

rem --- Start server hidden, wait for it to answer ---
start "VCM Gate1 Server" /min cmd /c "python gate1_server.py"
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 20;$i++){ Start-Sleep -Milliseconds 500; try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/pipeline_all_in_one.html -TimeoutSec 2) | Out-Null; $ok=$true; break } catch {} }; if($ok){exit 0}else{exit 1}"
if not %errorlevel%==0 (
  echo Server failed to start. Check that Python is installed and port 8765 is free.
  pause
  exit /b 1
)

:open
start "" http://127.0.0.1:8765/pipeline_all_in_one.html
exit /b 0
