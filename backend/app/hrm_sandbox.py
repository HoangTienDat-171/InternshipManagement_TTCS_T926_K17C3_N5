"""Local-only HRM Sandbox API backed by its own persistent SQLite database."""
from __future__ import annotations

import hmac
import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
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


@app.get("/", response_class=HTMLResponse)
def sandbox_console():
    """Small local console for HRM staff to review candidate drafts."""
    return HTMLResponse(r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HRM Sandbox · Hộp thư tuyển dụng</title>
<style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#172033;background:#f4f6fb}*{box-sizing:border-box}body{margin:0;padding:28px}main{max-width:1050px;margin:auto}.top,.card,.login{background:#fff;border:1px solid #dfe5f0;border-radius:16px;box-shadow:0 8px 26px #15234a0c}.top{padding:24px;margin-bottom:18px}.eyebrow{color:#5948de;font-size:12px;font-weight:800;letter-spacing:.12em}h1{margin:7px 0;font-size:26px}.muted{color:#65738b;line-height:1.5}.login{display:grid;grid-template-columns:1fr auto;gap:10px;padding:16px;margin-bottom:18px}.login label{grid-column:1/-1;font-weight:650}input,select,button{font:inherit;border-radius:9px}input,select{min-height:42px;padding:9px 11px;border:1px solid #cfd7e5;background:white;color:#172033;width:100%}button{min-height:40px;padding:8px 14px;border:1px solid #d6ddeb;background:#fff;color:#18233a;font-weight:650;cursor:pointer}button.primary{background:#5546e8;color:white;border-color:#5546e8}button.danger{color:#b42318;border-color:#f3c8c4}button:disabled{opacity:.55;cursor:wait}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:20px 0 12px}.toolbar h2{font-size:18px;margin:0}.toolbar select{width:auto;min-width:160px}.card{padding:18px;margin:12px 0}.card h3{margin:0 0 6px;font-size:17px}.meta{font-size:13px;color:#65738b}.programs{padding:11px 13px;margin:12px 0;background:#f2f5fb;border-radius:10px}.programs div{padding:4px 0}.actions{display:grid;grid-template-columns:minmax(180px,1fr) auto auto;gap:8px;align-items:center}.notice{padding:12px;border-radius:10px;background:#e8f8ef;color:#176b3a;margin:12px 0}.error{padding:12px;border-radius:10px;background:#fff0ef;color:#a42318;margin:12px 0}.empty{padding:30px;text-align:center;color:#65738b}.hidden{display:none!important}small{color:#65738b}@media(max-width:640px){body{padding:14px}.login{grid-template-columns:1fr}.login label{grid-column:auto}.toolbar{align-items:flex-start;flex-direction:column}.toolbar select{width:100%}.actions{grid-template-columns:1fr}.top{padding:18px}}
</style></head><body><main>
<header class="top"><div class="eyebrow">HRM SANDBOX · LOCAL DEMO</div><h1>Hộp thư đề xuất tuyển dụng</h1><div class="muted">Xem xét hồ sơ nháp do IMS gửi. Chấp nhận sẽ tạo nhân viên trong cơ sở dữ liệu Sandbox; từ chối cần ghi lý do. Dữ liệu này độc lập với IMS và MySQL.</div></header>
<form class="login" id="login"><label for="key">Sandbox API key</label><input id="key" type="password" autocomplete="off" required minlength="32" placeholder="Nhập key local đã cấu hình cho HRM Sandbox"><button class="primary">Kết nối</button></form>
<div id="message" aria-live="polite"></div><section id="inbox" class="hidden"><div class="toolbar"><h2>Hồ sơ đề xuất</h2><div><select id="filter" aria-label="Lọc trạng thái"><option value="PENDING">Đang chờ</option><option value="ACCEPTED">Đã chấp nhận</option><option value="REJECTED">Đã từ chối</option><option value="">Tất cả</option></select> <button id="refresh" type="button">Làm mới</button></div></div><div id="items"></div></section>
</main><script>
let apiKey='';const msg=document.querySelector('#message'),box=document.querySelector('#inbox'),items=document.querySelector('#items'),filter=document.querySelector('#filter');
function message(text,bad=false){msg.className=bad?'error':'notice';msg.textContent=text}
async function api(path,options={}){const response=await fetch('/api/v1/'+path,{...options,headers:{'Authorization':'Bearer '+apiKey,'Accept':'application/json','Content-Type':'application/json',...(options.headers||{})}});const body=await response.json().catch(()=>({}));if(!response.ok)throw new Error(body.detail||'HTTP '+response.status);return body}
function element(tag,text,cls){const node=document.createElement(tag);node.textContent=text;if(cls)node.className=cls;return node}
function render(data){items.replaceChildren();if(!data.items.length){items.append(element('div','Không có hồ sơ ở trạng thái này.','empty'));return}for(const item of data.items){const card=document.createElement('article');card.className='card';card.append(element('h3',item.payload.full_name));card.append(element('div',item.external_reference+' · revision '+item.revision+' · '+item.status,'meta'));card.append(element('div','Gửi lúc: '+new Date(item.created_at).toLocaleString('vi-VN')+(item.decided_at?' · Quyết định: '+new Date(item.decided_at).toLocaleString('vi-VN'):''),'meta'));const programs=document.createElement('div');programs.className='programs';programs.append(element('strong','Chương trình hoàn thành'));for(const p of item.payload.completed_programs||[]){const label=[p.program_name,p.start_date&&('Bắt đầu '+p.start_date),p.completion_date&&('Hoàn thành '+p.completion_date)].filter(Boolean).join(' · ');programs.append(element('div',label))}card.append(programs);if(item.decision_reason)card.append(element('div','Lý do: '+item.decision_reason,'meta'));if(item.status==='PENDING'){const actions=document.createElement('div');actions.className='actions';const reason=document.createElement('input');reason.maxLength=500;reason.placeholder='Lý do từ chối (bắt buộc khi từ chối)';reason.setAttribute('aria-label','Lý do từ chối');const accept=document.createElement('button');accept.className='primary';accept.textContent='Chấp nhận và tạo nhân viên';accept.onclick=()=>decide(item,'ACCEPT',reason);const reject=document.createElement('button');reject.className='danger';reject.textContent='Từ chối';reject.onclick=()=>decide(item,'REJECT',reason);actions.append(reason,accept,reject);card.append(actions)}else if(item.employee_id){card.append(element('strong','Mã nhân viên Sandbox: '+item.employee_id))}items.append(card)}}
async function load(){try{const q=filter.value?'?status='+encodeURIComponent(filter.value)+'&page=1&page_size=100':'?page=1&page_size=100';const data=await api('candidate-requests'+q);render(data);box.classList.remove('hidden');message('Đã kết nối · '+data.total+' hồ sơ trong hộp thư.')}catch(error){message(error.message,true);box.classList.add('hidden')}}
async function decide(item,decision,reasonInput){const reason=reasonInput.value.trim();if(decision==='REJECT'&&!reason){message('Nhập lý do trước khi từ chối.',true);reasonInput.focus();return}if(decision==='ACCEPT'&&!confirm('Chấp nhận hồ sơ nháp và tạo nhân viên trong HRM Sandbox?'))return;try{const result=await api('candidate-requests/by-reference/'+encodeURIComponent(item.external_reference)+'/decision',{method:'POST',body:JSON.stringify({decision,reason:reason||null})});message(result.status==='ACCEPTED'?'Đã chấp nhận · mã nhân viên '+result.employee_id:'Đã từ chối và lưu lý do.');await load()}catch(error){message(error.message,true)}}
document.querySelector('#login').addEventListener('submit',async e=>{e.preventDefault();apiKey=document.querySelector('#key').value.trim();try{await api('health');document.querySelector('#key').value='';await load()}catch(error){apiKey='';message(error.message,true)}});document.querySelector('#refresh').addEventListener('click',load);filter.addEventListener('change',load);
</script></body></html>""")


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


def _candidate_hash(payload: CandidateRequestPayload) -> tuple[dict, str]:
    data = payload.model_dump(mode="json")
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return data, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@app.post("/api/v1/candidate-requests", dependencies=[Depends(require_api_key)])
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


@app.post("/api/v1/candidate-requests/by-reference/{external_reference}/decision", dependencies=[Depends(require_api_key)])
def decide_candidate_request(external_reference: str, decision: CandidateRequestDecision):
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
