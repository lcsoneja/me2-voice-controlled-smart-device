<#
Open the VCM One-Shot app, make sure a window is actually VISIBLE, and report what came up.

pywebview intermittently leaves its WinForms window created-but-hidden, so "is a process running"
is not the same as "the user can see the app". This script shows/restores the window either way:

    powershell -ExecutionPolicy Bypass -File .\_open_app.ps1

Exits non-zero when the shortcut is missing, the page never answers, or no window exists.
#>
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'VCM One-Shot.lnk'
if (-not (Test-Path $lnk)) { 'MISSING_SHORTCUT ' + $lnk; exit 1 }

Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class AppWin {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc lp, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  public static IntPtr FindForPid(uint want, string hint) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => {
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (pid != want) return true;
      var sb = new StringBuilder(512); GetWindowText(h, sb, 512);
      if (sb.ToString().IndexOf(hint, StringComparison.OrdinalIgnoreCase) >= 0) { found = h; }
      return true;
    }, IntPtr.Zero);
    return found;
  }
  public static string Describe(IntPtr h) {
    RECT r; GetWindowRect(h, out r);
    return r.Left + "," + r.Top + " " + (r.Right - r.Left) + "x" + (r.Bottom - r.Top)
           + " visible=" + IsWindowVisible(h);
  }
}
"@

function Get-AppProcess {
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*VCM_OneShot_App*' } |
    Select-Object -First 1
}

$app = Get-AppProcess
$handle = [IntPtr]::Zero
if ($app) { $handle = [AppWin]::FindForPid([uint32]$app.ProcessId, 'One-Shot') }

if ($handle -ne [IntPtr]::Zero) {
  # The window exists: restore + show it even when the toolkit left it hidden.
  [AppWin]::ShowWindow($handle, 9) | Out-Null   # SW_RESTORE
  [AppWin]::ShowWindow($handle, 5) | Out-Null   # SW_SHOW
  [AppWin]::SetForegroundWindow($handle) | Out-Null
  'action=shown window=' + [AppWin]::Describe($handle)
} else {
  Start-Process -FilePath $lnk
  'action=launched'
}

$code = '000'
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Milliseconds 1000
  $code = & curl.exe -s -o NUL -w '%{http_code}' --max-time 3 http://127.0.0.1:8765/oneshot.html
  if ($code -eq '200') { break }
}
'http=' + $code

$handle = [IntPtr]::Zero
$app = Get-AppProcess
for ($i = 0; $i -lt 60; $i++) {
  $app = Get-AppProcess
  if ($app) { $handle = [AppWin]::FindForPid([uint32]$app.ProcessId, 'One-Shot') }
  if ($handle -ne [IntPtr]::Zero) { break }
  Start-Sleep -Seconds 1
}
if ($handle -eq [IntPtr]::Zero) { 'WINDOW=missing'; exit 1 }
[AppWin]::ShowWindow($handle, 9) | Out-Null
[AppWin]::ShowWindow($handle, 5) | Out-Null
[AppWin]::SetForegroundWindow($handle) | Out-Null
'window=' + [AppWin]::Describe($handle)
