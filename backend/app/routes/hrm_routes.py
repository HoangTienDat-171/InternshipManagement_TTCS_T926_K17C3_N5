"""Admin-only HRM Sandbox connection, preview, mapping, and apply workflow."""
from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import database
from ..database import get_db
from ..hrm_integration import HRM_SETUP_REQUIREMENTS, HRM_SYNC_SCOPE, HRM_EXCLUDED_SCOPE
from ..hrm_provider import HRMProviderError, configured_provider, get_sandbox_config
from .. import hrm_outbound
from ..hrm_storage import (
    PROVIDER_ID,
    acquire_sync_lock,
    apply_rows_and_history,
    department_mapping_data,
    hrm_schema_ready,
    list_directory,
    list_history,
    load_sync_context,
    parse_timestamp,
    persist_preview,
    preview_rows,
    read_preview,
    record_failed_sync,
    release_sync_lock,
    snapshot_digest,
)
from ..security import require_role

router = APIRouter(prefix="/api/integrations/hrm", tags=["HRM Integration"])

CONNECTION_STATE: dict[str, Any] = {"state": "NOT_TESTED", "message": "Chưa kiểm tra kết nối trong phiên backend này."}


class DepartmentMappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    department_code: str = Field(min_length=1, max_length=128)
    ma_phong_ban: int = Field(ge=1)

    @field_validator("department_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class ApplySyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_id: str = Field(min_length=36, max_length=36)


class MentorMappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_employee_id: str = Field(min_length=1, max_length=128)
    ma_nguoi_dung: int = Field(ge=1)


class OutboundProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: int = Field(ge=1)


class OutboundPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=36, max_length=36)
    reason: str | None = Field(default=None, max_length=500)


class SandboxDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: str = Field(pattern=r"^(ACCEPT|REJECT)$")
    reason: str | None = Field(default=None, max_length=500)


def _require_admin(request: Request):
    return require_role(request, "Admin")


def _require_hr(request: Request):
    return require_role(request, "HR")


def _require_hr_or_admin(request: Request):
    return require_role(request, "HR", "Admin")


def _require_outbound_test(request: Request, db) -> None:
    _require_schema(db)
    if not hrm_outbound.outbound_enabled():
        raise HTTPException(status_code=503, detail="Outbound candidate staging is enabled only for the isolated SQLite UAT runtime.")
    provider = _provider_or_error()
    if provider.provider_id != "sandbox":
        raise HTTPException(status_code=503, detail="Outbound candidate staging is available only for HRM Sandbox.")


def _require_schema(db) -> None:
    if not hrm_schema_ready(db):
        raise HTTPException(
            status_code=503,
            detail="Chưa có schema HRM trên database IMS này. Hãy áp dụng migration US37 cho database thử nghiệm.",
        )


def _provider_or_error():
    provider, configuration_error = configured_provider()
    if configuration_error:
        raise HTTPException(status_code=503, detail=configuration_error)
    if provider is None:
        raise HTTPException(status_code=503, detail="HRM Sandbox chưa được cấu hình. Hãy đặt HRM_PROVIDER, HRM_SANDBOX_BASE_URL và HRM_SANDBOX_API_KEY.")
    return provider


