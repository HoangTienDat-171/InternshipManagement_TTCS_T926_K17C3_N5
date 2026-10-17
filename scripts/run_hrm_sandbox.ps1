$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDir = Join-Path $repoRoot 'backend'
$pythonPath = Join-Path $backendDir '.venv\Scripts\python.exe'
$envPath = Join-Path $backendDir '.env'
$stateDir = Join-Path $env:LOCALAPPDATA 'IMS-HRM-SANDBOX'
$statePath = Join-Path $stateDir 'standalone-process.json'
$outPath = Join-Path $stateDir 'sandbox.stdout.log'
$errPath = Join-Path $stateDir 'sandbox.stderr.log'
$marker = 'app.hrm_sandbox'

if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Backend virtualenv is missing. Install backend requirements first.' }
if (-not (Test-Path -LiteralPath $envPath)) { throw 'backend\.env is missing. Configure the local HRM Sandbox first.' }
$keyLines = @([IO.File]::ReadAllLines($envPath) | Where-Object { $_ -match '^\s*HRM_SANDBOX_API_KEY\s*=' })
if ($keyLines.Count -ne 1) { throw 'backend\.env must contain exactly one HRM_SANDBOX_API_KEY entry.' }
$configuredKey = ($keyLines[0] -split '=', 2)[1].Trim().Trim('"').Trim("'")
if ($configuredKey.Length -lt 32 -or $configuredKey -match '[^\x21-\x7E]') {
  Remove-Variable configuredKey -ErrorAction SilentlyContinue
  throw 'HRM_SANDBOX_API_KEY must be at least 32 printable ASCII characters.'
}
$adminKeyLines = @([IO.File]::ReadAllLines($envPath) | Where-Object { $_ -match '^\s*HRM_SANDBOX_ADMIN_API_KEY\s*=' })
if ($adminKeyLines.Count -ne 1) { Remove-Variable configuredKey -ErrorAction SilentlyContinue; throw 'backend\.env must contain exactly one HRM_SANDBOX_ADMIN_API_KEY entry.' }
$configuredAdminKey = ($adminKeyLines[0] -split '=', 2)[1].Trim().Trim('"').Trim("'")
if ($configuredAdminKey.Length -lt 32 -or $configuredAdminKey -match '[^\x21-\x7E]' -or [string]::Equals($configuredAdminKey, $configuredKey, [StringComparison]::Ordinal)) {
  Remove-Variable configuredKey, configuredAdminKey -ErrorAction SilentlyContinue
  throw 'HRM_SANDBOX_ADMIN_API_KEY must be a separate key of at least 32 printable ASCII characters.'
}
$portLine = @([IO.File]::ReadAllLines($envPath) | Where-Object { $_ -match '^\s*HRM_SANDBOX_PORT\s*=' })
$configuredPort = if ($portLine.Count -eq 1) { ($portLine[0] -split '=', 2)[1].Trim().Trim('"').Trim("'") } else { '8100' }
if ($configuredPort -ne '8100') { Remove-Variable configuredKey -ErrorAction SilentlyContinue; throw 'Standalone Sandbox start script is reserved for port 8100.' }
$env:HRM_SANDBOX_API_KEY = $configuredKey
$env:HRM_SANDBOX_ADMIN_API_KEY = $configuredAdminKey
$dbLine = @([IO.File]::ReadAllLines($envPath) | Where-Object { $_ -match '^\s*HRM_SANDBOX_DATABASE_PATH\s*=' })
if ($dbLine.Count -eq 1) { $env:HRM_SANDBOX_DATABASE_PATH = ($dbLine[0] -split '=', 2)[1].Trim().Trim('"').Trim("'") }
else { Remove-Item Env:HRM_SANDBOX_DATABASE_PATH -ErrorAction SilentlyContinue }
Remove-Variable portLine, configuredPort, dbLine -ErrorAction SilentlyContinue
Remove-Variable configuredKey, configuredAdminKey, adminKeyLines -ErrorAction SilentlyContinue

