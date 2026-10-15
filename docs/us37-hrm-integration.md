# US37 — HRM Sandbox integration

This feature contains a local HRM demonstration service and an Admin-only IMS
workflow. **The sandbox is synthetic and is not a connection to a real company
HRM.** It binds to `127.0.0.1` only and stores its records in a separate SQLite
file. The IMS directory, preview tokens, department mappings, and sync history
are stored in the currently configured IMS database.

## Local setup

1. Create `backend/.env` from `backend/.env.example` if it does not exist.
2. Generate a random local API key and put the following values in that ignored
   `.env` file. The command below updates only the HRM keys and preserves the
   existing MySQL/SMTP settings; it does not print the key:

   ```powershell
   $hrmEnvPath = (Resolve-Path .).Path + '\backend\.env'
   $hrmLines = if (Test-Path -LiteralPath $hrmEnvPath) { [IO.File]::ReadAllLines($hrmEnvPath) } else { @() }
   $hrmBytes = New-Object byte[] 32
   $hrmRng = [Security.Cryptography.RandomNumberGenerator]::Create()
   $hrmRng.GetBytes($hrmBytes)
   $hrmRng.Dispose()
   $hrmKey = [Convert]::ToBase64String($hrmBytes)
   $hrmValues = [ordered]@{
     HRM_PROVIDER = 'sandbox'
     HRM_SANDBOX_BASE_URL = 'http://127.0.0.1:8100'
     HRM_SANDBOX_API_KEY = $hrmKey
     HRM_SANDBOX_TIMEOUT_SECONDS = '5'
     HRM_SANDBOX_PORT = '8100'
   }
   foreach ($hrmName in $hrmValues.Keys) {
     $hrmPattern = '^' + [regex]::Escape($hrmName) + '='
     $hrmLine = $hrmName + '=' + $hrmValues[$hrmName]
     $hrmMatch = -1
     for ($hrmIndex = 0; $hrmIndex -lt $hrmLines.Count; $hrmIndex++) {
       if ($hrmLines[$hrmIndex] -match $hrmPattern) { $hrmMatch = $hrmIndex; break }
     }
     if ($hrmMatch -ge 0) { $hrmLines[$hrmMatch] = $hrmLine } else { $hrmLines += $hrmLine }
   }
   [IO.File]::WriteAllLines($hrmEnvPath, $hrmLines, [Text.UTF8Encoding]::new($false))
   Remove-Variable hrmKey, hrmBytes, hrmValues, hrmLine, hrmName
   ```

   Run this from the repository root. Do not commit or share `backend/.env`.
   The Sandbox reads only its HRM settings from this file; it does not load IMS
   database credentials.

3. Install the backend virtualenv requirements and frontend dependencies if
   needed. The local scripts expect `backend/.venv` and `frontend/node_modules`.
4. Apply `migrations/20261015_us37_hrm_sandbox.sql` **only to an isolated/test
   IMS database**. Do not apply it to a business database without separate
   owner approval and backup.

## Start and stop

To run all three processes on the familiar local URLs with fully isolated test
databases, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_us37_uat.ps1
```

This UAT launcher checks ports 3000, 8000, and 8100 first and exits without
stopping anything if one is occupied. It generates a short-lived API key in
process memory, uses separate persistent SQLite files under
`%LOCALAPPDATA%\IMS-US37-UAT`, and starts only the source in the current
worktree. Open `http://localhost:3000`, sign in using an Admin account from this
isolated demo database, then open **Tích hợp HRM**. It does not connect to the
workspace's MySQL database or alter the root `run_server.bat` behavior.

The seeded demo sign-in is `admin@internship.vn` / `123456`; it exists only in
the isolated SQLite test database and must never be used in production.

To run the synthetic HTTP end-to-end flow as part of startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_us37_uat.ps1 -VerifyE2E
```

This optional check maps `TECH`, imports NV001, repeats sync, updates it, marks
it inactive, and verifies persisted history in the isolated SQLite files. It
intentionally changes only synthetic UAT rows and leaves the services running
for review. The normal launcher without `-VerifyE2E` does not apply a sync
automatically.

Stop only those UAT processes with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_us37_uat.ps1
```

The stop script verifies each recorded PID, executable path, and command line
before stopping it. UAT databases and logs remain in the isolated local folder.

