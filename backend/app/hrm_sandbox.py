"""Local-only HRM Sandbox API backed by its own persistent SQLite database."""
from __future__ import annotations

import hmac
import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BACKEND_DIR / ".local" / "hrm-sandbox.sqlite3"
MAX_PAGE_SIZE = 100
ADMIN_PRINCIPAL = "sandbox_admin_api_key"
SERVICE_PRINCIPAL = "ims_service_api_key"
AUDIT_FIELDS = {
    "EMPLOYEE": {
        "full_name": "Họ và tên",
        "work_email": "Email công việc",
        "phone": "Số điện thoại công việc",
        "department_code": "Mã phòng ban",
        "department_name": "Tên phòng ban",
        "job_title": "Chức danh",
        "employment_status": "Trạng thái nhân sự",
    },
    "DEPARTMENT": {
        "department_code": "Mã phòng ban",
        "department_name": "Tên phòng ban",
        "is_active": "Trạng thái phòng ban",
    },
}
SENSITIVE_AUDIT_FIELDS = {"work_email", "phone"}


def _load_env_value(name: str) -> str:
    """Read one HRM credential from the local env file without loading IMS secrets."""
    env_path = BACKEND_DIR / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key, separator, candidate = line.partition("=")
            key = key.strip()
            if separator and key == name:
                value = candidate.strip().strip('"').strip("'")
                if value:
                    os.environ.setdefault(name, value)
                    break
    return os.getenv(name, "")


def _load_api_key() -> str:
    """Return the service-to-service key used by IMS."""
    return _load_env_value("HRM_SANDBOX_API_KEY")


def _load_admin_api_key() -> str:
    """Return the separately scoped key used by the local Sandbox console."""
    return _load_env_value("HRM_SANDBOX_ADMIN_API_KEY")


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
    expected_updated_at: str | None = Field(default=None, min_length=1, max_length=64)
    reason: str | None = Field(default=None, max_length=500)

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


class SandboxEmployeeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    employee_id: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    work_email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    department_code: str | None = Field(default=None, max_length=128)
    job_title: str | None = Field(default=None, max_length=200)
    employment_status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"

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


class SandboxDepartmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    department_code: str = Field(min_length=1, max_length=32)
    department_name: str = Field(min_length=1, max_length=200)

    @field_validator("department_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,31}", value):
            raise ValueError("Mã phòng ban chỉ được gồm chữ Latin, số, dấu gạch ngang hoặc gạch dưới.")
        return value


class SandboxDepartmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    department_code: str | None = Field(default=None, min_length=1, max_length=32)
    department_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    expected_updated_at: str = Field(min_length=1, max_length=64)
    confirm_ims_mapping_impact: bool = False
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("department_code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,31}", value):
            raise ValueError("Mã phòng ban chỉ được gồm chữ Latin, số, dấu gạch ngang hoặc gạch dưới.")
        return value


