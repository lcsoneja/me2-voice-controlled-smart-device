$app = $args[0]
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'VCM One-Shot.lnk'
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class WinEnum6 {
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc lp, IntPtr l);
  delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  public static List<string> Find(string hint) {
    var list = new List<string>();
    EnumWindows((h, l) => {
      if (IsWindowVisible(h)) {
        var sb = new StringBuilder(512);
        GetWindowText(h, sb, 512);
        if (sb.Length > 0 && sb.ToString().IndexOf(hint, StringComparison.OrdinalIgnoreCase) >= 0)
          list.Add(h.ToInt64() + "|" + sb.ToString());
      }
      return true;
    }, IntPtr.Zero);
    return list;
  }
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
}
"@
'1_RETARGET_SHORTCUT'
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = (Get-Command pythonw.exe -ErrorAction Stop).Source
$s.Arguments = '"' + (Join-Path $app 'VCM_OneShot_App.py') + '"'
$s.WorkingDirectory = $app
$s.IconLocation = (Join-Path $app 'vcm_pipeline.ico') + ',0'
$s.Description = 'VCM One-Shot dashboard - one-shot Gate 2 capture'
$s.Save()
$v = $sh.CreateShortcut($lnk)
'2_target=' + $v.TargetPath
'3_args=[' + $v.Arguments + ']'
Get-Process -Name 'VCM_OneShot' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -like '*gate1_server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Remove-Item (Join-Path $app '_oneshot_app.log') -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
'4_CLEAN servers=' + @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*gate1_server.py*' }).Count
'5_LAUNCH_SHORTCUT'
try { Start-Process -FilePath $lnk -ErrorAction Stop; 'launch_accepted' } catch { 'LAUNCH_BLOCKED: ' + $_.Exception.Message.Split([Environment]::NewLine)[0] }
$http = '000'; $win = $null
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Milliseconds 800
  if ($http -ne '200') { $http = & curl.exe -s -o NUL -w '%{http_code}' --max-time 3 http://127.0.0.1:8765/oneshot.html }
  if (-not $win) { $win = [WinEnum6]::Find('One-Shot') | Select-Object -First 1 }
  if (($http -eq '200') -and $win) { '6_READY tick=' + $i; break }
}
'7_http=' + $http
'8_WINDOW=' + $(if ($win) { $win } else { 'MISSING' })
$appProcs = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*VCM_OneShot_App.py*' }).Count
'9_app_procs=' + $appProcs
Start-Sleep -Seconds 10
'10_app_alive_while_open=' + @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*VCM_OneShot_App.py*' }).Count
'11_server_alive_while_open=' + @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*gate1_server.py*' }).Count
'12_LOG:'
Get-Content (Join-Path $app '_oneshot_app.log') -ErrorAction SilentlyContinue | Select-Object -Last 6
if ($win) {
  $h = [IntPtr]::new([int64]($win.Split('|')[0]))
  '13_SEND_WM_CLOSE'
  [WinEnum6]::PostMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
  Start-Sleep -Seconds 12
  '14_after_close_app=' + @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*VCM_OneShot_App.py*' }).Count
  '15_after_close_servers=' + @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*gate1_server.py*' }).Count
  '16_pidfile=' + (Test-Path (Join-Path $app '_oneshot_server.pid'))
  '17_LOG_AFTER:'
  Get-Content (Join-Path $app '_oneshot_app.log') -ErrorAction SilentlyContinue | Select-Object -Last 4
}