# US37 — HRM Sandbox integration

This feature contains a local HRM demonstration service and an Admin-only IMS
workflow. **The sandbox is synthetic and is not a connection to a real company
HRM.** It binds to `127.0.0.1` only and stores its records in a separate SQLite
file. The IMS directory, preview tokens, department mappings, and sync history
are stored in the currently configured IMS database.

## Local setup

1. Create `backend/.env` from `backend/.env.example` if it does not exist.
2. Configure one random local API key in the ignored `backend/.env` files used
   by the IMS backend and Sandbox. This script preserves MySQL/SMTP settings,
   aligns the same key in both files, and never prints it:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\configure_hrm_sandbox.ps1 `
     -ImsEnvPath 'D:\antigravity_file\InternshipManagement_TTCS_T926_K17C3_N5\backend\.env' `
     -SandboxEnvPath 'D:\Codex_file\ims-sprint4-us37-hrm\backend\.env'
   ```

   Run it once with the local workspace paths. Do not commit or share either
   `backend/.env` file.
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
stopping anything if one is occupied. It reads the configured Sandbox key from
the current worktree's ignored `backend/.env`, uses separate persistent SQLite files under
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

To start only the standalone Sandbox in the background, double-click
`scripts\run_hrm_sandbox.bat`; stop its verified process with
`scripts\stop_hrm_sandbox.bat`. These scripts use `127.0.0.1:8100`, keep logs
and the standalone SQLite database under `%LOCALAPPDATA%\IMS-HRM-SANDBOX`, and
leave the data in place when stopped. If UAT already owns port 8100, the
standalone launcher exits without stopping or duplicating it.

For normal IMS runtime, the IMS `backend/.env` must use the same
`HRM_PROVIDER`, `HRM_SANDBOX_BASE_URL`, and `HRM_SANDBOX_API_KEY` values as the
Sandbox. Start the Sandbox separately, apply the migration only to an isolated
test IMS database, and then use the repository's `run_server.bat`.

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

Sandbox sample employees use stable IDs (`NV001`–`NV018`), multiple departments,
active and inactive statuses, and `.test` email domains. Startup inserts any
missing sample IDs without replacing records already edited in the Sandbox.
Data persists in a dedicated SQLite file, defaulting to
`backend/.local/hrm-sandbox.sqlite3`; override with
`HRM_SANDBOX_DATABASE_PATH` when needed. The UAT launcher uses its own separate
file and never reads or writes the standalone Sandbox database.

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
- Load the department list, map each source department to the correct existing
  IMS department, and save each mapping. A mapping must be confirmed before
  employee rows from that department can be applied.
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

## Owner demo steps

1. Start the isolated demo with `scripts\run_us37_uat.ps1`.
2. Open `http://localhost:3000`, sign in to the isolated demo as `admin@internship.vn` / `123456`, then open **Admin → Tích hợp HRM**.
3. Click **Kiểm tra kết nối**. Load department codes, select the matching
   existing IMS department for each code, and click **Lưu ánh xạ**.
4. Click **Xem trước đồng bộ**. Review `NEW`, `UPDATE`, `UNCHANGED`,
   `CONFLICT`, and `INVALID` rows and their reasons.
5. Click **Xác nhận đồng bộ** only after reviewing the preview. The result and
   **Lịch sử đồng bộ** show created, updated, unchanged, skipped, and error
   counts.
6. To simulate a source change, update an employee in the Sandbox through its
   authenticated `PATCH /api/v1/employees/{employee_id}` endpoint, then repeat
   preview and confirmation. The included `-VerifyE2E` startup option performs
   this flow against the isolated SQLite test databases.
7. Stop the isolated demo with `scripts\stop_us37_uat.ps1`. Its databases and
   logs remain available for review.

## Real HRM follow-up

`SANDBOX E2E VERIFIED` means this local service and isolated IMS test database
completed the connection/preview/apply/history workflow. It does not mean a
real company HRM is connected. `REAL HRM INTEGRATION PENDING` remains until the
owner supplies the vendor/API contract, stable employee IDs, approved field
ownership, department-code mapping rules, rate limits, and inactive/duplicate
handling policies. Implementing a real provider must use a separate reviewed
adapter and secret provisioning process.