def _safe_failure(exc: HRMProviderError) -> HTTPException:
    CONNECTION_STATE.update(state="ERROR", message=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/status")
def get_status(request: Request, db=Depends(get_db)):
    _require_admin(request)
    config, configuration_error = get_sandbox_config()
    status: dict[str, Any] = {
        "state": "NOT_CONFIGURED",
        "configured": False,
        "provider_name": None,
        "endpoint": None,
        "connection_state": "NOT_TESTED",
        "can_test_connection": False,
        "can_preview": False,
        "can_sync": False,
        "sync_history_available": False,
        "missing_requirements": list(HRM_SETUP_REQUIREMENTS),
        "sync_scope": list(HRM_SYNC_SCOPE),
        "excluded_scope": list(HRM_EXCLUDED_SCOPE),
        "message": "Cấu hình HRM Sandbox qua biến môi trường để bắt đầu kiểm thử.",
    }
    if configuration_error:
        status.update(state="ERROR", message=configuration_error)
        return status
    if config is None:
        return status

    status.update(
        state=CONNECTION_STATE["state"],
        configured=True,
        provider_name="HRM Sandbox",
        endpoint=config.display_endpoint,
        connection_state=CONNECTION_STATE["state"],
        can_test_connection=True,
        missing_requirements=[],
        message=CONNECTION_STATE["message"],
    )
    try:
        schema_ready = hrm_schema_ready(db) if database.DATABASE_BACKEND == "mysql" else hrm_schema_ready(db)
    except Exception:
        schema_ready = False
    status.update(
        can_preview=schema_ready,
        can_sync=schema_ready,
        sync_history_available=schema_ready,
    )
    if not schema_ready:
        status.update(
            state="SCHEMA_REQUIRED",
            message="HRM Sandbox đã cấu hình; database IMS cần migration US37 trước khi xem trước/đồng bộ.",
            missing_requirements=["Áp dụng migrations/20261015_us37_hrm_sandbox.sql trên database IMS thử nghiệm."],
        )
    return status


@router.post("/test-connection")
async def test_connection(request: Request):
    _require_admin(request)
    provider = _provider_or_error()
    try:
        await provider.test_connection()
    except HRMProviderError as exc:
        raise _safe_failure(exc)
    CONNECTION_STATE.update(state="CONNECTED", message="Đã kết nối HRM Sandbox thành công.")
    config, _ = get_sandbox_config()
    return {
        "state": "CONNECTED",
        "provider_name": provider.provider_name,
        "endpoint": config.display_endpoint if config else None,
        "message": CONNECTION_STATE["message"],
    }


@router.get("/department-mappings")
async def get_department_mappings(request: Request, db=Depends(get_db)):
    _require_admin(request)
    _require_schema(db)
    provider = _provider_or_error()
    try:
        records = await provider.fetch_employees()
    except HRMProviderError as exc:
        raise _safe_failure(exc)
    return department_mapping_data(db, records)


@router.put("/department-mappings")
async def save_department_mapping(
    payload: DepartmentMappingRequest,
    request: Request,
    db=Depends(get_db),
):
    _require_admin(request)
    _require_schema(db)
    provider = _provider_or_error()
    try:
        records = await provider.fetch_employees()
    except HRMProviderError as exc:
        raise _safe_failure(exc)
    known_codes = {str(row.get("department_code") or "").strip().upper() for row in records}
    if payload.department_code not in known_codes:
        raise HTTPException(status_code=422, detail="Mã phòng ban không có trong danh mục HRM Sandbox hiện tại.")
    department = db.execute(
        "SELECT ma_phong_ban FROM PHONG_BAN WHERE ma_phong_ban = ?",
        (payload.ma_phong_ban,),
    ).fetchone()
    if not department:
        raise HTTPException(status_code=422, detail="Phòng ban IMS được chọn không tồn tại.")
    db.execute(
        """INSERT INTO HRM_DEPARTMENT_MAPPINGS (
               provider_id, external_department_key, external_department_code, ma_phong_ban
           ) VALUES (?, ?, ?, ?)
           ON CONFLICT(provider_id, external_department_key) DO UPDATE SET
               external_department_code = excluded.external_department_code,
               ma_phong_ban = excluded.ma_phong_ban""",
        (PROVIDER_ID, payload.department_code.casefold(), payload.department_code, payload.ma_phong_ban),
    )
    db.commit()
    CONNECTION_STATE.update(state="CONNECTED", message="Đã lưu ánh xạ phòng ban HRM → IMS.")
    return {"saved": True, "department_code": payload.department_code, "ma_phong_ban": payload.ma_phong_ban}


@router.get("/mentor-mappings")
async def get_mentor_mappings(request: Request, db=Depends(get_db)):
    _require_admin(request)
    _require_schema(db)
    provider = _provider_or_error()
    try:
        records = await provider.fetch_employees()
    except HRMProviderError as exc:
        raise _safe_failure(exc)
    mentors = db.execute(
        "SELECT ma_nguoi_dung, ho_ten, email, so_dien_thoai, ma_phong_ban "
        "FROM NGUOI_DUNG WHERE vai_tro = 'Mentor' ORDER BY ho_ten, ma_nguoi_dung"
    ).fetchall()
    links = {row["external_employee_key"].casefold(): dict(row) for row in db.execute(
        "SELECT external_employee_key, external_employee_id, ma_nguoi_dung, approved_by, approved_at "
        "FROM HRM_MENTOR_LINKS WHERE provider_id = ?", (PROVIDER_ID,),
    ).fetchall()}
    by_email: dict[str, list[int]] = {}
    for mentor in mentors:
        email = str(mentor["email"] or "").strip().casefold()
        if email:
            by_email.setdefault(email, []).append(int(mentor["ma_nguoi_dung"]))
    rows = []
    for employee in records:
        external_id = str(employee.get("external_employee_id") or "")
        link = links.get(external_id.casefold())
        suggestions = by_email.get(str(employee.get("work_email") or "").strip().casefold(), [])
        rows.append({
            "external_employee_id": external_id,
            "full_name": employee.get("full_name"),
            "work_email": employee.get("work_email"),
            "linked_user_id": link["ma_nguoi_dung"] if link else None,
            "linked_at": link["approved_at"] if link else None,
            "email_suggestion_user_id": suggestions[0] if len(suggestions) == 1 else None,
            "email_suggestion_count": len(suggestions),
        })
    return {"employees": rows, "mentors": [dict(row) for row in mentors]}


@router.put("/mentor-mappings")
async def save_mentor_mapping(payload: MentorMappingRequest, request: Request, db=Depends(get_db)):
    actor = _require_admin(request)
    _require_schema(db)
    provider = _provider_or_error()
    try:
        records = await provider.fetch_employees()
    except HRMProviderError as exc:
        raise _safe_failure(exc)
    source = [row for row in records if str(row.get("external_employee_id") or "").casefold() == payload.external_employee_id.casefold()]
    if len(source) != 1:
        raise HTTPException(status_code=422, detail="HRM external employee ID was not found uniquely in the current Sandbox directory.")
    mentor = db.execute(
        "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE ma_nguoi_dung = ? AND vai_tro = 'Mentor'",
        (payload.ma_nguoi_dung,),
    ).fetchone()
    if not mentor:
        raise HTTPException(status_code=422, detail="The selected IMS account is not a Mentor.")
    external_key = payload.external_employee_id.casefold()
    existing_external = db.execute(
        "SELECT ma_nguoi_dung FROM HRM_MENTOR_LINKS WHERE provider_id = ? AND external_employee_key = ?",
        (PROVIDER_ID, external_key),
    ).fetchone()
    if existing_external:
        if int(existing_external["ma_nguoi_dung"]) == payload.ma_nguoi_dung:
            return {"saved": True, "already_linked": True}
        raise HTTPException(status_code=409, detail="This HRM employee is already linked to another IMS Mentor.")
    existing_mentor = db.execute(
        "SELECT external_employee_id FROM HRM_MENTOR_LINKS WHERE provider_id = ? AND ma_nguoi_dung = ?",
        (PROVIDER_ID, payload.ma_nguoi_dung),
    ).fetchone()
    if existing_mentor:
        raise HTTPException(status_code=409, detail="This IMS Mentor is already linked to another HRM employee.")
    try:
        db.execute(
            "INSERT INTO HRM_MENTOR_LINKS (provider_id, external_employee_key, external_employee_id, ma_nguoi_dung, approved_by, approved_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (PROVIDER_ID, external_key, payload.external_employee_id, payload.ma_nguoi_dung,
             int(actor["ma_nguoi_dung"]), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="The HRM employee or IMS Mentor was linked concurrently; refresh and review the mapping.") from exc
    CONNECTION_STATE.update(state="CONNECTED", message="An Admin explicitly approved an HRM external-ID to Mentor mapping.")
    return {"saved": True, "already_linked": False}


@router.get("/outbound/status")
def get_outbound_status(request: Request, db=Depends(get_db)):
    _require_hr_or_admin(request)
    enabled = hrm_outbound.outbound_enabled() and hrm_schema_ready(db)
    return {
        "enabled": enabled,
        "provider": "HRM Sandbox",
        "environment": "isolated SQLite UAT" if enabled else "disabled",
        "message": "Only explicitly completed internship participation is eligible. HR approval is required; Sandbox acceptance creates an employee." if enabled else "Outbound is disabled outside the isolated SQLite UAT runtime.",
    }


@router.get("/outbound/candidates")
def get_outbound_candidates(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    _require_hr_or_admin(request)
    _require_outbound_test(request, db)
    return hrm_outbound.list_candidates(db, page, page_size)


@router.post("/outbound/preview")
def preview_outbound_candidate(payload: OutboundProfileRequest, request: Request, db=Depends(get_db)):
    actor = _require_hr(request)
    _require_outbound_test(request, db)
    provider = _provider_or_error()
    try:
        result = hrm_outbound.create_preview(db, int(actor["ma_nguoi_dung"]), payload.profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["provider_name"] = provider.provider_name
    return result


@router.post("/outbound/approve")
def approve_outbound_candidate(payload: OutboundPreviewRequest, request: Request, db=Depends(get_db)):
    actor = _require_hr(request)
    _require_outbound_test(request, db)
    preview = hrm_outbound.read_outbound_preview(db, payload.preview_id)
    if not preview:
        raise HTTPException(status_code=404, detail="Outbound preview was not found.")
    if int(preview["actor_user_id"]) != int(actor["ma_nguoi_dung"]):
        raise HTTPException(status_code=403, detail="Only the HR account that created this preview may approve it.")
    if preview["status"] != "PENDING":
        raise HTTPException(status_code=409, detail="This preview is no longer pending approval.")
    if hrm_outbound.is_preview_expired(preview):
        db.execute("UPDATE HRM_OUTBOUND_PREVIEWS SET status = 'EXPIRED' WHERE preview_id = ? AND status = 'PENDING'", (payload.preview_id,))
        db.commit()
        raise HTTPException(status_code=409, detail="The preview expired; create a new one.")
    current_payload, reason = hrm_outbound.build_candidate_payload(db, int(preview["ma_ho_so"]))
    if current_payload is None or not hmac.compare_digest(preview["snapshot_hash"], hrm_outbound.payload_digest(current_payload)):
        db.execute("UPDATE HRM_OUTBOUND_PREVIEWS SET status = 'STALE' WHERE preview_id = ?", (payload.preview_id,))
        db.commit()
        raise HTTPException(status_code=409, detail=reason or "Candidate data changed after preview; create a new preview.")
    try:
        hrm_outbound.approve_preview(db, preview, int(actor["ma_nguoi_dung"]), payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "HR_APPROVED", "preview_id": payload.preview_id, "message": "HR hiring decision and data-transfer approval recorded."}


@router.post("/outbound/send")
async def send_outbound_candidate(payload: OutboundPreviewRequest, request: Request, db=Depends(get_db)):
    actor = _require_hr(request)
    _require_outbound_test(request, db)
    provider = _provider_or_error()
    preview = hrm_outbound.read_outbound_preview(db, payload.preview_id)
    if not preview:
        raise HTTPException(status_code=404, detail="Outbound preview was not found.")
    if int(preview["actor_user_id"]) != int(actor["ma_nguoi_dung"]):
        raise HTTPException(status_code=403, detail="Only the HR account that approved this preview may send it.")
    if preview["status"] != "APPROVED":
        raise HTTPException(status_code=409, detail="HR must approve the preview before sending it.")
    if hrm_outbound.is_preview_expired(preview):
        db.execute("UPDATE HRM_OUTBOUND_PREVIEWS SET status = 'EXPIRED' WHERE preview_id = ? AND status = 'APPROVED'", (payload.preview_id,))
        db.commit()
        raise HTTPException(status_code=409, detail="The preview expired; create a new one.")
    decision = db.execute("SELECT decision_status FROM HRM_HIRING_DECISIONS WHERE ma_ho_so = ?", (int(preview["ma_ho_so"]),)).fetchone()
    if not decision or decision["decision_status"] != "APPROVED":
        raise HTTPException(status_code=403, detail="An explicit HR hiring decision is required before sending.")
    candidate, reason = hrm_outbound.build_candidate_payload(db, int(preview["ma_ho_so"]))
    if candidate is None or not hmac.compare_digest(preview["snapshot_hash"], hrm_outbound.payload_digest(candidate)):
        db.execute("UPDATE HRM_OUTBOUND_PREVIEWS SET status = 'STALE' WHERE preview_id = ?", (payload.preview_id,))
        db.commit()
        raise HTTPException(status_code=409, detail=reason or "Candidate data changed after approval; create a new preview.")
    existing_proposal = db.execute(
        "SELECT external_reference, status FROM HRM_OUTBOUND_PROPOSALS WHERE provider_id = ? AND ma_ho_so = ?",
        (PROVIDER_ID, int(preview["ma_ho_so"])),
    ).fetchone()
    if existing_proposal and existing_proposal["status"] not in {"REJECTED", "FAILED"}:
        raise HTTPException(
            status_code=409,
            detail="A prior request is pending, final, or awaiting reconciliation. Resolve it before another send.",
        )
    if existing_proposal and existing_proposal["external_reference"] != candidate["external_reference"]:
        raise HTTPException(status_code=409, detail="The existing Sandbox reference does not match this IMS profile.")
    try:
        await provider.test_connection()
        response = await provider.submit_candidate_request(candidate)
    except HRMProviderError as exc:
        if exc.uncertain:
            try:
                response = await provider.get_candidate_request(candidate["external_reference"])
            except HRMProviderError:
                response = None
            if response is None:
                hrm_outbound.save_proposal(db, int(actor["ma_nguoi_dung"]), int(preview["ma_ho_so"]),
                    candidate["external_reference"], "PENDING_RECONCILIATION", preview["snapshot_hash"], reason="Submission response was uncertain; lookup must resolve before another send.")
                return {"status": "PENDING_RECONCILIATION", "message": "Submission response was uncertain. The Sandbox will be checked by IMS reference before another send."}
        else:
            hrm_outbound.save_proposal(db, int(actor["ma_nguoi_dung"]), int(preview["ma_ho_so"]),
                candidate["external_reference"], "FAILED", preview["snapshot_hash"], reason="Sandbox rejected the request; review the current preview before retrying.")
            raise _safe_failure(exc)
    if not response or response.get("external_reference") != candidate["external_reference"]:
        hrm_outbound.save_proposal(db, int(actor["ma_nguoi_dung"]), int(preview["ma_ho_so"]),
            candidate["external_reference"], "PENDING_RECONCILIATION", preview["snapshot_hash"], reason="Sandbox response did not match the IMS reference.")
        return {"status": "PENDING_RECONCILIATION", "message": "The Sandbox response is being reconciled by IMS reference."}
    status = str(response.get("status") or "")
    if status not in {"PENDING", "ACCEPTED", "REJECTED"}:
        status = "PENDING_RECONCILIATION"
    hrm_outbound.save_proposal(db, int(actor["ma_nguoi_dung"]), int(preview["ma_ho_so"]),
        candidate["external_reference"], status, preview["snapshot_hash"],
        response.get("candidate_request_id"), response.get("employee_id"),
        response.get("decision_reason"))
    db.execute("UPDATE HRM_OUTBOUND_PREVIEWS SET status = 'SENT' WHERE preview_id = ?", (payload.preview_id,))
    db.commit()
    return {"status": status, "candidate_request_id": response.get("candidate_request_id"),
            "external_employee_id": response.get("employee_id"), "message": "Candidate request sent to the HRM Sandbox inbox."}


@router.get("/outbound/sandbox-inbox")
async def get_sandbox_candidate_inbox(request: Request, db=Depends(get_db)):
    _require_hr_or_admin(request)
    _require_outbound_test(request, db)
    provider = _provider_or_error()
    try:
        items = await provider.fetch_candidate_requests("PENDING")
    except HRMProviderError as exc:
        raise _safe_failure(exc)
    return {"items": items, "total": len(items)}


@router.post("/outbound/sandbox-inbox/{external_reference}/decision")
async def decide_sandbox_candidate(external_reference: str, payload: SandboxDecisionRequest, request: Request, db=Depends(get_db)):
    actor = _require_hr(request)
    _require_outbound_test(request, db)
    if payload.decision == "REJECT" and not (payload.reason or "").strip():
        raise HTTPException(status_code=422, detail="A rejection reason is required.")
    local = db.execute(
        "SELECT ma_ho_so, candidate_request_id, last_payload_hash FROM HRM_OUTBOUND_PROPOSALS "
        "WHERE provider_id = ? AND external_reference = ?", (PROVIDER_ID, external_reference),
    ).fetchone()
    if not local:
        raise HTTPException(status_code=404, detail="No IMS outbound proposal matches this candidate request.")
    provider = _provider_or_error()
    try:
        response = await provider.decide_candidate_request(external_reference, payload.decision, payload.reason)
    except HRMProviderError as exc:
        raise _safe_failure(exc)
    status = str(response.get("status") or "")
    if status not in {"ACCEPTED", "REJECTED"}:
        raise HTTPException(status_code=502, detail="Sandbox returned an invalid candidate decision.")
    hrm_outbound.save_proposal(db, int(actor["ma_nguoi_dung"]), int(local["ma_ho_so"]), external_reference,
        status, local["last_payload_hash"] or "", response.get("candidate_request_id"),
        response.get("employee_id"), payload.reason if status == "REJECTED" else None)
    return {"status": status, "external_employee_id": response.get("employee_id"), "message": "Sandbox candidate decision saved."}


@router.post("/outbound/reconcile/{profile_id}")
async def reconcile_outbound_candidate(profile_id: int, request: Request, db=Depends(get_db)):
    actor = _require_hr_or_admin(request)
    _require_outbound_test(request, db)
    local = db.execute(
        "SELECT external_reference, candidate_request_id, status, external_employee_id, last_payload_hash "
        "FROM HRM_OUTBOUND_PROPOSALS WHERE provider_id = ? AND ma_ho_so = ?",
        (PROVIDER_ID, profile_id),
    ).fetchone()
    if not local or local["status"] != "PENDING_RECONCILIATION":
        raise HTTPException(status_code=409, detail="This proposal does not need reconciliation.")
    provider = _provider_or_error()
    try:
        remote = await provider.get_candidate_request(local["external_reference"])
    except HRMProviderError as exc:
        raise _safe_failure(exc)
    if not remote:
        return {"status": "PENDING_RECONCILIATION", "found": False,
                "message": "No Sandbox record was found yet. Do not resend until this is resolved."}
    remote_status = str(remote.get("status") or "")
    if remote_status not in {"PENDING", "ACCEPTED", "REJECTED"}:
        raise HTTPException(status_code=502, detail="Sandbox returned an invalid reconciliation state.")
    if remote_status != local["status"] or remote.get("employee_id") != local["external_employee_id"]:
        hrm_outbound.save_proposal(db, int(actor["ma_nguoi_dung"]), profile_id,
            local["external_reference"], remote_status, local["last_payload_hash"] or "",
            remote.get("candidate_request_id"), remote.get("employee_id"), remote.get("decision_reason"))
    return {"status": remote_status, "found": True, "external_employee_id": remote.get("employee_id"),
            "message": "IMS proposal was reconciled with the Sandbox record."}


@router.get("/outbound/history")
def get_outbound_history(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    _require_hr_or_admin(request)
    _require_outbound_test(request, db)
    return hrm_outbound.list_history(db, page, page_size)


@router.post("/preview")
async def create_preview(request: Request, db=Depends(get_db)):
    actor = _require_admin(request)
    _require_schema(db)
    provider = _provider_or_error()
    try:
        await provider.test_connection()
        records = await provider.fetch_employees()
    except HRMProviderError as exc:
        raise _safe_failure(exc)
    context = load_sync_context(db, provider.provider_id)
    rows = preview_rows(records, context)
    digest = snapshot_digest(records, context, rows)
    saved = persist_preview(db, int(actor["ma_nguoi_dung"]), digest, provider.provider_id)
    counts = {action: sum(row["action"] == action for row in rows) for action in (
        "NEW", "UPDATE", "MENTOR_UPDATE", "MENTOR_DIRECTORY_UPDATE", "UNCHANGED", "MENTOR_UNCHANGED", "CONFLICT", "INVALID",
    )}
    CONNECTION_STATE.update(state="CONNECTED", message="Đã tạo bản xem trước từ dữ liệu HRM Sandbox.")
    return {
        **saved,
        "provider_name": provider.provider_name,
        "total": len(rows),
        "counts": counts,
        "rows": rows,
    }


@router.post("/apply")
async def apply_sync(payload: ApplySyncRequest, request: Request, db=Depends(get_db)):
    actor = _require_admin(request)
    _require_schema(db)
    provider = _provider_or_error()
    saved_preview = read_preview(db, payload.preview_id)
    if not saved_preview:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản xem trước. Hãy tạo lại trước khi đồng bộ.")
    if int(saved_preview["actor_user_id"]) != int(actor["ma_nguoi_dung"]):
        raise HTTPException(status_code=403, detail="Bản xem trước thuộc phiên Admin khác.")
    if saved_preview["status"] != "PENDING":
        raise HTTPException(status_code=409, detail="Bản xem trước đã được dùng hoặc không còn hợp lệ.")
    expires_at = parse_timestamp(saved_preview["expires_at"])
    if not expires_at or expires_at <= datetime.now(timezone.utc):
        db.execute("UPDATE HRM_SYNC_PREVIEWS SET status = 'EXPIRED' WHERE preview_id = ?", (payload.preview_id,))
        db.commit()
        raise HTTPException(status_code=409, detail="Bản xem trước đã hết hạn. Hãy tạo bản mới.")

    lock_token = acquire_sync_lock(db, provider.provider_id)
    if not lock_token:
        raise HTTPException(status_code=409, detail="Một phiên đồng bộ HRM đang chạy; hãy thử lại sau.")
    try:
        try:
            await provider.test_connection()
            records = await provider.fetch_employees()
        except HRMProviderError as exc:
            record_failed_sync(db, int(actor["ma_nguoi_dung"]))
            raise _safe_failure(exc)
        context = load_sync_context(db, provider.provider_id)
        rows = preview_rows(records, context)
        digest = snapshot_digest(records, context, rows)
        if not hmac.compare_digest(str(saved_preview["snapshot_hash"]), digest):
            db.execute("UPDATE HRM_SYNC_PREVIEWS SET status = 'STALE' WHERE preview_id = ?", (payload.preview_id,))
            db.commit()
            raise HTTPException(status_code=409, detail="Dữ liệu HRM hoặc mapping đã thay đổi sau preview. Hãy xem trước lại.")
        summary = apply_rows_and_history(db, int(actor["ma_nguoi_dung"]), rows, payload.preview_id)
        CONNECTION_STATE.update(state="CONNECTED", message="Đồng bộ HRM Sandbox đã hoàn tất.")
        return summary
    finally:
        release_sync_lock(db, lock_token, provider.provider_id)


@router.get("/history")
def get_sync_history(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    _require_admin(request)
    _require_schema(db)
    return list_history(db, page, page_size)


@router.get("/directory")
def get_synced_directory(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    _require_admin(request)
    _require_schema(db)
    return list_directory(db, page, page_size)
