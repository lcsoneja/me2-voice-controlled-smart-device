@echo off
setlocal
title VCM One-Shot
cd /d "%~dp0"

rem Pick an interpreter: prefer the pinned launcher, fall back to python on PATH.
set "PYCMD=py -3.12"
%PYCMD% --version >nul 2>&1
if errorlevel 1 set "PYCMD=python"
%PYCMD% --version >nul 2>&1
if errorlevel 1 (
    echo Python 3 was not found. Install it, then run this file again.
    pause
    exit /b 1
)

echo ================================================================
echo   VCM One-Shot - wake word gates a single 5 s Gate 2 capture
echo ================================================================
echo   Close the app window to exit.
echo   On exit this launcher stops EVERY pipeline process, so nothing
echo   is left running in the background (including a dashboard server
echo   you may have started separately).
echo.
%PYCMD% "%~dp0VCM_OneShot_App.py" %*

echo.
echo App exited. Stopping pipeline processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -like '*gate1_server.py*' } | ForEach-Object { Write-Host ('  stopped PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
if exist "%~dp0_oneshot_server.pid" del /q "%~dp0_oneshot_server.pid" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$left = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -like '*gate1_server.py*' }).Count; if ($left -eq 0) { Write-Host 'OK: no pipeline processes remain.' } else { Write-Host ('WARNING: ' + $left + ' still running.') }"
echo.
timeout /t 3 >nul
endlocal
