param(
  [ValidateRange(1, 65535)][int]$FrontendPort = 3000,
  [ValidateRange(1, 65535)][int]$BackendPort = 8000,
  [ValidateRange(1, 65535)][int]$SandboxPort = 8100,
  [string]$RuntimeConfigPath = (Join-Path $env:LOCALAPPDATA 'IMS-US37-CLEAN-UAT\runtime.env')
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$pythonCandidates = @(
  (Join-Path $backendDir '.venv\Scripts\python.exe'),
  (Get-Command python.exe -ErrorAction SilentlyContinue).Source
) | Where-Object { $_ } | Select-Object -Unique
$pythonPath = $null
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$vitePath = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
$stateDir = Join-Path $env:LOCALAPPDATA 'IMS-US37-CLEAN-UAT'
$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$runDir = Join-Path $stateDir "run-$runId"
$statePath = Join-Path $stateDir "processes-$runId.json"

function Read-SimpleEnv([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'Local clean UAT runtime config is missing.' }
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

if ((@($FrontendPort, $BackendPort, $SandboxPort) | Select-Object -Unique).Count -ne 3) {
  throw 'Frontend, backend, and Sandbox ports must be distinct.'
}
foreach ($candidate in $pythonCandidates) {
  if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
  & $candidate -c "import sys; sys.path.insert(0, r'$backendDir'); import app.main, app.hrm_sandbox" *> $null
  if ($LASTEXITCODE -eq 0) { $pythonPath = $candidate; break }
}
if (-not $pythonPath) { throw 'No installed Python runtime can import the US37 IMS and HRM Sandbox applications.' }
if (-not (Test-Path -LiteralPath $vitePath -PathType Leaf)) { throw 'Frontend dependencies are missing from the US37 worktree.' }

$runtime = Read-SimpleEnv $RuntimeConfigPath
$requiredKeys = @(
  'MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE',
  'HRM_SANDBOX_API_KEY', 'HRM_SANDBOX_ADMIN_API_KEY', 'HRM_SANDBOX_MYSQL_HOST', 'HRM_SANDBOX_MYSQL_PORT',
  'HRM_SANDBOX_MYSQL_USER', 'HRM_SANDBOX_MYSQL_PASSWORD', 'HRM_SANDBOX_MYSQL_DATABASE',
  'US37_CLEAN_ADMIN_PASSWORD', 'US37_CLEAN_HR_PASSWORD'
)
foreach ($key in $requiredKeys) {
  if (-not $runtime.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($runtime[$key])) { throw "Local clean UAT config is missing $key." }
}
if ($runtime.MYSQL_DATABASE -ne 'ims_us37_clean_uat' -or $runtime.HRM_SANDBOX_MYSQL_DATABASE -ne 'hrm_us37_clean_uat') {
  throw 'Refusing to run because the configured databases do not match the two clean UAT schemas.'
}
if ($runtime.MYSQL_HOST -notin @('127.0.0.1', 'localhost', '::1') -or $runtime.HRM_SANDBOX_MYSQL_HOST -notin @('127.0.0.1', 'localhost', '::1')) {
  throw 'Clean UAT databases must use a loopback MySQL host.'
}
if ([string]$runtime.MYSQL_PORT -ne '3306' -or [string]$runtime.HRM_SANDBOX_MYSQL_PORT -ne '3306') {
  throw 'Clean UAT is configured for MySQL80 on localhost:3306.'
}
if ($runtime.HRM_SANDBOX_API_KEY -eq $runtime.HRM_SANDBOX_ADMIN_API_KEY) {
  throw 'HRM Sandbox service and Admin API keys must be different.'
}
if ([string]$runtime.HRM_SANDBOX_SEED_DEMO -ne '0' -or [string]$runtime.IMS_DISABLE_EMAIL_WORKER -ne '1') {
  throw 'Clean UAT must keep employee demo seeding and the email worker disabled.'
}

$busy = @()
foreach ($port in @($FrontendPort, $BackendPort, $SandboxPort)) {
  $listenerPid = Get-ListeningPid $port
  if ($listenerPid) { $busy += "$port (PID $listenerPid)" }
}
if ($busy.Count) { throw "UAT did not start because ports are occupied: $($busy -join ', '). Existing processes were left untouched." }

New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$logs = @{
  sandboxOut = Join-Path $runDir 'sandbox.stdout.log'
  sandboxErr = Join-Path $runDir 'sandbox.stderr.log'
  backendOut = Join-Path $runDir 'backend.stdout.log'
  backendErr = Join-Path $runDir 'backend.stderr.log'
  frontendOut = Join-Path $runDir 'frontend.stdout.log'
  frontendErr = Join-Path $runDir 'frontend.stderr.log'
}
$environmentNames = @($runtime.Keys) + @(
  'IMS_DATABASE_BACKEND', 'IMS_SQLITE_PATH', 'MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE',
  'HRM_PROVIDER', 'HRM_SANDBOX_BASE_URL', 'HRM_SANDBOX_API_KEY', 'HRM_SANDBOX_PORT', 'HRM_SANDBOX_DATABASE_BACKEND',
  'HRM_SANDBOX_ADMIN_API_KEY',
  'HRM_SANDBOX_DATABASE_PATH', 'HRM_SANDBOX_MYSQL_HOST', 'HRM_SANDBOX_MYSQL_PORT', 'HRM_SANDBOX_MYSQL_USER',
  'HRM_SANDBOX_MYSQL_PASSWORD', 'HRM_SANDBOX_MYSQL_DATABASE', 'HRM_SANDBOX_SEED_DEMO',
  'IMS_HRM_SANDBOX_OUTBOUND_ENABLED', 'IMS_DISABLE_EMAIL_WORKER', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_FROM',
  'VITE_API_PROXY_TARGET', 'US37_MYSQL_UAT_SCHEMA', 'US37_CLEAN_ADMIN_PASSWORD', 'US37_CLEAN_HR_PASSWORD', 'PYTHONPATH'
) | Select-Object -Unique
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$started = @()

try {
  foreach ($key in $runtime.Keys) { [Environment]::SetEnvironmentVariable($key, [string]$runtime[$key], 'Process') }
  $env:IMS_DATABASE_BACKEND = 'mysql'
  $env:IMS_SQLITE_PATH = ''
  $env:MYSQL_DATABASE = 'ims_us37_clean_uat'
  $env:HRM_PROVIDER = 'sandbox'
  $env:HRM_SANDBOX_BASE_URL = "http://127.0.0.1:$SandboxPort"
  $env:HRM_SANDBOX_PORT = [string]$SandboxPort
  $env:HRM_SANDBOX_DATABASE_BACKEND = 'mysql'
  $env:HRM_SANDBOX_DATABASE_PATH = ''
  $env:HRM_SANDBOX_MYSQL_DATABASE = 'hrm_us37_clean_uat'
  $env:HRM_SANDBOX_SEED_DEMO = '0'
  $env:IMS_HRM_SANDBOX_OUTBOUND_ENABLED = '1'
  $env:IMS_DISABLE_EMAIL_WORKER = '1'
  $env:SMTP_HOST = ''
  $env:SMTP_USERNAME = ''
  $env:SMTP_PASSWORD = ''
  $env:SMTP_FROM = ''
  $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$BackendPort"
  $env:US37_MYSQL_UAT_SCHEMA = 'ims_us37_clean_uat'
  $env:PYTHONPATH = $backendDir

  Push-Location -LiteralPath $repoRoot
  try {
    & $pythonPath (Join-Path $repoRoot 'scripts\migrate_us37_mysql_uat.py')
    if ($LASTEXITCODE -ne 0) { throw 'US37 MySQL schema migration failed.' }
    Push-Location -LiteralPath $backendDir
    try {
      & $pythonPath -m app.us37_clean_uat_seed
      if ($LASTEXITCODE -ne 0) { throw 'Clean UAT login account preparation failed.' }
    } finally { Pop-Location }
  } finally { Pop-Location }

  # Login passwords are needed only for the idempotent account seed, never by the running services.
  Remove-Item Env:US37_CLEAN_ADMIN_PASSWORD, Env:US37_CLEAN_HR_PASSWORD -ErrorAction SilentlyContinue
  Push-Location -LiteralPath $backendDir
  try {
    $sandbox = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'app.hrm_sandbox') -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $logs.sandboxOut -RedirectStandardError $logs.sandboxErr
    $started += @{ name = 'hrm-sandbox'; id = $sandbox.Id; executable = $pythonPath; marker = 'app.hrm_sandbox'; port = $SandboxPort }
    $backend = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', [string]$BackendPort, '--log-level', 'warning') -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $logs.backendOut -RedirectStandardError $logs.backendErr
    $started += @{ name = 'ims-backend'; id = $backend.Id; executable = $pythonPath; marker = 'uvicorn app.main:app'; port = $BackendPort }
  } finally { Pop-Location }
  $frontend = Start-Process -FilePath $nodePath -ArgumentList @($vitePath, '--host', '127.0.0.1', '--port', [string]$FrontendPort, '--strictPort') -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $logs.frontendOut -RedirectStandardError $logs.frontendErr
  $started += @{ name = 'ims-frontend'; id = $frontend.Id; executable = $nodePath; marker = 'vite'; port = $FrontendPort }

  $deadline = (Get-Date).AddSeconds(60)
  $servicesReady = $false
  while ((Get-Date) -lt $deadline) {
    foreach ($service in $started) {
      if (-not (Get-Process -Id $service.id -ErrorAction SilentlyContinue)) { throw "A UAT service exited during startup; inspect run logs at $runDir." }
    }
    try {
      $sandboxHeaders = @{ Authorization = "Bearer $($runtime.HRM_SANDBOX_API_KEY)" }
      $sandboxHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$SandboxPort/api/v1/health" -Headers $sandboxHeaders -TimeoutSec 3
      $backendHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/" -TimeoutSec 3
      $frontendHealth = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$FrontendPort/" -TimeoutSec 3
      if ($sandboxHealth.status -ne 'ok' -or $sandboxHealth.database_backend -ne 'mysql' -or $sandboxHealth.database_name -ne 'hrm_us37_clean_uat' -or $sandboxHealth.employee_count -lt 0) {
        throw 'HRM Sandbox did not report the expected local MySQL schema.'
      }
      if ($backendHealth.status -ne 'Online' -or $frontendHealth.StatusCode -ne 200) { throw 'IMS service health check failed.' }
      $servicesReady = $true
      break
    } catch {
      if ((Get-Date) -ge $deadline) { throw "UAT health, login, or connection check failed. Inspect run logs at $runDir." }
      Start-Sleep -Milliseconds 700
    }
  }
  if (-not $servicesReady) { throw "UAT services did not become healthy within 60 seconds. Inspect run logs at $runDir." }

  $loginBody = @{ email = 'admin@internship.vn'; mat_khau = $runtime.US37_CLEAN_ADMIN_PASSWORD } | ConvertTo-Json -Compress
  $login = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$BackendPort/api/auth/login" -ContentType 'application/json' -Body $loginBody -TimeoutSec 5
  if (-not $login.token -or $login.user.vai_tro -ne 'Admin') { throw 'UAT Admin login did not return an Admin session.' }
  $imsHeaders = @{ Authorization = "Bearer $($login.token)" }
  $connectionCheck = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$BackendPort/api/integrations/hrm/test-connection" -Headers $imsHeaders -TimeoutSec 10
  if ($connectionCheck.state -ne 'CONNECTED') { throw 'IMS could not complete the authenticated HRM Sandbox connection check.' }
  & $pythonPath (Join-Path $repoRoot 'scripts\verify_us37_clean_mysql_uat.py')
  if ($LASTEXITCODE -ne 0) { throw 'Clean UAT database verification failed.' }

  $state = [ordered]@{
    source_root = $repoRoot
    branch = (& git -C $repoRoot branch --show-current).Trim()
    head = (& git -C $repoRoot rev-parse HEAD).Trim()
    database = 'ims_us37_clean_uat'
    sandbox_database = 'hrm_us37_clean_uat'
    database_directory = $stateDir
    log_directory = $runDir
    started_at = (Get-Date).ToString('o')
    ports = @{ frontend = $FrontendPort; backend = $BackendPort; sandbox = $SandboxPort }
    processes = $started
  }
  $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
  Write-Output 'Clean MySQL UAT IMS + HRM Sandbox is ready.'
  Write-Output "Frontend: http://localhost:$FrontendPort"
  Write-Output "Backend: http://localhost:$BackendPort"
  Write-Output "HRM Sandbox: http://127.0.0.1:$SandboxPort"
  Write-Output 'IMS database: ims_us37_clean_uat'
  Write-Output 'HRM database: hrm_us37_clean_uat'
  Write-Output "HRM Sandbox employees: $($sandboxHealth.employee_count) (existing UAT data preserved)"
  Write-Output 'IMS HRM directory: 0'
  Write-Output "Process record: $statePath"
} catch {
  for ($index = $started.Count - 1; $index -ge 0; $index--) {
    $service = $started[$index]
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($service.id)" -ErrorAction SilentlyContinue
    if ($process -and [string]::Equals($process.ExecutablePath, $service.executable, [StringComparison]::OrdinalIgnoreCase) -and $process.CommandLine -like "*$($service.marker)*") {
      $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($service.id)" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$($service.marker)*" }
      foreach ($child in $children) { Stop-Process -Id ([int]$child.ProcessId) -ErrorAction SilentlyContinue }
      Stop-Process -Id ([int]$process.ProcessId) -ErrorAction SilentlyContinue
    }
  }
  throw
} finally {
  foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process') }
  Remove-Variable runtime, login, sandboxHeaders, imsHeaders, loginBody -ErrorAction SilentlyContinue
}
