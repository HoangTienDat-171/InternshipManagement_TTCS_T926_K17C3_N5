# US37 — HRM integration readiness and provider contract

## Current state

The Product Backlog describes synchronizing employee data from an HRM, but does
not name a vendor or provide API documentation, a sandbox, credentials, a stable
employee identifier, or field ownership rules. The current source has no HRM
adapter or employee-to-IMS external-ID mapping. The Admin page and
`GET /api/integrations/hrm/status` report this as **NOT_CONFIGURED**. No network
connection, preview from real HRM data, or synchronization is performed.

## Adapter contract

A vendor adapter must implement the `HRMProvider` protocol in
`backend/app/hrm_integration.py`:

- `provider_name`: non-secret vendor label for Admin status.
- `test_connection()`: use the vendor's approved sandbox and return no
  credentials or response payloads containing personal data.
- `fetch_employees()`: translate vendor-specific pagination and schema into
  validated `HRMEmployeeRecord` objects. Reject malformed responses and duplicate
  external employee IDs before creating a preview.

The adapter must use a reviewed HTTPS host allowlist, bounded timeouts and
response sizes, secure secret storage, and vendor-specific authentication. Do
not accept arbitrary endpoint URLs from browser requests or dynamically import
adapter code based on user input.

## Canonical record and matching rules

The provider adapter may return only the agreed fields: stable external employee
ID, name, work email, phone, department, job title, and active/inactive status.
Additional fields are rejected by the canonical model. A stable external ID is
the only automatic identity link. An email match can appear only as a manual
review suggestion; it must never merge accounts silently.

Preview is review-only. It requires an explicit confirmation step before writes.
HRM status/title never assigns IMS roles or permissions. Inactive HRM status must
not automatically delete or lock an IMS account, remove Mentor assignments, or
rewrite internship history. Department changes require an approved policy and
must not rewrite historical program/mentor assignments. Intern profiles,
internship programs, evaluations, attendance, leave, and allowances are outside
the HRM sync scope.

## Information needed before real integration can be completed

1. HRM vendor/product and official API contract, including pagination and rate
   limits.
2. Sandbox tenant, approved HTTPS hostnames, and authentication mechanism.
3. Secret provisioning channel; credentials must not be committed or returned
   by the API/UI.
4. Stable employee ID and approved mapping/ownership for each field.
5. HR decisions for duplicate records, email changes, department changes, and
   inactive employees.
6. A sanitized sample response and an owner-approved test plan.

Until these are supplied, the Admin interface intentionally leaves connection,
preview, sync, and history actions unavailable. The module's contract and pure
preview planner can be tested without contacting HRM or touching the local IMS
database.