class CandidateProgram(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    program_reference: str = Field(min_length=1, max_length=64)
    program_name: str = Field(min_length=1, max_length=200)
    start_date: str | None = Field(default=None, max_length=10)
    completion_date: str | None = Field(default=None, max_length=10)
    completion_confirmed_at: str = Field(min_length=1, max_length=64)


class CandidateRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_reference: str = Field(min_length=1, max_length=128, pattern=r"^ims-profile-[1-9][0-9]*$")
    full_name: str = Field(min_length=1, max_length=200)
    request_type: Literal["candidate_review"]
    source_status: Literal["HR_REVIEW_REQUESTED"]
    completed_programs: list[CandidateProgram] = Field(min_length=1, max_length=20)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("A valid full name is required.")
        return value


class CandidateRequestDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["ACCEPT", "REJECT"]
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


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
        connection.execute("""CREATE TABLE IF NOT EXISTS sandbox_departments (
            department_code TEXT PRIMARY KEY COLLATE NOCASE,
            department_name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS sandbox_change_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL CHECK(entity_type IN ('EMPLOYEE', 'DEPARTMENT')),
            entity_id TEXT NOT NULL,
            action TEXT NOT NULL,
            before_json TEXT NULL,
            after_json TEXT NULL,
            reason TEXT NULL,
            changed_at TEXT NOT NULL
        )""")
        history_columns = {row["name"] for row in connection.execute("PRAGMA table_info(sandbox_change_history)").fetchall()}
        if "actor_identity" not in history_columns:
            connection.execute("ALTER TABLE sandbox_change_history ADD COLUMN actor_identity TEXT NULL")
        if "result" not in history_columns:
            connection.execute("ALTER TABLE sandbox_change_history ADD COLUMN result TEXT NOT NULL DEFAULT 'SUCCESS'")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_sandbox_change_history_entity ON sandbox_change_history(entity_type, entity_id, id DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_sandbox_change_history_time ON sandbox_change_history(changed_at DESC, id DESC)")
        connection.execute("""CREATE TABLE IF NOT EXISTS candidate_requests (
            candidate_request_id TEXT PRIMARY KEY,
            external_reference TEXT NOT NULL UNIQUE COLLATE NOCASE,
            payload_json TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('PENDING', 'ACCEPTED', 'REJECTED')),
            revision INTEGER NOT NULL DEFAULT 1,
            employee_id TEXT NULL UNIQUE,
            decision_reason TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decided_at TEXT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS candidate_request_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_request_id TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(candidate_request_id) REFERENCES candidate_requests(candidate_request_id) ON DELETE RESTRICT
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_candidate_requests_status ON candidate_requests(status, updated_at)")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        samples = [
            ("NV001", "Nguyễn An", "nguyen.an@hrm-sandbox.test", "0901000001", "TECH", "Kỹ thuật", "Kỹ sư Backend", "ACTIVE", now),
            ("NV002", "Trần Bình", "tran.binh@hrm-sandbox.test", "0901000002", "OPS", "Vận hành", "Chuyên viên vận hành", "ACTIVE", now),
            ("NV003", "Lê Chi", "le.chi@hrm-sandbox.test", "0901000003", "DATA", "Dữ liệu", "Chuyên viên dữ liệu", "ACTIVE", now),
            ("NV004", "Phạm Dũng", "pham.dung@hrm-sandbox.test", "0901000004", "HR", "Nhân sự", "Chuyên viên tuyển dụng", "ACTIVE", now),
            ("NV005", "Vũ Hà", "vu.ha@hrm-sandbox.test", "0901000005", "FIN", "Tài chính", "Kế toán viên", "ACTIVE", now),
            ("NV006", "Đỗ Huy", "do.huy@hrm-sandbox.test", "0901000006", "OPS", "Vận hành", "Kỹ sư QA", "INACTIVE", now),
            ("NV007", "Bùi Lan", "bui.lan@hrm-sandbox.test", "0901000007", "OPS", "Vận hành", "Điều phối viên", "ACTIVE", now),
            ("NV008", "Ngô Minh", "ngo.minh@hrm-sandbox.test", "0901000008", "DATA", "Dữ liệu", "Chuyên viên phân tích", "ACTIVE", now),
            ("NV009", "Dương Nam", "duong.nam@hrm-sandbox.test", "0901000009", "HR", "Nhân sự", "Chuyên viên C&B", "INACTIVE", now),
            ("NV010", "Lý Oanh", "ly.oanh@hrm-sandbox.test", "0901000010", "FIN", "Tài chính", "Chuyên viên tài chính", "ACTIVE", now),
            ("NV011", "Trịnh Phúc", "trinh.phuc@hrm-sandbox.test", "0901000011", "DATA", "Dữ liệu", "Kỹ sư Frontend", "ACTIVE", now),
            ("NV012", "Mai Quỳnh", "mai.quynh@hrm-sandbox.test", "0901000012", "OPS", "Vận hành", "Chuyên viên hỗ trợ", "ACTIVE", now),
            ("NV013", "Cao Sơn", "cao.son@hrm-sandbox.test", "0901000013", "DATA", "Dữ liệu", "Kỹ sư dữ liệu", "ACTIVE", now),
            ("NV014", "Hồ Trang", "ho.trang@hrm-sandbox.test", "0901000014", "HR", "Nhân sự", "Chuyên viên đào tạo", "ACTIVE", now),
            ("NV015", "Đặng Uyên", "dang.uyen@hrm-sandbox.test", "0901000015", "FIN", "Tài chính", "Chuyên viên công nợ", "INACTIVE", now),
            ("NV016", "Phan Việt", "phan.viet@hrm-sandbox.test", "0901000016", "OPS", "Vận hành", "Kỹ sư hệ thống", "ACTIVE", now),
            ("NV017", "Hà Xuân", "ha.xuan@hrm-sandbox.test", "0901000017", "OPS", "Vận hành", "Giám sát vận hành", "ACTIVE", now),
            ("NV018", "Tạ Yến", "ta.yen@hrm-sandbox.test", "0901000018", "DATA", "Dữ liệu", "Chuyên viên báo cáo", "ACTIVE", now),
        ]
        connection.executemany(
            """INSERT OR IGNORE INTO sandbox_employees (
                employee_id, full_name, work_email, phone, department_code,
                department_name, job_title, employment_status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            samples,
        )
        connection.execute(
            """INSERT OR IGNORE INTO sandbox_departments (department_code, department_name, is_active, created_at, updated_at)
               SELECT department_code, COALESCE(NULLIF(TRIM(department_name), ''), department_code), 1,
                      MIN(updated_at), MAX(updated_at)
               FROM sandbox_employees
               WHERE department_code IS NOT NULL AND TRIM(department_code) <> ''
               GROUP BY department_code"""
        )
        duplicate_email = connection.execute(
            """SELECT 1 FROM sandbox_employees WHERE work_email IS NOT NULL AND TRIM(work_email) <> ''
               GROUP BY LOWER(TRIM(work_email)) HAVING COUNT(*) > 1 LIMIT 1"""
        ).fetchone()
        if not duplicate_email:
            connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_sandbox_employees_work_email
                   ON sandbox_employees(LOWER(TRIM(work_email)))
                   WHERE work_email IS NOT NULL AND TRIM(work_email) <> ''"""
            )
        connection.commit()
    finally:
        connection.close()


def _authorization_key(authorization: str | None) -> str:
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not supplied:
        raise HTTPException(status_code=401, detail="Không xác thực được với HRM Sandbox.")
    return supplied


def require_api_key(authorization: str | None = Header(default=None)) -> str:
    """Allow either scoped key on read-only integration endpoints."""
    service_key = _load_api_key()
    admin_key = _load_admin_api_key()
    if not service_key or not admin_key:
        raise HTTPException(status_code=503, detail="HRM Sandbox chưa cấu hình đủ khóa service và quản trị.")
    if hmac.compare_digest(service_key, admin_key):
        raise HTTPException(status_code=503, detail="Khóa service và quản trị phải khác nhau.")
    supplied = _authorization_key(authorization)
    if hmac.compare_digest(supplied, service_key):
        return SERVICE_PRINCIPAL
    if hmac.compare_digest(supplied, admin_key):
        return ADMIN_PRINCIPAL
    raise HTTPException(status_code=401, detail="Không xác thực được với HRM Sandbox.")


def require_service_api_key(authorization: str | None = Header(default=None)) -> None:
    service_key = _load_api_key()
    admin_key = _load_admin_api_key()
    if not service_key or not admin_key:
        raise HTTPException(status_code=503, detail="HRM Sandbox chưa cấu hình đủ khóa service và quản trị.")
    if hmac.compare_digest(service_key, admin_key):
        raise HTTPException(status_code=503, detail="Khóa service và quản trị phải khác nhau.")
    supplied = _authorization_key(authorization)
    if hmac.compare_digest(supplied, service_key):
        return
    if hmac.compare_digest(supplied, admin_key):
        raise HTTPException(status_code=403, detail="Khóa quản trị không dùng cho API gửi đề xuất từ IMS.")
    raise HTTPException(status_code=401, detail="Không xác thực được với HRM Sandbox.")


def require_admin_api_key(authorization: str | None = Header(default=None)) -> str:
    service_key = _load_api_key()
    admin_key = _load_admin_api_key()
    if not service_key or not admin_key:
        raise HTTPException(status_code=503, detail="HRM Sandbox chưa cấu hình đủ khóa service và quản trị.")
    if hmac.compare_digest(service_key, admin_key):
        raise HTTPException(status_code=503, detail="Khóa service và quản trị phải khác nhau.")
    supplied = _authorization_key(authorization)
    if hmac.compare_digest(supplied, admin_key):
        return ADMIN_PRINCIPAL
    if hmac.compare_digest(supplied, service_key):
        raise HTTPException(status_code=403, detail="Thao tác này cần khóa quản trị Sandbox; khóa IMS chỉ có quyền tích hợp giới hạn.")
    raise HTTPException(status_code=401, detail="Không xác thực được với HRM Sandbox.")


app = FastAPI(title="HRM Sandbox", version="1.0.0", docs_url=None, redoc_url=None)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    )
    if request.url.path.startswith("/api/v1/changes"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/", response_class=HTMLResponse)
def sandbox_console():
    """Serve the local HRM management console; no credential is embedded in the page."""
    page = Path(__file__).with_name("hrm_sandbox_console.html").read_text(encoding="utf-8")
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})

@app.on_event("startup")
def on_startup() -> None:
    if not _load_api_key() or not _load_admin_api_key():
        raise RuntimeError("HRM_SANDBOX_API_KEY and HRM_SANDBOX_ADMIN_API_KEY must both be configured.")
    if hmac.compare_digest(_load_api_key(), _load_admin_api_key()):
        raise RuntimeError("HRM Sandbox service and admin keys must be different.")
    initialize_database()


@app.get("/api/v1/health", dependencies=[Depends(require_api_key)])
def health():
    return {"status": "ok", "provider_id": "sandbox", "version": app.version}


@app.get("/api/v1/employees", dependencies=[Depends(require_api_key)])
def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=MAX_PAGE_SIZE),
    q: str | None = Query(default=None, max_length=100),
    department_code: str | None = Query(default=None, max_length=32),
    employment_status: Literal["ACTIVE", "INACTIVE"] | None = Query(default=None),
):
    connection = _connect()
    try:
        conditions = []
        params: list = []
        if isinstance(q, str) and q.strip():
            term = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
            conditions.append("(employee_id LIKE ? ESCAPE '\\' OR full_name LIKE ? ESCAPE '\\' OR work_email LIKE ? ESCAPE '\\' OR job_title LIKE ? ESCAPE '\\')")
            params.extend([term] * 4)
        if isinstance(department_code, str) and department_code:
            conditions.append("department_code = ?")
            params.append(department_code.strip())
        if employment_status in {"ACTIVE", "INACTIVE"}:
            conditions.append("employment_status = ?")
            params.append(employment_status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = int(connection.execute(f"SELECT COUNT(*) FROM sandbox_employees {where}", params).fetchone()[0])
        rows = connection.execute(
            f"SELECT {', '.join(EMPLOYEE_FIELDS)} FROM sandbox_employees {where} "
            "ORDER BY employee_id LIMIT ? OFFSET ?",
            (*params, page_size, (page - 1) * page_size),
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


@app.post("/api/v1/employees", response_model=SandboxEmployee, status_code=201)
def create_employee(employee: SandboxEmployeeCreate, actor_identity: str = Depends(require_admin_api_key)):
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM sandbox_employees WHERE employee_id = ?", (employee.employee_id,)).fetchone():
            raise HTTPException(status_code=409, detail="Employee ID đã tồn tại; mã nhân viên là định danh ổn định và không được dùng lại.")
        _check_employee_email(connection, employee.work_email)
        department = _get_active_department(connection, employee.department_code)
        now = _timestamp()
        values = {
            "employee_id": employee.employee_id,
            "full_name": employee.full_name,
            "work_email": employee.work_email,
            "phone": employee.phone,
            "department_code": department["department_code"] if department else None,
            "department_name": department["department_name"] if department else None,
            "job_title": employee.job_title,
            "employment_status": employee.employment_status,
            "updated_at": now,
        }
        validated = SandboxEmployee.model_validate(values)
        connection.execute(
            f"INSERT INTO sandbox_employees ({', '.join(EMPLOYEE_FIELDS)}) VALUES ({', '.join('?' for _ in EMPLOYEE_FIELDS)})",
            tuple(values[field] for field in EMPLOYEE_FIELDS),
        )
        _record_change(connection, "EMPLOYEE", employee.employee_id, "CREATE", None, values,
                       "Tạo hồ sơ từ HRM Sandbox.", actor_identity)
        connection.commit()
        return validated
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise HTTPException(status_code=409, detail="Employee ID hoặc email công việc đã tồn tại.") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@app.get("/api/v1/departments", dependencies=[Depends(require_api_key)])
def list_departments(include_inactive: bool = Query(default=True)):
    connection = _connect()
    try:
        where = "WHERE d.is_active = 1" if not include_inactive else ""
        rows = connection.execute(
            f"""SELECT d.department_code, d.department_name, d.is_active, d.created_at, d.updated_at,
                       COUNT(e.employee_id) AS employee_count
                FROM sandbox_departments d LEFT JOIN sandbox_employees e ON e.department_code = d.department_code
                {where} GROUP BY d.department_code ORDER BY d.is_active DESC, d.department_name COLLATE NOCASE"""
        ).fetchall()
        return {"items": [dict(row) for row in rows], "total": len(rows)}
    finally:
        connection.close()


@app.post("/api/v1/departments", status_code=201)
def create_department(department: SandboxDepartmentCreate, actor_identity: str = Depends(require_admin_api_key)):
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM sandbox_departments WHERE department_code = ?", (department.department_code,)).fetchone():
            raise HTTPException(status_code=409, detail="Mã phòng ban đã tồn tại; hãy dùng mã khác.")
        now = _timestamp()
        values = {
            "department_code": department.department_code,
            "department_name": " ".join(department.department_name.split()),
            "is_active": 1,
            "created_at": now,
            "updated_at": now,
        }
        connection.execute(
            "INSERT INTO sandbox_departments (department_code, department_name, is_active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
            (values["department_code"], values["department_name"], now, now),
        )
        _record_change(connection, "DEPARTMENT", department.department_code, "CREATE", None, values,
                       "Tạo danh mục phòng ban.", actor_identity)
        connection.commit()
        return {**values, "employee_count": 0}
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise HTTPException(status_code=409, detail="Mã phòng ban đã tồn tại.") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@app.patch("/api/v1/departments/{department_code}")
def update_department(department_code: str, changes: SandboxDepartmentPatch,
                      actor_identity: str = Depends(require_admin_api_key)):
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute(
            "SELECT department_code, department_name, is_active, created_at, updated_at FROM sandbox_departments WHERE department_code = ?",
            (department_code,),
        ).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban. Tải lại danh mục để kiểm tra mã.")
        if current["updated_at"] != changes.expected_updated_at:
            raise HTTPException(status_code=409, detail="Phòng ban vừa được thay đổi ở nơi khác. Tải lại danh mục trước khi lưu.")
        new_code = changes.department_code or current["department_code"]
        new_name = " ".join((changes.department_name or current["department_name"]).split())
        is_active = current["is_active"] if changes.is_active is None else int(changes.is_active)
        if new_code == current["department_code"] and new_name == current["department_name"] and is_active == current["is_active"]:
            raise HTTPException(status_code=400, detail="Không có thay đổi để lưu.")
        code_changed = new_code.casefold() != current["department_code"].casefold()
        if code_changed and not changes.confirm_ims_mapping_impact:
            raise HTTPException(status_code=409, detail="Đổi mã có thể làm mất khớp ánh xạ phòng ban IMS. Hãy xác nhận cảnh báo rồi thử lại.")
        if code_changed and connection.execute("SELECT 1 FROM sandbox_departments WHERE department_code = ?", (new_code,)).fetchone():
            raise HTTPException(status_code=409, detail="Mã phòng ban mới đã được sử dụng.")
        assigned = connection.execute(
            "SELECT employee_id, full_name, department_code, department_name, updated_at FROM sandbox_employees WHERE department_code = ? ORDER BY employee_id",
            (current["department_code"],),
        ).fetchall()
        if not is_active and assigned:
            raise HTTPException(status_code=409, detail=f"Chưa thể ngừng phòng ban: còn {len(assigned)} nhân viên đang gán. Hãy chuyển họ sang phòng ban khác trước.")
        now = _timestamp()
        before_department = dict(current)
        after_department = {
            "department_code": new_code,
            "department_name": new_name,
            "is_active": is_active,
            "created_at": current["created_at"],
            "updated_at": now,
        }
        connection.execute(
            "UPDATE sandbox_departments SET department_code = ?, department_name = ?, is_active = ?, updated_at = ? WHERE department_code = ?",
            (new_code, new_name, is_active, now, current["department_code"]),
        )
        for employee in assigned:
            before_employee = dict(employee)
            after_employee = dict(employee)
            after_employee["department_code"] = new_code
            after_employee["department_name"] = new_name
            after_employee["updated_at"] = now
            connection.execute(
                "UPDATE sandbox_employees SET department_code = ?, department_name = ?, updated_at = ? WHERE employee_id = ?",
                (new_code, new_name, now, employee["employee_id"]),
            )
            _record_change(connection, "EMPLOYEE", employee["employee_id"], "UPDATE", before_employee, after_employee,
                           changes.reason or "Thông tin phòng ban được cập nhật trong danh mục HRM Sandbox.", actor_identity)
        _record_change(connection, "DEPARTMENT", new_code, "UPDATE", before_department, after_department,
                       changes.reason or ("Đổi mã phòng ban; cần rà soát lại mapping HRM → IMS." if code_changed else None),
                       actor_identity)
        connection.commit()
        result = {**after_department, "employee_count": len(assigned), "code_changed": code_changed}
        if code_changed:
            result["mapping_warning"] = "Mã phòng ban đã đổi. Mapping HRM → IMS dùng mã cũ sẽ không tự chuyển; Admin cần ánh xạ mã mới trong IMS và tạo preview lại."
        return result
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise HTTPException(status_code=409, detail="Mã phòng ban hoặc dữ liệu liên quan bị trùng. Tải lại danh mục rồi thử lại.") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@app.get("/api/v1/changes")
def list_changes(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=MAX_PAGE_SIZE),
    entity_type: Literal["EMPLOYEE", "DEPARTMENT"] | None = Query(default=None),
    entity_id: str | None = Query(default=None, max_length=128),
    q: str | None = Query(default=None, max_length=100),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    actor: Literal["sandbox_admin_api_key", "ims_service_api_key", "legacy_unknown"] | None = Query(default=None),
    action: Literal["CREATE", "UPDATE", "STATUS_CHANGE", "DEACTIVATE", "REACTIVATE"] | None = Query(default=None),
    _principal: str = Depends(require_admin_api_key),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    connection = _connect()
    try:
        conditions = []
        params: list = []
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        if entity_id:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        if q and q.strip():
            escaped = q.strip().replace("%", r"\%").replace("_", r"\_")
            conditions.append("(entity_id LIKE ? ESCAPE '\\' OR reason LIKE ? ESCAPE '\\')")
            params.extend([f"%{escaped}%"] * 2)
        if date_from:
            conditions.append("substr(changed_at, 1, 10) >= ?")
            params.append(date_from.isoformat())
        if date_to:
            conditions.append("substr(changed_at, 1, 10) <= ?")
            params.append(date_to.isoformat())
        if action in {"DEACTIVATE", "REACTIVATE"}:
            old_status, new_status = (
                ("ACTIVE", "INACTIVE") if action == "DEACTIVATE" else ("INACTIVE", "ACTIVE")
            )
            conditions.append(
                "(action = ? OR (entity_type = 'EMPLOYEE' AND action = 'UPDATE' "
                "AND json_extract(before_json, '$.employment_status') = ? "
                "AND json_extract(after_json, '$.employment_status') = ?))"
            )
            params.extend([action, old_status, new_status])
        elif action == "UPDATE":
            conditions.append(
                "action = 'UPDATE' AND NOT (entity_type = 'EMPLOYEE' "
                "AND json_extract(before_json, '$.employment_status') IS NOT NULL "
                "AND json_extract(after_json, '$.employment_status') IS NOT NULL "
                "AND json_extract(before_json, '$.employment_status') <> json_extract(after_json, '$.employment_status'))"
            )
        elif action:
            conditions.append("action = ?")
            params.append(action)
        if actor in {ADMIN_PRINCIPAL, SERVICE_PRINCIPAL}:
            conditions.append("actor_identity = ?")
            params.append(actor)
        elif actor == "legacy_unknown":
            conditions.append("actor_identity IS NULL")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = int(connection.execute(f"SELECT COUNT(*) FROM sandbox_change_history {where}", params).fetchone()[0])
        rows = connection.execute(
            f"SELECT id, entity_type, entity_id, action, before_json, after_json, reason, changed_at, actor_identity, result FROM sandbox_change_history {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
        items = [_audit_summary(dict(row)) for row in rows]
        return {"items": items, "total": total, "page": page, "page_size": page_size,
                "total_pages": max(1, (total + page_size - 1) // page_size)}
    finally:
        connection.close()


@app.get("/api/v1/changes/{event_id}")
def get_change_detail(event_id: int, show_sensitive: bool = Query(default=False),
                      _principal: str = Depends(require_admin_api_key)):
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT id, entity_type, entity_id, action, before_json, after_json, reason, changed_at, actor_identity, result "
            "FROM sandbox_change_history WHERE id = ?", (event_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy sự kiện lịch sử.")
        item = dict(row)
        before, after = _audit_snapshots(item)
        changes = []
        fields = AUDIT_FIELDS.get(item["entity_type"], {})
        for field, label in fields.items():
            old_value = before.get(field)
            new_value = after.get(field)
            if old_value == new_value:
                continue
            sensitive = field in SENSITIVE_AUDIT_FIELDS
            changes.append({
                "field": field,
                "label": label,
                "before": _audit_display_value(field, old_value, show_sensitive),
                "after": _audit_display_value(field, new_value, show_sensitive),
                "sensitive": sensitive,
            })
        summary = _audit_summary(item)
        return {**summary, "changes": changes, "sensitive_values_visible": show_sensitive}
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


EMPLOYEE_FIELDS = (
    "employee_id", "full_name", "work_email", "phone", "department_code",
    "department_name", "job_title", "employment_status", "updated_at",
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _serialize(value) -> str | None:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if value is not None else None


def _record_change(connection: sqlite3.Connection, entity_type: str, entity_id: str, action: str,
                   before: dict | None, after: dict | None, reason: str | None = None,
                   actor_identity: str | None = None) -> None:
    allowed = AUDIT_FIELDS.get(entity_type, {})
    before_data = {key: before[key] for key in allowed if before is not None and key in before}
    after_data = {key: after[key] for key in allowed if after is not None and key in after}
    changed_fields = [key for key in allowed if before_data.get(key) != after_data.get(key)]
    if action == "UPDATE" and not changed_fields:
        return
    if action == "UPDATE" and entity_type == "EMPLOYEE":
        old_status = before_data.get("employment_status")
        new_status = after_data.get("employment_status")
        if old_status != new_status and old_status is not None and new_status is not None:
            action = "DEACTIVATE" if new_status == "INACTIVE" else "REACTIVATE"
        elif old_status != new_status:
            action = "STATUS_CHANGE"
    stored_before = {key: before_data[key] for key in changed_fields if key in before_data} or None
    stored_after = {key: after_data[key] for key in changed_fields if key in after_data} or None
    connection.execute(
        """INSERT INTO sandbox_change_history
           (entity_type, entity_id, action, before_json, after_json, reason, changed_at, actor_identity, result)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'SUCCESS')""",
        (entity_type, entity_id, action, _serialize(stored_before), _serialize(stored_after),
         _safe_audit_reason(reason), _timestamp(), actor_identity),
    )


def _get_active_department(connection: sqlite3.Connection, department_code: str | None):
    if department_code is None:
        return None
    department = connection.execute(
        "SELECT department_code, department_name, is_active FROM sandbox_departments WHERE department_code = ?",
        (department_code,),
    ).fetchone()
    if not department:
        raise HTTPException(status_code=422, detail="Mã phòng ban chưa có trong danh mục HRM Sandbox. Hãy tạo phòng ban trước.")
    if not department["is_active"]:
        raise HTTPException(status_code=422, detail="Phòng ban đã ngừng sử dụng. Hãy kích hoạt lại hoặc chọn phòng ban đang hoạt động.")
    return department


def _check_employee_email(connection: sqlite3.Connection, email: str | None, employee_id: str | None = None) -> None:
    if not email:
        return
    existing = connection.execute(
        "SELECT employee_id FROM sandbox_employees WHERE LOWER(TRIM(work_email)) = LOWER(TRIM(?)) AND employee_id <> ? LIMIT 1",
        (email, employee_id or ""),
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Email công việc đã được một nhân viên khác sử dụng.")


def _audit_snapshots(item: dict) -> tuple[dict, dict]:
    before = json.loads(item["before_json"]) if item.get("before_json") else {}
    after = json.loads(item["after_json"]) if item.get("after_json") else {}
    allowed = AUDIT_FIELDS.get(item.get("entity_type"), {})
    return ({key: before[key] for key in allowed if key in before},
            {key: after[key] for key in allowed if key in after})


def _safe_audit_reason(reason: str | None) -> str | None:
    if not reason:
        return None
    safe = re.sub(r"(?i)\b(password|api[_-]?key|token|secret|authorization)\s*[:=]\s*\S+",
                  r"\1=[đã ẩn]", reason)
    safe = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [đã ẩn]", safe)
    safe = re.sub(r"(?i)\b(?:mysql|postgres(?:ql)?|sqlite)://\S+", "[kết nối đã ẩn]", safe)
    safe = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[email đã ẩn]", safe)
    safe = re.sub(r"(?<!\w)(?:\+?84|0)(?:[\s().-]*\d){8,10}(?!\w)", "[số điện thoại đã ẩn]", safe)
    safe = re.sub(r"(?<![A-Za-z0-9])[A-Za-z0-9_+/=-]{40,}(?![A-Za-z0-9])", "[mã dài đã ẩn]", safe)
    return safe[:500]


def _effective_audit_action(item: dict, before: dict, after: dict) -> str:
    action = item["action"]
    if action == "UPDATE" and item["entity_type"] == "EMPLOYEE":
        old_status, new_status = before.get("employment_status"), after.get("employment_status")
        if old_status != new_status and old_status is not None and new_status is not None:
            return "DEACTIVATE" if new_status == "INACTIVE" else "REACTIVATE"
        if old_status != new_status:
            return "STATUS_CHANGE"
    return action


def _audit_summary(item: dict) -> dict:
    before, after = _audit_snapshots(item)
    changed = [key for key in AUDIT_FIELDS.get(item["entity_type"], {})
               if before.get(key) != after.get(key)]
    action = _effective_audit_action(item, before, after)
    action_labels = {
        "CREATE": "Tạo mới", "UPDATE": "Cập nhật", "STATUS_CHANGE": "Đổi trạng thái",
        "DEACTIVATE": "Đánh dấu nghỉ việc", "REACTIVATE": "Kích hoạt lại",
    }
    return {
        "id": item["id"],
        "entity_type": item["entity_type"],
        "entity_label": "Nhân viên" if item["entity_type"] == "EMPLOYEE" else "Phòng ban",
        "entity_id": item["entity_id"],
        "action": action,
        "action_label": action_labels.get(action, "Thay đổi"),
        "actor_label": {ADMIN_PRINCIPAL: "Quản trị Sandbox", SERVICE_PRINCIPAL: "IMS service"}.get(
            item.get("actor_identity"), "Không ghi nhận (lịch sử cũ)"),
        "result": item.get("result") or "SUCCESS",
        "result_label": "Thành công",
        "reason": _safe_audit_reason(item.get("reason")),
        "changed_at": item["changed_at"],
        "changed_fields": [AUDIT_FIELDS[item["entity_type"]][key] for key in changed],
    }


def _audit_display_value(field: str, value, show_sensitive: bool):
    if value is None:
        return "Chưa có giá trị"
    if field == "employment_status":
        return "Đang làm việc" if value == "ACTIVE" else "Ngừng làm việc"
    if field == "is_active":
        return "Đang sử dụng" if value else "Ngừng sử dụng"
    if field in SENSITIVE_AUDIT_FIELDS and not show_sensitive:
        text = str(value)
        if field == "work_email" and "@" in text:
            local, domain = text.split("@", 1)
            return f"{local[:1]}{'•' * max(2, min(len(local) - 1, 6))}@{domain}"
        digits = re.sub(r"\D", "", text)
        return f"••••••{digits[-2:]}" if len(digits) >= 2 else "••••••"
    return str(value)


@app.patch("/api/v1/employees/{employee_id}", response_model=SandboxEmployee)
def update_employee(employee_id: str, changes: SandboxEmployeePatch,
                    actor_identity: str = Depends(require_admin_api_key)):
    updates = changes.model_dump(exclude_unset=True, exclude={"expected_updated_at", "reason"})
    if not updates:
        raise HTTPException(status_code=400, detail="Cần có ít nhất một trường thay đổi.")
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute(
            "SELECT employee_id, full_name, work_email, phone, department_code, department_name, "
            "job_title, employment_status, updated_at FROM sandbox_employees WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên trong HRM Sandbox.")
        if not changes.expected_updated_at:
            raise HTTPException(status_code=428, detail="Thiếu mã phiên bản. Tải lại hồ sơ rồi thử cập nhật lại.")
        if changes.expected_updated_at != current["updated_at"]:
            raise HTTPException(status_code=409, detail="Hồ sơ vừa được cập nhật ở nơi khác. Tải lại dữ liệu mới trước khi lưu.")
        if "department_name" in updates and "department_code" not in updates:
            raise HTTPException(status_code=422, detail="Hãy chọn phòng ban theo mã trong danh mục; không nhập tên phòng ban tự do.")
        candidate = dict(current)
        candidate.update(updates)
        if "department_code" in updates:
            department = _get_active_department(connection, candidate["department_code"])
            if department:
                if "department_name" in updates and updates["department_name"] != department["department_name"]:
                    raise HTTPException(status_code=422, detail="Tên phòng ban không khớp với mã đã chọn. Hãy tải lại danh mục.")
                candidate["department_code"] = department["department_code"]
                candidate["department_name"] = department["department_name"]
            else:
                candidate["department_name"] = None
        candidate["updated_at"] = _timestamp()
        validated = SandboxEmployee.model_validate(candidate)
        _check_employee_email(connection, validated.work_email, employee_id)
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
        _record_change(connection, "EMPLOYEE", employee_id, "UPDATE", dict(current), validated.model_dump(),
                       changes.reason, actor_identity)
        connection.commit()
        return validated
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise HTTPException(status_code=409, detail="Mã nhân viên hoặc email đã tồn tại. Kiểm tra lại danh sách rồi thử lại.") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _candidate_hash(payload: CandidateRequestPayload) -> tuple[dict, str]:
    data = payload.model_dump(mode="json")
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return data, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@app.post("/api/v1/candidate-requests", dependencies=[Depends(require_service_api_key)])
def submit_candidate_request(payload: CandidateRequestPayload):
    data, digest = _candidate_hash(payload)
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        current = connection.execute(
            "SELECT candidate_request_id, payload_hash, status, revision, employee_id, decision_reason "
            "FROM candidate_requests WHERE external_reference = ?", (payload.external_reference,),
        ).fetchone()
        if current and current["status"] == "ACCEPTED":
            connection.commit()
            return {"candidate_request_id": current["candidate_request_id"], "external_reference": payload.external_reference,
                    "status": "ACCEPTED", "revision": current["revision"], "employee_id": current["employee_id"], "created": False}
        if current and current["status"] == "PENDING" and current["payload_hash"] == digest:
            connection.commit()
            return {"candidate_request_id": current["candidate_request_id"], "external_reference": payload.external_reference,
                    "status": "PENDING", "revision": current["revision"], "employee_id": None, "created": False}
        if current:
            next_revision = int(current["revision"]) + 1
            connection.execute(
                "UPDATE candidate_requests SET payload_json = ?, payload_hash = ?, status = 'PENDING', revision = ?, "
                "decision_reason = NULL, updated_at = ?, decided_at = NULL WHERE candidate_request_id = ?",
                (json.dumps(data, ensure_ascii=False), digest, next_revision, now, current["candidate_request_id"]),
            )
            request_id = current["candidate_request_id"]
        else:
            next_revision = 1
            request_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO candidate_requests (candidate_request_id, external_reference, payload_json, payload_hash, status, revision, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?)",
                (request_id, payload.external_reference, json.dumps(data, ensure_ascii=False), digest, next_revision, now, now),
            )
        connection.execute(
            "INSERT INTO candidate_request_history (candidate_request_id, status, reason, created_at) VALUES (?, 'PENDING', NULL, ?)",
            (request_id, now),
        )
        connection.commit()
        return {"candidate_request_id": request_id, "external_reference": payload.external_reference,
                "status": "PENDING", "revision": next_revision, "employee_id": None, "created": current is None}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@app.get("/api/v1/candidate-requests", dependencies=[Depends(require_api_key)])
def list_candidate_requests(
    status_filter: Literal["PENDING", "ACCEPTED", "REJECTED"] | None = Query(default=None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
):
    connection = _connect()
    try:
        where = "WHERE status = ?" if status_filter else ""
        params: tuple = (status_filter,) if status_filter else ()
        total = int(connection.execute(f"SELECT COUNT(*) FROM candidate_requests {where}", params).fetchone()[0])
        rows = connection.execute(
            f"SELECT candidate_request_id, external_reference, payload_json, status, revision, employee_id, decision_reason, created_at, updated_at, decided_at "
            f"FROM candidate_requests {where} ORDER BY updated_at DESC, candidate_request_id LIMIT ? OFFSET ?",
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            items.append(item)
        return {"items": items, "total": total, "page": page, "page_size": page_size,
                "total_pages": max(1, (total + page_size - 1) // page_size)}
    finally:
        connection.close()


@app.get("/api/v1/candidate-requests/by-reference/{external_reference}", dependencies=[Depends(require_api_key)])
def get_candidate_request(external_reference: str):
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT candidate_request_id, external_reference, payload_json, status, revision, employee_id, decision_reason, created_at, updated_at, decided_at "
            "FROM candidate_requests WHERE external_reference = ?", (external_reference,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Candidate request not found.")
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        return item
    finally:
        connection.close()


@app.post("/api/v1/candidate-requests/by-reference/{external_reference}/decision")
def decide_candidate_request(external_reference: str, decision: CandidateRequestDecision,
                             actor_identity: str = Depends(require_api_key)):
    if decision.decision == "REJECT" and not decision.reason:
        raise HTTPException(status_code=422, detail="A reason is required when rejecting a candidate.")
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT candidate_request_id, status, employee_id, revision FROM candidate_requests WHERE external_reference = ?",
            (external_reference,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Candidate request not found.")
        requested_status = "ACCEPTED" if decision.decision == "ACCEPT" else "REJECTED"
        if row["status"] in {"ACCEPTED", "REJECTED"}:
            if row["status"] != requested_status:
                raise HTTPException(status_code=409, detail="This candidate request already has a different final decision.")
            connection.commit()
            return {"external_reference": external_reference, "candidate_request_id": row["candidate_request_id"],
                    "status": row["status"], "employee_id": row["employee_id"], "revision": row["revision"], "created": False}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        employee_id = None
        if requested_status == "ACCEPTED":
            candidate = connection.execute("SELECT payload_json FROM candidate_requests WHERE candidate_request_id = ?", (row["candidate_request_id"],)).fetchone()
            candidate_data = json.loads(candidate["payload_json"])
            latest = connection.execute(
                "SELECT COALESCE(MAX(CAST(SUBSTR(employee_id, 3) AS INTEGER)), 0) FROM sandbox_employees WHERE employee_id GLOB 'NV[0-9]*'"
            ).fetchone()[0]
            employee_id = f"NV{int(latest) + 1:03d}"
            connection.execute(
                "INSERT INTO sandbox_employees (employee_id, full_name, employment_status, updated_at) VALUES (?, ?, 'ACTIVE', ?)",
                (employee_id, candidate_data["full_name"], now),
            )
            _record_change(
                connection, "EMPLOYEE", employee_id, "CREATE", None,
                {
                    "employee_id": employee_id,
                    "full_name": candidate_data["full_name"],
                    "work_email": None,
                    "phone": None,
                    "department_code": None,
                    "department_name": None,
                    "job_title": None,
                    "employment_status": "ACTIVE",
                    "updated_at": now,
                    "source_candidate_reference": external_reference,
                },
                f"Tạo từ đề xuất tuyển dụng IMS {external_reference} đã được HRM chấp nhận.",
                actor_identity,
            )
        connection.execute(
            "UPDATE candidate_requests SET status = ?, employee_id = ?, decision_reason = ?, updated_at = ?, decided_at = ? "
            "WHERE candidate_request_id = ? AND status = 'PENDING'",
            (requested_status, employee_id, decision.reason, now, now, row["candidate_request_id"]),
        )
        connection.execute(
            "INSERT INTO candidate_request_history (candidate_request_id, status, reason, created_at) VALUES (?, ?, ?, ?)",
            (row["candidate_request_id"], requested_status, decision.reason, now),
        )
        connection.commit()
        return {"external_reference": external_reference, "candidate_request_id": row["candidate_request_id"],
                "status": requested_status, "employee_id": employee_id, "revision": row["revision"], "created": True}
    except HTTPException:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise
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