To start only the standalone sandbox interactively, run
`scripts\run_hrm_sandbox.bat`; it listens on `127.0.0.1:8100` and can be stopped
with Ctrl+C in that terminal. For the normal IMS launcher, configure the same
`HRM_PROVIDER`, `HRM_SANDBOX_BASE_URL`, and `HRM_SANDBOX_API_KEY` values in the
IMS `backend/.env`, start the sandbox separately, apply the migration to the
intended test database, and then use the repository's `run_server.bat`.

## Sandbox API

- `GET /api/v1/health` — authenticated connection check.
- `GET /api/v1/employees?page=1&page_size=50` — paginated employee list.
- `GET /api/v1/employees/{employee_id}` — employee detail.
- `PATCH /api/v1/employees/{employee_id}` — change only synthetic Sandbox data
  for testing incremental synchronization.

Every endpoint requires `Authorization: Bearer <HRM_SANDBOX_API_KEY>`. The API
rejects missing/incorrect keys, limits page size and response size, and is
bound to loopback. The adapter accepts only configured loopback URLs, blocks
redirects, uses bounded timeouts/retries, and never accepts a URL from a
browser request. The key is not returned by IMS or rendered in the Admin UI.

Sandbox sample employees use stable IDs (`NV001`–`NV003`) and `.test` email
domains. Data persists in a dedicated SQLite file, defaulting to
`backend/.local/hrm-sandbox.sqlite3`; override with
`HRM_SANDBOX_DATABASE_PATH` when needed.

## IMS workflow and data rules

1. Admin tests the Sandbox connection.
2. Admin maps each source department code to an existing `PHONG_BAN` record.
   No department is created automatically. A missing mapping is `CONFLICT`.
3. Admin creates a preview. Rows are classified as `NEW`, `UPDATE`,
   `UNCHANGED`, `CONFLICT`, or `INVALID`; the UI shows category counts and the
   reason/warnings per row.
4. Admin explicitly confirms apply. The backend re-fetches the Sandbox and
   recalculates the preview. If source data or mappings changed, the preview is
   marked stale and apply is rejected. A per-provider database lease prevents
   concurrent applies. Preview tokens expire after 15 minutes.
5. Valid rows are upserted by `(provider_id, external_employee_id)` into the
   separate `HRM_EMPLOYEE_DIRECTORY`; repeat sync does not create duplicates.
   Sync history records the actor and created/updated/unchanged/skipped/error
   counts.

Imported HRM employee rows are not IMS login accounts. Email matches are
conflicts for manual review; the service never merges accounts by name or
email. The sync does not create accounts, set roles, change permissions, update
Mentor assignments, or rewrite internship history. An `INACTIVE` source status
is retained in the HRM directory with a warning; it does not lock or delete an
IMS account. Department assignment uses the mapped IMS department ID and does
not alter program/mentor history.

All IMS integration endpoints are Admin-only. HR, Mentor, and intern roles are
denied by the backend, even if they call the API directly.

## Safe UAT sequence

- Connect: **Kiểm tra kết nối** should report `CONNECTED`.
- New record: preview includes `NV001` as `NEW` after mapping `TECH`; confirm
  once and verify one row in **Danh bạ HRM đã đồng bộ** plus one history entry.
- Repeat: preview should show `UNCHANGED`; apply does not add another employee.
- Update: change only Sandbox `NV001` through its authenticated PATCH API, then
  preview should show `UPDATE`; apply changes the HRM directory only.
- Inactive: set a Sandbox row to `INACTIVE`; preview warns that IMS access and
  Mentor assignments remain unchanged.
- Conflict: leave a department code unmapped or use an email already present in
  IMS; the row remains unapplied and explains why.
- Error: stop the Sandbox, use an invalid test key, or let the request time out;
  the UI reports a safe connection error and does not apply data.

The UAT launcher logs are in `%LOCALAPPDATA%\IMS-US37-UAT`. Logs contain no
Sandbox key. Do not test writes against the real IMS MySQL database.

## Real HRM follow-up

`SANDBOX E2E VERIFIED` means this local service and isolated IMS test database
completed the connection/preview/apply/history workflow. It does not mean a
real company HRM is connected. `REAL HRM INTEGRATION PENDING` remains until the
owner supplies the vendor/API contract, stable employee IDs, approved field
ownership, department-code mapping rules, rate limits, and inactive/duplicate
handling policies. Implementing a real provider must use a separate reviewed
adapter and secret provisioning process.
