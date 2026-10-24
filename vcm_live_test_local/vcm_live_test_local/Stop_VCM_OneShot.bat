@echo off
setlocal
title Stop VCM One-Shot
cd /d "%~dp0"

echo Stopping every VCM pipeline process (server + app)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and ($_.CommandLine -like '*gate1_server.py*' -or $_.CommandLine -like '*VCM_OneShot_App.py*') } | ForEach-Object { Write-Host ('  stopped PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
if exist "%~dp0_oneshot_server.pid" del /q "%~dp0_oneshot_server.pid" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$left = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -like '*gate1_server.py*' }).Count; if ($left -eq 0) { Write-Host 'OK: nothing left running.' } else { Write-Host ('WARNING: ' + $left + ' still running.') }"
echo.
timeout /t 3 >nul
endlocal