if (Test-Path -LiteralPath $statePath) {
  $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
  $worker = Get-CimInstance Win32_Process -Filter "ProcessId = $($state.process.id)" -ErrorAction SilentlyContinue
  $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($state.process.parent_id)" -ErrorAction SilentlyContinue
  $recordMatches = $worker -and $parent -and
    [string]::Equals($worker.ExecutablePath, $state.process.executable, [StringComparison]::OrdinalIgnoreCase) -and
    $worker.CommandLine -like "*$marker*" -and $worker.ParentProcessId -eq [int]$state.process.parent_id -and
    [string]::Equals($parent.ExecutablePath, $pythonPath, [StringComparison]::OrdinalIgnoreCase) -and
    $parent.CommandLine -like "*$marker*"
  if ($recordMatches) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort 8100 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener -and $listener.OwningProcess -eq $worker.ProcessId) {
      Write-Output 'HRM Sandbox is already running at http://127.0.0.1:8100.'
      return
    }
    throw 'A recorded Sandbox process exists but does not own port 8100. No process was stopped.'
  }
  if ($worker -or $parent) { throw 'A recorded Sandbox process tree no longer matches its process identity. No process was stopped.' }
  Remove-Item -LiteralPath $statePath -Force
}

$existing = Get-NetTCPConnection -State Listen -LocalPort 8100 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) { throw "Port 8100 is already owned by PID $($existing.OwningProcess). No process was stopped." }

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$launcher = Start-Process -FilePath $pythonPath -ArgumentList @('-m', $marker) -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $outPath -RedirectStandardError $errPath
Remove-Item Env:HRM_SANDBOX_ADMIN_API_KEY -ErrorAction SilentlyContinue
$deadline = (Get-Date).AddSeconds(20)
$listener = $null
while ((Get-Date) -lt $deadline) {
  $listener = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort 8100 -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($listener) { break }
  if (-not (Get-Process -Id $launcher.Id -ErrorAction SilentlyContinue)) { throw 'Sandbox exited during startup. See the local Sandbox log.' }
  Start-Sleep -Milliseconds 300
}
$worker = if ($listener) { Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue }
$parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($launcher.Id)" -ErrorAction SilentlyContinue
if (-not $listener -or -not $worker -or -not $parent -or $worker.ParentProcessId -ne $launcher.Id -or
    $worker.CommandLine -notlike "*$marker*" -or $parent.CommandLine -notlike "*$marker*" -or
    -not [string]::Equals($parent.ExecutablePath, $pythonPath, [StringComparison]::OrdinalIgnoreCase)) {
  if ($listener -and $worker -and $worker.ParentProcessId -eq $launcher.Id -and $worker.CommandLine -like "*$marker*") {
    Stop-Process -Id ([int]$worker.ProcessId) -ErrorAction SilentlyContinue
  }
  $startedLauncher = Get-CimInstance Win32_Process -Filter "ProcessId = $($launcher.Id)" -ErrorAction SilentlyContinue
  if ($startedLauncher -and [string]::Equals($startedLauncher.ExecutablePath, $pythonPath, [StringComparison]::OrdinalIgnoreCase) -and $startedLauncher.CommandLine -like "*$marker*") {
    Stop-Process -Id ([int]$startedLauncher.ProcessId) -ErrorAction SilentlyContinue
  }
  throw 'Could not verify Sandbox ownership of 127.0.0.1:8100. No unrelated process was stopped.'
}
$state = @{
  repo_root = $repoRoot
  started_at = (Get-Date).ToUniversalTime().ToString('o')
  database_path = 'configured in backend/.env'
  logs = @{ stdout = $outPath; stderr = $errPath }
  process = @{
    id = $worker.ProcessId
    executable = $worker.ExecutablePath
    marker = $marker
    parent_id = $launcher.Id
    parent_executable = $parent.ExecutablePath
  }
}
$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
Write-Output 'HRM Sandbox ready at http://127.0.0.1:8100.'
Write-Output 'Health check: http://127.0.0.1:8100/api/v1/health (requires the configured API key).'
Write-Output 'Use scripts\stop_hrm_sandbox.ps1 or stop_hrm_sandbox.bat to stop this verified process.'
