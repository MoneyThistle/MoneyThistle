# MoneyThistle uninstaller (Windows Settings, Installed apps: MoneyThistle, Uninstall).
# Removes the program, its shortcuts and start-ups. Your money data in %APPDATA%\MoneyThistle
# (and your backups) stay, unless you choose to delete the data too.
param([switch]$Quiet)
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Windows.Forms
$Target = Split-Path -Parent $MyInvocation.MyCommand.Path
$data = Join-Path $env:APPDATA 'MoneyThistle'

if (-not $Quiet) {
  $a = [System.Windows.Forms.MessageBox]::Show("Remove MoneyThistle from this computer?`n`nYour money data and backups are kept.",
                                               'MoneyThistle', 'YesNo', 'Question')
  if ($a -ne 'Yes') { exit 0 }
}
# Stop it (it saves and makes its backup first).
$py = Join-Path $Target 'runtime\python.exe'
if (Test-Path $py) { & $py (Join-Path $Target 'app\main.py') --stop | Out-Null }

# Shortcuts and start-ups.
$paths = @((Join-Path ([Environment]::GetFolderPath('Programs')) 'MoneyThistle'),
           (Join-Path ([Environment]::GetFolderPath('Desktop')) 'MoneyThistle.lnk'),
           (Join-Path ([Environment]::GetFolderPath('Startup')) 'MoneyThistle.lnk'))
foreach ($p in $paths) { if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force } }
# Started with the computer: that task was set up as administrator, so removing it asks too.
if (Get-ScheduledTask -TaskName 'MoneyThistle' -ErrorAction SilentlyContinue) {
  try { Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList '-NoProfile -Command "Unregister-ScheduledTask -TaskName MoneyThistle -Confirm:$false"' } catch { }
}
Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MoneyThistle' -Recurse -Force -ErrorAction SilentlyContinue

if (-not $Quiet -and (Test-Path -LiteralPath $data)) {
  $a = [System.Windows.Forms.MessageBox]::Show("MoneyThistle is removed.`n`nAlso delete your money data on this computer?`n$data`n`n" +
                                               "Choose No to keep it (installing MoneyThistle again picks it up). Backups on Nextcloud are never touched.",
                                               'MoneyThistle', 'YesNo', 'Warning', 'Button2')
  if ($a -eq 'Yes') { Remove-Item -LiteralPath $data -Recurse -Force }
}
# The program folder holds this script: remove it a moment after this window closes.
Start-Process cmd.exe -WindowStyle Hidden -ArgumentList "/c timeout /t 3 /nobreak >nul & rmdir /s /q `"$Target`""
