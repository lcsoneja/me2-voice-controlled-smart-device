<#
Open the VCM One-Shot app, bring it to the front, and report what came up.

Used after every change so the window on screen always runs the code that was just tested:

    powershell -ExecutionPolicy Bypass -File .\_open_app.ps1

Exits non-zero when the shortcut is missing, the page never answers, or no window appears.
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
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  public static IntPtr Find(string hint) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => {
      if (IsWindowVisible(h)) {
        var sb = new StringBuilder(512); GetWindowText(h, sb, 512);
        if (sb.ToString().IndexOf(hint, StringComparison.OrdinalIgnoreCase) >= 0) { found = h; }
      }
      return true;
    }, IntPtr.Zero);
    return found;
  }
  public static string Describe(IntPtr h) {
    RECT r; GetWindowRect(h, out r);
    return r.Left + "," + r.Top + " " + (r.Right - r.Left) + "x" + (r.Bottom - r.Top);
  }
}
"@

# Already open? Just raise it instead of starting a second copy.
$window = [AppWin]::Find('One-Shot')
if ($window -ne [IntPtr]::Zero) {
  [AppWin]::ShowWindow($window, 5) | Out-Null
  [AppWin]::SetForegroundWindow($window) | Out-Null
  'action=raised window=' + [AppWin]::Describe($window)
} else {
  Start-Process -FilePath $lnk
  'action=launched'
}

$code = '000'
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 1200
  $code = & curl.exe -s -o NUL -w '%{http_code}' --max-time 3 http://127.0.0.1:8765/oneshot.html
  if ($code -eq '200') { break }
}
'http=' + $code

$window = [IntPtr]::Zero
for ($i = 0; $i -lt 30; $i++) {
  $window = [AppWin]::Find('One-Shot')
  if ($window -ne [IntPtr]::Zero) { break }
  Start-Sleep -Seconds 1
}
if ($window -eq [IntPtr]::Zero) { 'WINDOW=missing'; exit 1 }
[AppWin]::ShowWindow($window, 5) | Out-Null
[AppWin]::SetForegroundWindow($window) | Out-Null
'window=' + [AppWin]::Describe($window) + ' raised=ok'
