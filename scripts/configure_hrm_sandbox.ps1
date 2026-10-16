param(
  [Parameter(Mandatory = $true)][string]$ImsEnvPath,
  [Parameter(Mandatory = $true)][string]$SandboxEnvPath,
  [string]$SandboxDatabasePath = (Join-Path $env:LOCALAPPDATA 'IMS-HRM-SANDBOX\hrm-sandbox.sqlite3')
)

$ErrorActionPreference = 'Stop'

function Read-EnvLines([string]$Path) {
  if (Test-Path -LiteralPath $Path) { return ,([IO.File]::ReadAllLines($Path, [Text.Encoding]::UTF8)) }
  return ,([string[]]@())
}

function Read-Key([string[]]$Lines, [string]$Name = 'HRM_SANDBOX_API_KEY') {
  $entries = @($Lines | Where-Object { $_ -match ('^\s*' + [regex]::Escape($Name) + '\s*=') })
  if ($entries.Count -ne 1) { return $null }
  $candidate = ($entries[0] -split '=', 2)[1].Trim().Trim('"').Trim("'")
  if ($candidate.Length -lt 32 -or $candidate -match '[^\x21-\x7E]') { return $null }
  return $candidate
}

function Set-EnvValues([string]$Path, [System.Collections.IDictionary]$Values) {
  $parent = Split-Path -Parent $Path
  if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
  $exists = Test-Path -LiteralPath $Path
  $hasBom = $false
  if ($exists) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
  }
  $lines = [System.Collections.Generic.List[string]]::new()
  foreach ($line in (Read-EnvLines $Path)) { $lines.Add([string]$line) }
  foreach ($name in $Values.Keys) {
    $indices = [System.Collections.Generic.List[int]]::new()
    for ($index = 0; $index -lt $lines.Count; $index++) {
      if ($lines[$index] -match ('^\s*' + [regex]::Escape([string]$name) + '\s*=')) { $indices.Add($index) }
    }
    $valueLine = [string]$name + '=' + [string]$Values[$name]
    if ($indices.Count -eq 0) { $lines.Add($valueLine); continue }
    $lines[$indices[0]] = $valueLine
    for ($remove = $indices.Count - 1; $remove -ge 1; $remove--) { $lines.RemoveAt($indices[$remove]) }
  }
  [IO.File]::WriteAllLines($Path, $lines.ToArray(), [Text.UTF8Encoding]::new($hasBom))
}

$imsPath = [IO.Path]::GetFullPath($ImsEnvPath)
$sandboxPath = [IO.Path]::GetFullPath($SandboxEnvPath)
$sandboxLines = Read-EnvLines $sandboxPath
$existingKey = Read-Key (Read-EnvLines $imsPath)
if ($existingKey) {
  $apiKey = $existingKey
} else {
  $randomBytes = New-Object byte[] 48
  $random = [Security.Cryptography.RandomNumberGenerator]::Create()
  $random.GetBytes($randomBytes)
  $random.Dispose()
  $apiKey = [Convert]::ToBase64String($randomBytes)
}
$adminKey = Read-Key $sandboxLines 'HRM_SANDBOX_ADMIN_API_KEY'
if (-not $adminKey -or [string]::Equals($adminKey, $apiKey, [StringComparison]::Ordinal)) {
  $adminBytes = New-Object byte[] 48
  $random = [Security.Cryptography.RandomNumberGenerator]::Create()
  $random.GetBytes($adminBytes)
  $random.Dispose()
  $adminKey = [Convert]::ToBase64String($adminBytes)
}

$sharedValues = [ordered]@{
  HRM_PROVIDER = 'sandbox'
  HRM_SANDBOX_BASE_URL = 'http://127.0.0.1:8100'
  HRM_SANDBOX_API_KEY = $apiKey
  HRM_SANDBOX_TIMEOUT_SECONDS = '5'
  HRM_SANDBOX_PORT = '8100'
  HRM_SANDBOX_DATABASE_PATH = [IO.Path]::GetFullPath($SandboxDatabasePath)
}
Set-EnvValues $imsPath $sharedValues
Set-EnvValues $sandboxPath $sharedValues
Set-EnvValues $sandboxPath ([ordered]@{ HRM_SANDBOX_ADMIN_API_KEY = $adminKey })

$imsKey = Read-Key (Read-EnvLines $imsPath)
$sandboxKey = Read-Key (Read-EnvLines $sandboxPath)
if (-not $imsKey -or -not [string]::Equals($imsKey, $sandboxKey, [StringComparison]::Ordinal)) {
  throw 'HRM configuration verification failed. API key values were not displayed.'
}
if ([string]::Equals($sandboxKey, $adminKey, [StringComparison]::Ordinal)) {
  throw 'Sandbox admin and service credentials are not isolated.'
}

Remove-Variable apiKey, adminKey, existingKey, imsKey, sandboxKey, randomBytes, adminBytes, sharedValues -ErrorAction SilentlyContinue
Write-Output 'HRM Sandbox service settings are aligned; a separate local admin credential is configured. No key was displayed.'
