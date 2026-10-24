@echo off
setlocal
echo Stopping the unified VCM monitor (port 8765)...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if ($c) { Stop-Process -Id $c[0].OwningProcess -Force; 'Server stopped.' } else { 'Server was not running.' }"
timeout /t 2 /nobreak >nul
