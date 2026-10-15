"""Local-only HRM Sandbox API backed by its own persistent SQLite database."""
from __future__ import annotations

import hmac
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BACKEND_DIR / ".local" / "hrm-sandbox.sqlite3"
MAX_PAGE_SIZE = 100


def _load_api_key() -> str:
    """Read only the sandbox key from the local env file; never load IMS secrets."""
    env_path = BACKEND_DIR / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key, separator, candidate = line.partition("=")
            key = key.strip()
            if separator and key in {"HRM_SANDBOX_API_KEY", "HRM_SANDBOX_DATABASE_PATH", "HRM_SANDBOX_PORT"}:
                value = candidate.strip().strip('"').strip("'")
                if value:
                    os.environ.setdefault(key, value)
    return os.getenv("HRM_SANDBOX_API_KEY", "")


def _database_path() -> Path:
    configured = os.getenv("HRM_SANDBOX_DATABASE_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else DEFAULT_DB_PATH


class SandboxEmployee(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    employee_id: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    work_email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    department_code: str | None = Field(default=None, max_length=128)
    department_name: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    employment_status: Literal["ACTIVE", "INACTIVE"]
    updated_at: str = Field(min_length=1, max_length=64)

    @field_validator("employee_id", "full_name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Giá trị bắt buộc không hợp lệ.")
        return value

    @field_validator("work_email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().casefold()
        if not value:
            return None
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Email công việc không hợp lệ.")
        return value

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Thời gian cập nhật không hợp lệ.") from exc
        return value


class SandboxEmployeePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    work_email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    department_code: str | None = Field(default=None, max_length=128)
    department_name: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    employment_status: Literal["ACTIVE", "INACTIVE"] | None = None

    @field_validator("work_email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().casefold()
        if not value:
            return None
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Email công việc không hợp lệ.")
        return value


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database() -> None:
    connection = _connect()
    try:
        connection.execute("""CREATE TABLE IF NOT EXISTS sandbox_employees (
            employee_id TEXT PRIMARY KEY COLLATE NOCASE,
            full_name TEXT NOT NULL,
            work_email TEXT NULL,
            phone TEXT NULL,
            department_code TEXT NULL,
            department_name TEXT NULL,
            job_title TEXT NULL,
            employment_status TEXT NOT NULL CHECK(employment_status IN ('ACTIVE', 'INACTIVE')),
            updated_at TEXT NOT NULL
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_sandbox_employees_name ON sandbox_employees(full_name)")
        count = connection.execute("SELECT COUNT(*) FROM sandbox_employees").fetchone()[0]
        if count == 0:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            samples = [
                ("NV001", "Nguyễn An", "nguyen.an@hrm-sandbox.test", "0901000001", "TECH", "Kỹ thuật", "Kỹ sư Backend", "ACTIVE", now),
                ("NV002", "Trần Bình", "tran.binh@hrm-sandbox.test", "0901000002", "OPS", "Vận hành", "Chuyên viên vận hành", "ACTIVE", now),
                ("NV003", "Lê Chi", "le.chi@hrm-sandbox.test", "0901000003", "DATA", "Dữ liệu", "Chuyên viên dữ liệu", "ACTIVE", now),
            ]
            connection.executemany(
                """INSERT OR IGNORE INTO sandbox_employees (
                    employee_id, full_name, work_email, phone, department_code,
                    department_name, job_title, employment_status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                samples,
            )
        connection.commit()
    finally:
        connection.close()


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    expected = _load_api_key()
    scheme, _, supplied = (authorization or "").partition(" ")
    if not expected:
        raise HTTPException(status_code=503, detail="HRM Sandbox chưa được cấu hình credential thử nghiệm.")
    if scheme.casefold() != "bearer" or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Không xác thực được với HRM Sandbox.")


app = FastAPI(title="HRM Sandbox", version="1.0.0", docs_url=None, redoc_url=None)


@app.on_event("startup")
def on_startup() -> None:
    if not _load_api_key():
        raise RuntimeError("HRM_SANDBOX_API_KEY must be configured in the process environment.")
    initialize_database()


@app.get("/api/v1/health", dependencies=[Depends(require_api_key)])
def health():
    return {"status": "ok", "provider_id": "sandbox", "version": app.version}


@app.get("/api/v1/employees", dependencies=[Depends(require_api_key)])
def list_employees(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE)):
    connection = _connect()
    try:
        total = int(connection.execute("SELECT COUNT(*) FROM sandbox_employees").fetchone()[0])
        rows = connection.execute(
            "SELECT employee_id, full_name, work_email, phone, department_code, department_name, "
            "job_title, employment_status, updated_at FROM sandbox_employees "
            "ORDER BY employee_id LIMIT ? OFFSET ?",
            (page_size, (page - 1) * page_size),
        ).fetchall()
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    finally:
        connection.close()


@app.get("/api/v1/employees/{employee_id}", dependencies=[Depends(require_api_key)])
def get_employee(employee_id: str):
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT employee_id, full_name, work_email, phone, department_code, department_name, "
            "job_title, employment_status, updated_at FROM sandbox_employees WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên trong HRM Sandbox.")
        return dict(row)
    finally:
        connection.close()


@app.patch("/api/v1/employees/{employee_id}", response_model=SandboxEmployee, dependencies=[Depends(require_api_key)])
def update_employee(employee_id: str, changes: SandboxEmployeePatch):
    updates = changes.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Cần có ít nhất một trường thay đổi.")
    connection = _connect()
    try:
        current = connection.execute(
            "SELECT employee_id, full_name, work_email, phone, department_code, department_name, "
            "job_title, employment_status, updated_at FROM sandbox_employees WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên trong HRM Sandbox.")
        candidate = dict(current)
        candidate.update(updates)
        candidate["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        validated = SandboxEmployee.model_validate(candidate)
        connection.execute(
            """UPDATE sandbox_employees SET full_name = ?, work_email = ?, phone = ?,
               department_code = ?, department_name = ?, job_title = ?, employment_status = ?, updated_at = ?
               WHERE employee_id = ?""",
            (
                validated.full_name, validated.work_email, validated.phone,
                validated.department_code, validated.department_name, validated.job_title,
                validated.employment_status, validated.updated_at, employee_id,
            ),
        )
        connection.commit()
        return validated
    finally:
        connection.close()


def main() -> None:
    import uvicorn

    try:
        port = int(os.getenv("HRM_SANDBOX_PORT", "8100"))
    except ValueError:
        raise SystemExit("HRM_SANDBOX_PORT must be a valid TCP port.")
    if not 1 <= port <= 65535:
        raise SystemExit("HRM_SANDBOX_PORT must be between 1 and 65535.")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
