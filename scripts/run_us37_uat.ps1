$VerifyE2E = $false
if ($args -contains '-VerifyE2E') { $VerifyE2E = $true }
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$pythonPath = Join-Path $backendDir '.venv\Scripts\python.exe'
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$vitePath = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
$envPath = Join-Path $backendDir '.env'
$stateDir = Join-Path $env:LOCALAPPDATA 'IMS-US37-UAT'
$statePath = Join-Path $stateDir 'processes.json'

if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Backend virtualenv is missing. Create backend\.venv and install backend\requirements.txt.' }
if (-not (Test-Path -LiteralPath $vitePath)) { throw 'Frontend dependencies are missing. Run npm ci in frontend first.' }
if (-not (Test-Path -LiteralPath $envPath)) { throw 'backend\.env is missing. Configure the local HRM Sandbox first.' }

$keyLines = @([IO.File]::ReadAllLines($envPath) | Where-Object { $_ -match '^\s*HRM_SANDBOX_API_KEY\s*=' })
if ($keyLines.Count -ne 1) { throw 'backend\.env must contain exactly one HRM_SANDBOX_API_KEY entry.' }
$sandboxKey = ($keyLines[0] -split '=', 2)[1].Trim().Trim('"').Trim("'")
if ($sandboxKey.Length -lt 32 -or $sandboxKey -match '[^\x21-\x7E]') { throw 'HRM_SANDBOX_API_KEY must be at least 32 printable ASCII characters.' }

$portsInUse = @()
foreach ($port in @(3000, 8000, 8100)) {
  $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($listener) { $portsInUse += "${port} (PID $($listener.OwningProcess))" }
}
if ($portsInUse.Count -gt 0) {
  throw "UAT stopped before launch because these ports are already in use: $($portsInUse -join ', '). No existing process was stopped."
}

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$logPaths = @{
  sandboxOut = Join-Path $stateDir 'sandbox.stdout.log'
  sandboxErr = Join-Path $stateDir 'sandbox.stderr.log'
  backendOut = Join-Path $stateDir 'backend.stdout.log'
  backendErr = Join-Path $stateDir 'backend.stderr.log'
  frontendOut = Join-Path $stateDir 'frontend.stdout.log'
  frontendErr = Join-Path $stateDir 'frontend.stderr.log'
}
$previousEnvironment = @{}
$environmentNames = @(
  'IMS_DATABASE_BACKEND', 'IMS_SQLITE_PATH', 'HRM_PROVIDER',
  'HRM_SANDBOX_BASE_URL', 'HRM_SANDBOX_API_KEY', 'HRM_SANDBOX_DATABASE_PATH', 'HRM_SANDBOX_PORT'
)
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$started = @()

