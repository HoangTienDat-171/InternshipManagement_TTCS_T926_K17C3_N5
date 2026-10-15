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


def _require_admin(request: Request):
    return require_role(request, "Admin")


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
    counts = {action: sum(row["action"] == action for row in rows) for action in ("NEW", "UPDATE", "UNCHANGED", "CONFLICT", "INVALID")}
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
