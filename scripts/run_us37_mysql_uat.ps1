$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$pythonPath = Join-Path $backendDir '.venv\Scripts\python.exe'
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$vitePath = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
$localStateDir = Join-Path $env:LOCALAPPDATA 'IMS-US37-UAT'
$mysqlConfigPath = Join-Path $localStateDir 'mysql-uat.env'
$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$runDir = Join-Path $localStateDir "mysql-$runId"
$statePath = Join-Path $localStateDir "mysql-processes-$runId.json"
$backendEnvPath = Join-Path $backendDir '.env'

function Read-SimpleEnv([string]$Path) {
  $result = @{}
  foreach ($line in [IO.File]::ReadAllLines($Path)) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#') -or $trimmed -notmatch '=') { continue }
    $parts = $trimmed -split '=', 2
    $result[$parts[0].Trim()] = $parts[1].Trim().Trim('"').Trim("'")
  }
  return $result
}

function Get-ListeningPid([int]$Port) {
  foreach ($line in (& netstat -ano -p tcp)) {
    if ($line -match '^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$' -and [int]$Matches[1] -eq $Port) {
      return [int]$Matches[2]
    }
  }
  return $null
}

function Stop-StartedServices($Services) {
  $items = @($Services)
  for ($index = $items.Count - 1; $index -ge 0; $index--) {
    $service = $items[$index]
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($service.id)" -ErrorAction SilentlyContinue
    if ($process -and [string]::Equals($process.ExecutablePath, $service.executable, [StringComparison]::OrdinalIgnoreCase) -and $process.CommandLine -like "*$($service.marker)*") {
      $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($service.id)" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$($service.marker)*" }
      foreach ($child in $children) { Stop-Process -Id ([int]$child.ProcessId) -ErrorAction SilentlyContinue }
      Stop-Process -Id ([int]$process.ProcessId) -ErrorAction SilentlyContinue
    }
  }
}

if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Backend virtualenv is missing.' }
if (-not (Test-Path -LiteralPath $vitePath)) { throw 'Frontend dependencies are missing.' }
if (-not (Test-Path -LiteralPath $mysqlConfigPath)) { throw 'Local MySQL UAT credentials are missing; provision the UAT database first.' }
if (-not (Test-Path -LiteralPath $backendEnvPath)) { throw 'Local HRM Sandbox configuration is missing from this feature worktree.' }
if (Test-Path -LiteralPath $statePath) { throw 'A UAT process record already exists for this run ID; retry in a few seconds.' }

$mysql = Read-SimpleEnv $mysqlConfigPath
if ($mysql.MYSQL_DATABASE -ne 'internship_management_us37_uat' -or $mysql.MYSQL_HOST -notin @('127.0.0.1', 'localhost', '::1')) {
  throw 'Refusing to start because the local configuration does not target the isolated MySQL UAT schema.'
}
$sandboxKeyLines = @([IO.File]::ReadAllLines($backendEnvPath) | Where-Object { $_ -match '^\s*HRM_SANDBOX_API_KEY\s*=' })
if ($sandboxKeyLines.Count -ne 1) { throw 'Feature worktree backend/.env must contain exactly one HRM_SANDBOX_API_KEY entry.' }
$sandboxKey = ($sandboxKeyLines[0] -split '=', 2)[1].Trim().Trim('"').Trim("'")
if ($sandboxKey.Length -lt 32 -or $sandboxKey -match '[^\x21-\x7E]') { throw 'HRM_SANDBOX_API_KEY is missing or invalid.' }

$busy = @()
foreach ($port in @(3000, 8000, 8100)) {
  $listenerPid = Get-ListeningPid $port
  if ($listenerPid) { $busy += "$port (PID $listenerPid)" }
}
if ($busy.Count) { throw "UAT stopped before launch because ports are already in use: $($busy -join ', '). Existing processes were left untouched." }

