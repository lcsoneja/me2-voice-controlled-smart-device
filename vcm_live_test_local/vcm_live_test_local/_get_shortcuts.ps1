$sh = New-Object -ComObject WScript.Shell
Get-ChildItem -Path 'C:/Users/Leandro/Desktop' -Filter '*.lnk' | Where-Object { $_.Name -like '*VCM*' } | ForEach-Object {
  $l = $sh.CreateShortcut($_.FullName)
  Write-Output ("[" + $_.Name + "]")
  Write-Output ("  Target: " + $l.TargetPath)
  Write-Output ("  Args:   " + $l.Arguments)
  Write-Output ("  WorkDir:" + $l.WorkingDirectory)
  Write-Output ("  Icon:   " + $l.IconLocation)
}