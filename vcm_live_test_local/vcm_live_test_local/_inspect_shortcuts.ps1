$sh = New-Object -ComObject WScript.Shell
foreach ($p in @('C:/Users/Leandro/Desktop/Leandro/Desktop')) {
  Get-ChildItem $p -Filter '*.lnk' -ErrorAction SilentlyContinue | ForEach-Object {
    $l = $sh.CreateShortcut($_.FullName)
    Write-Output ($_.Name + ' ||| ' + $l.TargetPath + ' ||| args=' + $l.Arguments + ' ||| wd=' + $l.WorkingDirectory)
  }
}
Write-Output '=== PORTS ==='
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -ge 8700 -and $_.LocalPort -le 8790 } | ForEach-Object {
  $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
  Write-Output ('port ' + $_.LocalPort + ' pid ' + $_.OwningProcess + ' ' + $proc.ProcessName)
}