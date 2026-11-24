# MoneyThistle setup for Windows. Run by MoneyThistle-Setup.exe (made by tools/build_windows.py)
# after the person says yes. Installs for this person only, so no administrator rights are
# needed: the program goes to %LOCALAPPDATA%\Programs\MoneyThistle, the money data stays in
# %APPDATA%\MoneyThistle (never touched by installing, updating or uninstalling).
# Running a newer setup over an installed copy updates it: the running copy is asked to stop
# (it saves and backs up first), the program files are replaced, and it starts again.
param(
  [string]$Target = (Join-Path $env:LOCALAPPDATA 'Programs\MoneyThistle'),
  [switch]$NoLaunch,      # (tests) don't start it afterwards
  [switch]$NoShortcuts,   # (tests) no Start menu entry or uninstall entry
  [switch]$Quiet          # no message boxes
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$info = Get-Content -Raw -LiteralPath (Join-Path $here 'setup-info.json') | ConvertFrom-Json

function Say($text, $icon = 'Information') {
  if (-not $Quiet) { [void][System.Windows.Forms.MessageBox]::Show($text, 'MoneyThistle', 'OK', $icon) }
}

try {
  $runtime = Join-Path $Target 'runtime'
  $appDir = Join-Path $Target 'app'
  # An installed copy that's running: ask it to stop first (it backs up), so files can be replaced.
  $wasRunning = $false
  if (Test-Path (Join-Path $runtime 'python.exe')) {
    try { $wasRunning = (Invoke-WebRequest 'http://127.0.0.1:8080/healthz' -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { }
    & (Join-Path $runtime 'python.exe') (Join-Path $appDir 'main.py') --stop | Out-Null
    Start-Sleep -Milliseconds 800
  }
  foreach ($old in @($runtime, $appDir)) {
    if (Test-Path $old) { Remove-Item -LiteralPath $old -Recurse -Force }
  }
  New-Item -ItemType Directory -Force -Path $Target | Out-Null
  Expand-Archive -LiteralPath (Join-Path $here 'payload.zip') -DestinationPath $Target -Force

  $pyw = Join-Path $runtime 'pythonw.exe'
  $main = Join-Path $appDir 'main.py'
  $icon = Join-Path $Target 'moneythistle.ico'
  if (-not $NoShortcuts) {
    # Start menu (MoneyThistle keeps these current itself from now on).
    $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'MoneyThistle'
    New-Item -ItemType Directory -Force -Path $menu | Out-Null
    $sh = New-Object -ComObject WScript.Shell
    foreach ($s in @(@('MoneyThistle.lnk', "`"$main`"", 'Open MoneyThistle (starts it if needed)'),
                     @('Stop MoneyThistle.lnk', "`"$main`" --stop", 'Stop MoneyThistle (it saves and backs up first)'))) {
      $l = $sh.CreateShortcut((Join-Path $menu $s[0]))
      $l.TargetPath = $pyw; $l.Arguments = $s[1]; $l.WorkingDirectory = $appDir
      $l.Description = $s[2]; $l.IconLocation = $icon; $l.Save()
    }
    # "Installed apps" in Windows Settings, with its uninstaller.
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MoneyThistle'
    New-Item -Path $key -Force | Out-Null
    $size = [int]((Get-ChildItem -LiteralPath $Target -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
    $un = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $Target 'uninstall.ps1')`""
    $vals = @{ DisplayName = 'MoneyThistle'; DisplayVersion = $info.version; Publisher = 'MoneyThistle';
               DisplayIcon = $icon; InstallLocation = $Target; UninstallString = $un; QuietUninstallString = "$un -Quiet";
               Comments = 'A Slightly Better Money App' }
    foreach ($k in $vals.Keys) { New-ItemProperty -Path $key -Name $k -Value $vals[$k] -PropertyType String -Force | Out-Null }
    foreach ($k in @('NoModify', 'NoRepair')) { New-ItemProperty -Path $key -Name $k -Value 1 -PropertyType DWord -Force | Out-Null }
    New-ItemProperty -Path $key -Name 'EstimatedSize' -Value $size -PropertyType DWord -Force | Out-Null
  }
  if (-not $NoLaunch) {
    # Start it; it opens in the browser by itself (the first time: Set up MoneyThistle).
    Start-Process -FilePath $pyw -ArgumentList "`"$main`"" -WorkingDirectory $appDir
    $ok = $false
    for ($i = 0; $i -lt 40 -and -not $ok; $i++) {
      Start-Sleep -Milliseconds 500
      try { $ok = (Invoke-WebRequest 'http://127.0.0.1:8080/healthz' -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { }
    }
    if (-not $ok) {
      Say ("MoneyThistle was installed, but it didn't start. Another program may be using its address (port 8080).`n`n" +
           "Its log says more: $env:APPDATA\MoneyThistle\moneythistle.log") 'Warning'
      exit 1
    }
    if (-not $wasRunning) {
      Say "MoneyThistle is installed and opening in your browser.`n`nNext time, open it from the Start menu: MoneyThistle."
    }
  }
} catch {
  Say "MoneyThistle couldn't be installed:`n`n$($_.Exception.Message)" 'Error'
  exit 1
}
