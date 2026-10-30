$ErrorActionPreference = 'Continue'
$app = 'C:/Users/Leandro/Desktop/Leandro/AI 222 and AI 231/Exercise 2/Exercise 2b/vcm_live_test_local/vcm_live_test_local'
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'VCM One-Shot.lnk'
$log = Join-Path $app '_oneshot_app.log'
$py = 'C:/Users/Leandro/AppData/Local/Programs/Python/Python312/python.exe'

'== watch start ' + (Get-Date -Format 'HH:mm:ss') + ' =='
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" | Where-Object { $_.CommandLine -match 'VCM_OneShot|gate1_server' } | ForEach-Object { 'kill leftover ' + $_.ProcessId; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$pidFile = Join-Path $app '_oneshot_server.pid'
if (Test-Path $pidFile) { Remove-Item $pidFile -Force; 'pid file removed' }
Start-Sleep -Milliseconds 800

$before = 0
if (Test-Path $log) { $before = @(Get-Content $log).Count }
'log_lines_before=' + $before
'launching via shortcut'
Start-Process -FilePath $lnk

$ok = $false
$last = 0
for ($i = 1; $i -le 50; $i++) {
  Start-Sleep -Seconds 3
  $last = 3 * $i
  $proc = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match 'VCM_OneShot' })
  $code = & curl.exe -s -o NUL -w '%{http_code}' --max-time 3 http://127.0.0.1:8765/oneshot.html
  $win = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*VCM*' })
  if (($i % 4) -eq 0 -or $i -le 2) { 't=' + $last + 's proc=' + $proc.Count + ' http=' + $code + ' win=' + $win.Count }
  if ($code -eq '200' -and $win.Count -ge 1) { $ok = $true; break }
}

if ($ok) { 'VERDICT=UP t=' + $last + 's' } else { 'VERDICT=NOT_UP t=' + $last + 's' }

$win = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*VCM*' })
$win | ForEach-Object { 'win[' + $_.ProcessName + '] ' + $_.Id + ' :: ' + $_.MainWindowTitle }
$proc = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match 'VCM_OneShot' })
'procs=' + $proc.Count

Start-Sleep -Seconds 20
$code2 = & curl.exe -s -o NUL -w '%{http_code}' --max-time 4 http://127.0.0.1:8765/oneshot.html
$win2 = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*VCM*' })
'stability http=' + $code2 + ' win=' + $win2.Count

if ($code2 -eq '200') {
  $lb = & curl.exe -s --max-time 6 http://127.0.0.1:8765/api/oneshot/leaderboard
  try { $j = $lb | ConvertFrom-Json; 'board_models=' + $j.models + ' top=' + $j.ranking[0].model + ' ' + [math]::Round(100 * $j.ranking[0].acc, 1) + '%' } catch { 'board_parse_failed' }
}

if (-not $ok) {
  '== escalating: console launch to capture the error =='
  Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" | Where-Object { $_.CommandLine -match 'VCM_OneShot|gate1_server' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Milliseconds 600
  $out = Join-Path $app '_app_console.log'
  $err = Join-Path $app '_app_console_err.log'
  $before2 = 0
  if (Test-Path $out) { $before2 = @(Get-Content $out).Count }
  Start-Process -FilePath $py -ArgumentList ('"' + (Join-Path $app 'VCM_OneShot_App.py') + '"') -WorkingDirectory $app -RedirectStandardOutput $out -RedirectStandardError $err
  for ($j = 1; $j -le 20; $j++) {
    Start-Sleep -Seconds 3
    $code3 = & curl.exe -s -o NUL -w '%{http_code}' --max-time 3 http://127.0.0.1:8765/oneshot.html
    $win3 = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*VCM*' })
    if (($j % 4) -eq 0) { 'console t=' + (3*$j) + 's http=' + $code3 + ' win=' + $win3.Count }
    if ($code3 -eq '200' -and $win3.Count -ge 1) { 'CONSOLE_UP t=' + (3*$j) + 's'; break }
  }
  '--- console out ---'
  if (Test-Path $out) { Get-Content $out | Select-Object -Skip $before2 | Select-Object -First 40 | ForEach-Object { $_ } }
  '--- console err ---'
  if (Test-Path $err) { Get-Content $err | Select-Object -Last 30 | ForEach-Object { 'ERR ' + $_ } }
}

'--- new app log lines ---'
if (Test-Path $log) { Get-Content $log | Select-Object -Skip $before | ForEach-Object { $_ } }
'== watch done ' + (Get-Date -Format 'HH:mm:ss') + ' =='