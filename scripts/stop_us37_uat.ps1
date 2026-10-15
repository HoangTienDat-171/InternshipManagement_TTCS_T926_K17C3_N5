$ErrorActionPreference = 'Stop'
$stateDir = Join-Path $env:LOCALAPPDATA 'IMS-US37-UAT'
$statePath = Join-Path $stateDir 'processes.json'
if (-not (Test-Path -LiteralPath $statePath)) {
  Write-Output 'No US37 UAT process record found; nothing was stopped.'
  return
}

$state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
$stopped = @()
$skipped = @()
foreach ($service in $state.processes) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($service.id)" -ErrorAction SilentlyContinue
  $parent = if ($service.parent_id) { Get-CimInstance Win32_Process -Filter "ProcessId = $($service.parent_id)" -ErrorAction SilentlyContinue } else { $null }
  $executableMatches = $process -and [string]::Equals($process.ExecutablePath, $service.executable, [StringComparison]::OrdinalIgnoreCase)
  $commandMatches = $process -and $process.CommandLine -like "*$($service.marker)*"
  $parentMatches = -not $service.parent_id -or (
    $process -and $process.ParentProcessId -eq [int]$service.parent_id -and
    $parent -and [string]::Equals($parent.ExecutablePath, $service.parent_executable, [StringComparison]::OrdinalIgnoreCase) -and
    $parent.CommandLine -like "*$($service.parent_marker)*"
  )
  if ($process -and $executableMatches -and $commandMatches -and $parentMatches) {
    if (-not $service.parent_id) {
      $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($service.id)" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$($service.marker)*" }
      foreach ($child in $children) { Stop-Process -Id ([int]$child.ProcessId) -ErrorAction Stop }
    }
    Stop-Process -Id ([int]$service.id) -ErrorAction Stop
    $stopped += $service.name
    if ($parent) {
      Start-Sleep -Milliseconds 300
      $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($service.parent_id)" -ErrorAction SilentlyContinue
      if ($parent -and [string]::Equals($parent.ExecutablePath, $service.parent_executable, [StringComparison]::OrdinalIgnoreCase) -and $parent.CommandLine -like "*$($service.parent_marker)*") {
        Stop-Process -Id ([int]$service.parent_id) -ErrorAction Stop
      }
    }
  } elseif (-not $process -and $parent -and $service.parent_id -and
      [string]::Equals($parent.ExecutablePath, $service.parent_executable, [StringComparison]::OrdinalIgnoreCase) -and
      $parent.CommandLine -like "*$($service.parent_marker)*") {
    Stop-Process -Id ([int]$service.parent_id) -ErrorAction Stop
    $stopped += $service.name
  } elseif ($process) {
    $skipped += $service.name
  }
}
if (-not $skipped.Count) { Remove-Item -LiteralPath $statePath -Force }
Write-Output ("Stopped UAT services: " + ($(if ($stopped.Count) { $stopped -join ', ' } else { 'none' })))
if ($skipped.Count) { Write-Output ("Left processes untouched because identity did not match: " + ($skipped -join ', ')) }
Write-Output ("Persistent isolated databases and logs remain at " + $state.database_directory)
