$ErrorActionPreference = 'Stop'
$stateDir = Join-Path $env:LOCALAPPDATA 'IMS-US37-UAT'
$stateFiles = @(Get-ChildItem -LiteralPath $stateDir -Filter 'mysql-processes-*.json' -File -ErrorAction SilentlyContinue)
if (-not $stateFiles.Count) {
  Write-Output 'No MySQL UAT process records found; nothing was stopped.'
  return
}

foreach ($file in $stateFiles) {
  $state = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
  $skipped = @()
  $stopped = @()
  $items = @($state.processes)
  for ($index = $items.Count - 1; $index -ge 0; $index--) {
    $service = $items[$index]
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($service.id)" -ErrorAction SilentlyContinue
    if ($process -and [string]::Equals($process.ExecutablePath, $service.executable, [StringComparison]::OrdinalIgnoreCase) -and $process.CommandLine -like "*$($service.marker)*") {
      $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($service.id)" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$($service.marker)*" }
      foreach ($child in $children) { Stop-Process -Id ([int]$child.ProcessId) -ErrorAction Stop }
      Stop-Process -Id ([int]$process.ProcessId) -ErrorAction Stop
      $stopped += $service.name
    } elseif (-not $process) {
      continue
    } else {
      $skipped += $service.name
    }
  }
  if (-not $skipped.Count) {
    Remove-Item -LiteralPath $file.FullName -Force
    Write-Output ("Stopped MySQL UAT services: " + ($(if ($stopped.Count) { $stopped -join ', ' } else { 'none; processes already exited' })))
  } else {
    Write-Output ("Left processes untouched because identity did not match: " + ($skipped -join ', '))
  }
  Write-Output ("Logs and UAT data remain at " + $state.log_directory)
}