try {
  $env:IMS_DATABASE_BACKEND = 'sqlite'
  $env:IMS_SQLITE_PATH = Join-Path $stateDir 'ims-uat.sqlite3'
  $env:HRM_PROVIDER = 'sandbox'
  $env:HRM_SANDBOX_BASE_URL = 'http://127.0.0.1:8100'
  $env:HRM_SANDBOX_API_KEY = $sandboxKey
  $env:HRM_SANDBOX_DATABASE_PATH = Join-Path $stateDir 'hrm-sandbox.sqlite3'
  $env:HRM_SANDBOX_PORT = '8100'

  $sandbox = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'app.hrm_sandbox') -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $logPaths.sandboxOut -RedirectStandardError $logPaths.sandboxErr
  $started += @{ name = 'hrm-sandbox'; id = $sandbox.Id; executable = $pythonPath; marker = 'app.hrm_sandbox' }

  $backend = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--workers', '1', '--log-level', 'warning') -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $logPaths.backendOut -RedirectStandardError $logPaths.backendErr
  $started += @{ name = 'ims-backend'; id = $backend.Id; executable = $pythonPath; marker = 'uvicorn app.main:app' }

  $frontend = Start-Process -FilePath $nodePath -ArgumentList @($vitePath, '--host', '127.0.0.1', '--port', '3000', '--strictPort') -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $logPaths.frontendOut -RedirectStandardError $logPaths.frontendErr
  $started += @{ name = 'ims-frontend'; id = $frontend.Id; executable = $nodePath; marker = $vitePath }

  $deadline = (Get-Date).AddSeconds(45)
  $ready = $false
  $lastChecks = 'No health response yet.'
  $lastFailure = 'No request error recorded.'
  while ((Get-Date) -lt $deadline) {
    $alive = $true
    foreach ($service in $started) { if (-not (Get-Process -Id $service.id -ErrorAction SilentlyContinue)) { $alive = $false } }
    if (-not $alive) { throw 'A UAT service exited during startup. See the isolated logs in %LOCALAPPDATA%\IMS-US37-UAT.' }
    try {
      $headers = @{ Authorization = "Bearer $sandboxKey" }
      $sandboxHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8100/api/v1/health' -Headers $headers -TimeoutSec 2
      $lastChecks = "sandbox=$($sandboxHealth.status)"
      $backendHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/' -TimeoutSec 2
      $lastChecks += "; backend=$($backendHealth.status)"
      $frontendHealth = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 2
      $lastChecks += "; frontend=$($frontendHealth.StatusCode)"
      if ($sandboxHealth.status -eq 'ok' -and $backendHealth.status -eq 'Online' -and $frontendHealth.StatusCode -eq 200) { $ready = $true; break }
    } catch { $lastFailure = $_.Exception.Message; Start-Sleep -Milliseconds 500 }
  }
  if (-not $ready) { throw "UAT services did not become healthy within 45 seconds ($lastChecks; last request error: $lastFailure). See isolated logs in %LOCALAPPDATA%\IMS-US37-UAT." }

  foreach ($service in $started) {
    $port = switch ($service.name) {
      'hrm-sandbox' { 8100 }
      'ims-backend' { 8000 }
      default { $null }
    }
    if (-not $port) { continue }
    $listener = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    $launcher = Get-CimInstance Win32_Process -Filter "ProcessId = $($service.id)" -ErrorAction SilentlyContinue
    $worker = if ($listener) { Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue }
    if (-not $launcher -or -not $worker -or $worker.ParentProcessId -ne $launcher.ProcessId -or
        $launcher.ExecutablePath -ne $service.executable -or $launcher.CommandLine -notlike "*$($service.marker)*" -or
        $worker.CommandLine -notlike "*$($service.marker)*") {
      throw "Could not verify the exact isolated process tree for the UAT service on port $port."
    }
    $service.parent_id = $launcher.ProcessId
    $service.parent_executable = $launcher.ExecutablePath
    $service.parent_marker = $service.marker
    $service.id = $worker.ProcessId
    $service.executable = $worker.ExecutablePath
  }

  if ($VerifyE2E) {
    $imsLogin = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/auth/login' `
      -ContentType 'application/json' `
      -Body (@{ email = 'admin@internship.vn'; mat_khau = '123456' } | ConvertTo-Json -Compress) `
      -TimeoutSec 10
    if (-not $imsLogin.token -or $imsLogin.user.vai_tro -ne 'Admin') { throw 'Isolated UAT Admin login failed.' }
    $imsHeaders = @{ Authorization = "Bearer $($imsLogin.token)" }
    $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/integrations/hrm/status' -Headers $imsHeaders -TimeoutSec 10
    if (-not $status.can_preview) { throw 'HRM preview is not enabled in the isolated IMS SQLite database.' }
    $connection = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/integrations/hrm/test-connection' -Headers $imsHeaders -TimeoutSec 10
    if ($connection.state -ne 'CONNECTED') { throw 'IMS could not authenticate with HRM Sandbox.' }

    $mappingData = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/integrations/hrm/department-mappings' -Headers $imsHeaders -TimeoutSec 10
    $tech = $mappingData.hrm_departments | Where-Object { $_.department_code -eq 'TECH' } | Select-Object -First 1
    $imsDepartment = $mappingData.ims_departments | Select-Object -First 1
    if (-not $tech -or -not $imsDepartment) { throw 'UAT mapping prerequisites are missing.' }
    Invoke-RestMethod -Method Put -Uri 'http://127.0.0.1:8000/api/integrations/hrm/department-mappings' `
      -Headers $imsHeaders -ContentType 'application/json' `
      -Body (@{ department_code = 'TECH'; ma_phong_ban = $imsDepartment.ma_phong_ban } | ConvertTo-Json -Compress) `
      -TimeoutSec 10 | Out-Null

    $preview = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/integrations/hrm/preview' -Headers $imsHeaders -TimeoutSec 20
    if (($preview.counts.NEW + $preview.counts.UNCHANGED) -lt 1) { throw 'Expected NV001 to be importable or already synchronized.' }
    $firstApply = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/integrations/hrm/apply' `
      -Headers $imsHeaders -ContentType 'application/json' `
      -Body (@{ preview_id = $preview.preview_id } | ConvertTo-Json -Compress) -TimeoutSec 20

    $unchangedPreview = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/integrations/hrm/preview' -Headers $imsHeaders -TimeoutSec 20
    if ($unchangedPreview.counts.UNCHANGED -lt 1) { throw 'A repeated sync did not classify NV001 as UNCHANGED.' }
    $secondApply = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/integrations/hrm/apply' `
      -Headers $imsHeaders -ContentType 'application/json' `
      -Body (@{ preview_id = $unchangedPreview.preview_id } | ConvertTo-Json -Compress) -TimeoutSec 20
    $directory = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/integrations/hrm/directory?page=1&page_size=100' -Headers $imsHeaders -TimeoutSec 10
    if ($directory.total -ne 1) { throw "Duplicate prevention failed: expected one imported sandbox record, found $($directory.total)." }

    $sandboxHeaders = @{ Authorization = "Bearer $sandboxKey" }
    $changedPhone = '0901' + (Get-Date -Format 'HHmmss')
    Invoke-RestMethod -Method Patch -Uri 'http://127.0.0.1:8100/api/v1/employees/NV001' `
      -Headers $sandboxHeaders -ContentType 'application/json' `
      -Body (@{ phone = $changedPhone } | ConvertTo-Json -Compress) -TimeoutSec 10 | Out-Null
    $updatePreview = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/integrations/hrm/preview' -Headers $imsHeaders -TimeoutSec 20
    if ($updatePreview.counts.UPDATE -lt 1) { throw 'A changed sandbox employee was not classified as UPDATE.' }
    $updateApply = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/integrations/hrm/apply' `
      -Headers $imsHeaders -ContentType 'application/json' `
      -Body (@{ preview_id = $updatePreview.preview_id } | ConvertTo-Json -Compress) -TimeoutSec 20

    Invoke-RestMethod -Method Patch -Uri 'http://127.0.0.1:8100/api/v1/employees/NV001' `
      -Headers $sandboxHeaders -ContentType 'application/json' `
      -Body (@{ employment_status = 'INACTIVE' } | ConvertTo-Json -Compress) -TimeoutSec 10 | Out-Null
    $inactivePreview = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/integrations/hrm/preview' -Headers $imsHeaders -TimeoutSec 20
    $inactiveRow = $inactivePreview.rows | Where-Object { $_.external_employee_id -eq 'NV001' } | Select-Object -First 1
    if ($inactiveRow.action -ne 'UPDATE' -or -not $inactiveRow.warnings) { throw 'INACTIVE change was not represented as a safe directory update with warning.' }
    $inactiveApply = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/integrations/hrm/apply' `
      -Headers $imsHeaders -ContentType 'application/json' `
      -Body (@{ preview_id = $inactivePreview.preview_id } | ConvertTo-Json -Compress) -TimeoutSec 20
    $history = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/integrations/hrm/history?page=1&page_size=100' -Headers $imsHeaders -TimeoutSec 10
    if ($history.total -lt 4) { throw 'Sync history did not persist all four apply operations.' }
    Write-Output 'SANDBOX E2E VERIFIED: connection, mapping, NEW/UNCHANGED/UPDATE/INACTIVE, explicit apply, deduplication, and persistent history.'
    Write-Output 'All E2E writes were limited to the isolated HRM Sandbox and IMS SQLite UAT databases.'
    Remove-Variable imsLogin, imsHeaders, status, connection, mappingData, tech, imsDepartment, preview, firstApply, unchangedPreview, secondApply, directory, sandboxHeaders, changedPhone, updatePreview, updateApply, inactivePreview, inactiveRow, inactiveApply, history -ErrorAction SilentlyContinue
  }

  $state = @{
    repo_root = $repoRoot
    started_at = (Get-Date).ToUniversalTime().ToString('o')
    processes = $started
    logs = $logPaths
    database_directory = $stateDir
  }
  $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
  Write-Output 'US37 isolated UAT is ready: http://localhost:3000'
  Write-Output 'Backend: http://127.0.0.1:8000 | HRM Sandbox: http://127.0.0.1:8100'
  Write-Output 'IMS and HRM use separate persistent SQLite files under %LOCALAPPDATA%\IMS-US37-UAT.'
  Write-Output 'Use scripts\stop_us37_uat.ps1 to stop only these verified UAT processes.'
} catch {
  foreach ($service in $started) {
    if ($service.parent_id) {
      $worker = Get-CimInstance Win32_Process -Filter "ProcessId = $($service.id)" -ErrorAction SilentlyContinue
      if ($worker -and $worker.ParentProcessId -eq $service.parent_id -and $worker.ExecutablePath -eq $service.executable -and $worker.CommandLine -like "*$($service.marker)*") {
        Stop-Process -Id $worker.ProcessId -ErrorAction SilentlyContinue
      }
      $launcher = Get-CimInstance Win32_Process -Filter "ProcessId = $($service.parent_id)" -ErrorAction SilentlyContinue
      if ($launcher -and $launcher.ExecutablePath -eq $service.parent_executable -and $launcher.CommandLine -like "*$($service.parent_marker)*") {
        Stop-Process -Id $launcher.ProcessId -ErrorAction SilentlyContinue
      }
    } else {
      $launcher = Get-CimInstance Win32_Process -Filter "ProcessId = $($service.id)" -ErrorAction SilentlyContinue
      if ($launcher -and $launcher.ExecutablePath -eq $service.executable -and $launcher.CommandLine -like "*$($service.marker)*") {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($service.id)" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$($service.marker)*" }
        foreach ($child in $children) { Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $launcher.ProcessId -ErrorAction SilentlyContinue
      }
    }
  }
  throw
} finally {
  foreach ($name in $environmentNames) {
    [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
  }
  Remove-Variable sandboxKey -ErrorAction SilentlyContinue
}
