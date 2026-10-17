$ErrorActionPreference = 'Stop'
$stateDir = Join-Path $env:LOCALAPPDATA 'IMS-HRM-SANDBOX'
$statePath = Join-Path $stateDir 'standalone-process.json'
if (-not (Test-Path -LiteralPath $statePath)) {
  Write-Output 'No managed standalone HRM Sandbox process was recorded; nothing was stopped.'
  return
}

$state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
$record = $state.process
$marker = [string]$record.marker
$worker = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.id)" -ErrorAction SilentlyContinue
$parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.parent_id)" -ErrorAction SilentlyContinue
$listener = Get-NetTCPConnection -State Listen -LocalPort 8100 -ErrorAction SilentlyContinue | Select-Object -First 1
$verified = $worker -and $parent -and $listener -and $listener.OwningProcess -eq [int]$record.id -and
  $worker.ParentProcessId -eq [int]$record.parent_id -and
  [string]::Equals($worker.ExecutablePath, $record.executable, [StringComparison]::OrdinalIgnoreCase) -and
  [string]::Equals($parent.ExecutablePath, $record.parent_executable, [StringComparison]::OrdinalIgnoreCase) -and
  $worker.CommandLine -like "*$marker*" -and $parent.CommandLine -like "*$marker*"
if (-not $verified) { throw 'Sandbox process identity or port ownership changed. No process was stopped; inspect the recorded PID before retrying.' }

Stop-Process -Id ([int]$worker.ProcessId) -ErrorAction Stop
Start-Sleep -Milliseconds 300
$parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.parent_id)" -ErrorAction SilentlyContinue
if ($parent -and [string]::Equals($parent.ExecutablePath, $record.parent_executable, [StringComparison]::OrdinalIgnoreCase) -and $parent.CommandLine -like "*$marker*") {
  Stop-Process -Id ([int]$parent.ProcessId) -ErrorAction Stop
}
Remove-Item -LiteralPath $statePath -Force
Write-Output 'Stopped the verified standalone HRM Sandbox. Its SQLite database and logs were preserved.'
