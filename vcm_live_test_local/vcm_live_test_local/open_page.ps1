<#
.SYNOPSIS
  Open one of the local VCM dashboard pages, starting the server if it is down.

.DESCRIPTION
  The dashboard pages only exist while gate1_server.py is listening on 8765.
  This launcher is what the desktop shortcuts call: it starts the server hidden
  when nothing is listening, waits for the port, then opens the requested page
  in the default browser. Running it while the server is already up just opens
  another browser tab.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File open_page.ps1 -Page dataset_recorder.html
#>
param([string]$Page = "pipeline_all_in_one.html")

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port = 8765
$Url = "http://127.0.0.1:$Port/$Page"

function Test-Server {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

if (-not (Test-Server)) {
    $python = Get-Command py -ErrorAction SilentlyContinue
    if (-not $python) {
        $python = Get-Command python -ErrorAction SilentlyContinue
    }
    if (-not $python) {
        Write-Error "Neither 'py' nor 'python' is on PATH; cannot start gate1_server.py."
        exit 2
    }
    Start-Process -FilePath $python.Source -ArgumentList "-3.12", "gate1_server.py" -WorkingDirectory $AppDir -WindowStyle Hidden
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Server) { break }
    }
    if (-not (Test-Server)) {
        Write-Error "gate1_server.py did not start listening on $Port within 30 s. Check $AppDir for errors."
        exit 3
    }
}

try {
    Add-Content -Path (Join-Path $AppDir '_desktop_launch.log') -Value ((Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + '  page=' + $Page) -ErrorAction Stop
} catch { }

Start-Process $Url
exit 0
