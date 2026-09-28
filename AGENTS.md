# Project guidance for Codex

## Before changing code
- Read this file, then inspect only the relevant routes, components, schemas, SQL, and callers.
- Check Git status and preserve every pre-existing edit, untracked file, local database, and nested repository. Never reset, clean, overwrite, or delete user data.
- For work spanning modules or changing behavior, write a short objective, scope, acceptance criteria, and verification plan first.

## Implementation
- Follow the existing React + Vite frontend and FastAPI backend. The configured live runtime is MySQL (`IMS_DATABASE_BACKEND=mysql`); `backend/app/internship.db` is a legacy/local SQLite copy and SQLite is also used for isolated tests. Treat source code and each live database schema as separate sources of truth; review SQL migrations before touching either.
- Make the smallest behavior-preserving change that meets the request. Implement one slice at a time and inspect its callers and data flow.
- Do not add tools, dependencies, generated maps, abstractions, or files without a concrete benefit.
- Treat identity, authorization, user input, database changes, and secrets as security-sensitive. Authorization must use trusted server-side identity; client-supplied role headers do not prove identity.
- For bugs, reproduce behavior and add a focused regression check when practical. Avoid broad refactors while fixing defects.

## Verification and review
- Frontend: run npm run lint and npm run build from frontend/ for frontend changes.
- Backend: run .\.venv\Scripts\python -m compileall -q app from backend/ and focused isolated tests with .\.venv\Scripts\python -m unittest discover -s tests -v. Never point the test suite at the live MySQL schema or the legacy local database.
- After each coherent change group, report exact commands and results. Never claim a check passed unless it ran successfully.
- Review the final diff for behavior, security, dead code, duplication, naming, and scope. Ask whether each abstraction or file earns its maintenance cost.
- Do not commit, publish, run production migrations, or modify the local database unless explicitly asked.