New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$logs = @{
  sandboxOut = Join-Path $runDir 'sandbox.stdout.log'
  sandboxErr = Join-Path $runDir 'sandbox.stderr.log'
  backendOut = Join-Path $runDir 'backend.stdout.log'
  backendErr = Join-Path $runDir 'backend.stderr.log'
  frontendOut = Join-Path $runDir 'frontend.stdout.log'
  frontendErr = Join-Path $runDir 'frontend.stderr.log'
}
$environmentNames = @(
  'IMS_DATABASE_BACKEND', 'IMS_SQLITE_PATH', 'MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE',
  'HRM_PROVIDER', 'HRM_SANDBOX_BASE_URL', 'HRM_SANDBOX_API_KEY', 'HRM_SANDBOX_DATABASE_PATH', 'HRM_SANDBOX_PORT',
  'IMS_HRM_SANDBOX_OUTBOUND_ENABLED', 'IMS_DISABLE_EMAIL_WORKER', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_FROM'
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$started = @()

try {
  $env:IMS_DATABASE_BACKEND = 'mysql'
  $env:IMS_SQLITE_PATH = ''
  $env:MYSQL_HOST = $mysql.MYSQL_HOST
  $env:MYSQL_PORT = $mysql.MYSQL_PORT
  $env:MYSQL_USER = $mysql.MYSQL_USER
  $env:MYSQL_PASSWORD = $mysql.MYSQL_PASSWORD
  $env:MYSQL_DATABASE = $mysql.MYSQL_DATABASE
  $env:HRM_PROVIDER = 'sandbox'
  $env:HRM_SANDBOX_BASE_URL = 'http://127.0.0.1:8100'
  $env:HRM_SANDBOX_API_KEY = $sandboxKey
  $env:HRM_SANDBOX_DATABASE_PATH = Join-Path $localStateDir 'hrm-sandbox-mysql-uat.sqlite3'
  $env:HRM_SANDBOX_PORT = '8100'
  $env:IMS_HRM_SANDBOX_OUTBOUND_ENABLED = '1'
  $env:IMS_DISABLE_EMAIL_WORKER = '1'
  $env:SMTP_HOST = ''
  $env:SMTP_PORT = '587'
  $env:SMTP_USERNAME = ''
  $env:SMTP_PASSWORD = ''
  $env:SMTP_FROM = ''

  Push-Location -LiteralPath $repoRoot
  try {
    & $pythonPath (Join-Path $repoRoot 'scripts\migrate_us37_mysql_uat.py')
    if ($LASTEXITCODE -ne 0) { throw 'MySQL UAT schema initialization failed.' }
    Push-Location -LiteralPath $backendDir
    try {
      & $pythonPath -m app.us37_uat_seed
      if ($LASTEXITCODE -ne 0) { throw 'Synthetic US37 UAT candidate preparation failed.' }
    } finally { Pop-Location }
  } finally { Pop-Location }

  Push-Location -LiteralPath $backendDir
  try {
    $sandbox = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'app.hrm_sandbox') -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $logs.sandboxOut -RedirectStandardError $logs.sandboxErr
    $started += @{ name = 'hrm-sandbox'; id = $sandbox.Id; executable = $pythonPath; marker = 'app.hrm_sandbox'; port = 8100 }
    $backend = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--log-level', 'warning') -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $logs.backendOut -RedirectStandardError $logs.backendErr
    $started += @{ name = 'ims-backend'; id = $backend.Id; executable = $pythonPath; marker = 'uvicorn app.main:app'; port = 8000 }
  } finally { Pop-Location }
  $frontend = Start-Process -FilePath $nodePath -ArgumentList @($vitePath, '--host', '127.0.0.1', '--port', '3000', '--strictPort') -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $logs.frontendOut -RedirectStandardError $logs.frontendErr
  $started += @{ name = 'ims-frontend'; id = $frontend.Id; executable = $nodePath; marker = 'vite'; port = 3000 }

  $deadline = (Get-Date).AddSeconds(45)
  $ready = $false
  while ((Get-Date) -lt $deadline) {
    $alive = $true
    foreach ($service in $started) { if (-not (Get-Process -Id $service.id -ErrorAction SilentlyContinue)) { $alive = $false } }
    if (-not $alive) { throw 'A UAT service exited during startup. Inspect the run-specific logs in %LOCALAPPDATA%\IMS-US37-UAT.' }
    try {
      $headers = @{ Authorization = "Bearer $sandboxKey" }
      $sandboxHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8100/api/v1/health' -Headers $headers -TimeoutSec 2
      $backendHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/' -TimeoutSec 2
      $frontendHealth = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 2
      if ($sandboxHealth.status -eq 'ok' -and $backendHealth.status -eq 'Online' -and $frontendHealth.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
  }
  if (-not $ready) { throw 'UAT services did not become healthy within 45 seconds. Inspect the run-specific logs in %LOCALAPPDATA%\IMS-US37-UAT.' }

  $state = [ordered]@{
    source_root = $repoRoot
    branch = (& git -C $repoRoot branch --show-current).Trim()
    head = (& git -C $repoRoot rev-parse HEAD).Trim()
    database = 'internship_management_us37_uat'
    database_directory = $localStateDir
    log_directory = $runDir
    started_at = (Get-Date).ToString('o')
    processes = $started
  }
  $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
  Write-Output 'MySQL UAT IMS + HRM Sandbox is ready.'
  Write-Output 'Frontend: http://127.0.0.1:3000'
  Write-Output 'Backend: http://127.0.0.1:8000'
  Write-Output 'HRM Sandbox: http://127.0.0.1:8100'
  Write-Output "Process record: $statePath"
} catch {
  Stop-StartedServices $started
  throw
} finally {
  foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process') }
  Remove-Variable sandboxKey, mysql -ErrorAction SilentlyContinue
}
