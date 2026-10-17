# Local launcher and HRM Sandbox configuration

Run `run_server.bat` from the main workspace. Its local wrapper points at the selected current source checkout and reads configuration from the main workspace's ignored `backend/.env` file. The launcher performs read-only MySQL checks and does not migrate, create, seed, reset, or copy a database. It also skips application startup schema initialization for both IMS and Sandbox.

## HRM Sandbox API keys

The canonical local config file is:

`D:\antigravity_file\InternshipManagement_TTCS_T926_K17C3_N5\backend\.env`

Use these distinct variables:

- `HRM_SANDBOX_API_KEY`: service key shared by IMS and Sandbox for integration requests.
- `HRM_SANDBOX_ADMIN_API_KEY`: separate key for administrator actions in the local Sandbox console.

Open the file from the source checkout with `scripts\open_sandbox_config.bat`. When the launcher is called from the main workspace, its `IMS_CONFIG_ROOT` points to the main workspace config. Do not paste either value into source code, issues, logs, or chat. The Sandbox console requires the admin key; do not use the IMS service key for administrator actions.

To check that both entries are present without displaying their values, run this in PowerShell:

```powershell
$configPath = 'D:\antigravity_file\InternshipManagement_TTCS_T926_K17C3_N5\backend\.env'
$lines = Get-Content -LiteralPath $configPath
foreach ($name in @('HRM_SANDBOX_API_KEY', 'HRM_SANDBOX_ADMIN_API_KEY')) {
    $entry = $lines | Where-Object { $_ -match ('^\s*' + [regex]::Escape($name) + '\s*=\s*\S') } | Select-Object -First 1
    '{0} configured: {1}' -f $name, [bool]$entry
}
```

The launcher authenticates both keys against the read-only Sandbox health endpoint. If a key genuinely needs replacement, update the corresponding local configuration on both sides and restart IMS and Sandbox together. Do not rotate credentials just to re-open the config.

## Local file storage

For MySQL mode, `IMS_SQLITE_PATH` is used only as a stable path anchor by existing upload and backup code. It must point under the main workspace so old documents, reports, contracts, and attachments remain visible while the database backend remains MySQL. `EMAIL_ATTACHMENT_ROOT` keeps the email attachment store in its existing main-workspace directory.

## Startup and shutdown

- Start: main workspace `run_server.bat`
- Stop only launcher-owned processes: main workspace `stop_server.bat`
- MySQL is never stopped by `stop_server.bat`.
- Existing processes are reused only when their source fingerprint, configuration, database target, and health checks match. A port conflict with a different or unverifiable process is reported without terminating it.
- SMTP is checked with TLS/authentication only; the launcher sends no test email. The in-process outbox worker starts with the backend when configured and is stopped through backend shutdown.
