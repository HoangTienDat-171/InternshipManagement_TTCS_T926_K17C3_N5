import os
import re
from pathlib import Path, PurePosixPath
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import ValidationError

from .. import database as database_module
from ..database import get_db
from ..schemas import (
    SupportRequestCreate,
    SupportRequestResolve,
    SupportRequestReject,
)
from ..security import require_role
from ..support_request_service import SupportRequestService
from .document_routes import valid_file_content

router = APIRouter(tags=["Support Requests - US27/US28"])

MAX_SUPPORT_FILE_SIZE = 5 * 1024 * 1024
SUPPORT_FILE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _support_file_root() -> Path:
    return Path(database_module.DB_FILE).resolve().parent / "uploads" / "support_requests"


def _support_file_path(storage_key: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}\.(pdf|doc|docx|png|jpg|jpeg)", storage_key or ""):
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp đính kèm.")
    root = _support_file_root().resolve()
    path = (root / storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp đính kèm trên máy chủ.")
    return path


# ============================================================================
# US27 — THỰC TẬP SINH ENDPOINTS
# ============================================================================

@router.post("/api/support-requests", status_code=status.HTTP_201_CREATED)
@router.post("/api/interns/me/support-requests", status_code=status.HTTP_201_CREATED)
async def create_support_request(request: Request, db=Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    saved_paths = []
    prepared = []

    try:
        content_type = request.headers.get("content-type", "").lower()
        if content_type.startswith("multipart/form-data"):
            async with request.form() as form:
                payload = {
                    "loai_yeu_cau": form.get("loai_yeu_cau"),
                    "noi_dung": form.get("noi_dung"),
                    "ma_ho_so": form.get("ma_ho_so") if form.get("ma_ho_so") else None,
                }
                try:
                    data = SupportRequestCreate.model_validate(payload)
                except ValidationError as exc:
                    raise RequestValidationError(exc.errors()) from exc

                uploads = [
                    value for key, value in form.multi_items()
                    if key in ("files", "file") and hasattr(value, "read") and hasattr(value, "filename")
                ]

                for upload in uploads:
                    original_name = PurePosixPath((upload.filename or "").replace("\\", "/")).name
                    if not original_name:
                        continue
                    extension = Path(original_name).suffix.lower()
                    mime_type = SUPPORT_FILE_TYPES.get(extension)

                    if len(original_name) > 255 or any(ord(c) < 32 for c in original_name):
                        raise HTTPException(status_code=400, detail="Tên tệp đính kèm không hợp lệ.")
                    if not mime_type:
                        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ PNG, JPG, JPEG, PDF, DOC hoặc DOCX.")

                    content = await upload.read(MAX_SUPPORT_FILE_SIZE + 1)
                    if not content or len(content) > MAX_SUPPORT_FILE_SIZE:
                        raise HTTPException(status_code=400, detail="Mỗi tệp đính kèm phải có dung lượng từ 1 byte đến 5 MB.")

                    valid = content.startswith(b"\xff\xd8\xff") if extension in {".jpg", ".jpeg"} else valid_file_content(extension, content)
                    if not valid:
                        raise HTTPException(status_code=400, detail="Nội dung tệp không khớp định dạng đã chọn.")

                    storage_key = f"{uuid4().hex}{extension}"
                    prepared.append({
                        "storage_key": storage_key,
                        "original_filename": original_name,
                        "mime_type": mime_type,
                        "file_size": len(content),
                        "content": content,
                    })

                if prepared:
                    root = _support_file_root()
                    root.mkdir(parents=True, exist_ok=True)
                    for att in prepared:
                        path = root / att["storage_key"]
                        saved_paths.append(path)
                        with path.open("xb") as stored:
                            stored.write(att.pop("content"))
        else:
            try:
                payload = await request.json()
                data = SupportRequestCreate.model_validate(payload)
            except ValidationError as exc:
                raise RequestValidationError(exc.errors()) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Dữ liệu yêu cầu hỗ trợ không hợp lệ.") from exc

        metadata = [
            {k: v for k, v in item.items() if k != "content"}
            for item in prepared
        ]

        return SupportRequestService(db).create_request(
            intern_user_id=intern["ma_nguoi_dung"],
            payload=data.model_dump(),
            attachments=metadata,
        )
    except Exception:
        db.rollback()
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise


@router.get("/api/support-requests/my")
@router.get("/api/interns/me/support-requests")
def list_my_support_requests(
    request: Request,
    trang_thai: Optional[str] = Query(None, description="Lọc trạng thái (PENDING, RESOLVED, REJECTED)"),
    loai_yeu_cau: Optional[str] = Query(None, description="Lọc loại yêu cầu (CERTIFICATE, DOCUMENT, OTHER)"),
    status: Optional[str] = Query(None, description="Lọc trạng thái (alias)"),
    type: Optional[str] = Query(None, description="Lọc loại yêu cầu (alias)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return SupportRequestService(db).list_my_requests(
        intern_user_id=intern["ma_nguoi_dung"],
        status_filter=trang_thai or status,
        type_filter=loai_yeu_cau or type,
        page=page,
        page_size=page_size,
    )


@router.get("/api/support-requests/my/{request_id}")
@router.get("/api/interns/me/support-requests/{request_id}")
def get_my_support_request_detail(
    request_id: int,
    request: Request,
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return SupportRequestService(db).get_my_request_detail(
        intern_user_id=intern["ma_nguoi_dung"],
        request_id=request_id,
    )


# ============================================================================
# US28 — HR & ADMIN MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/api/support-requests")
def list_support_requests_hr(
    request: Request,
    trang_thai: Optional[str] = Query(None, description="Lọc trạng thái"),
    loai_yeu_cau: Optional[str] = Query(None, description="Lọc loại yêu cầu"),
    status: Optional[str] = Query(None, description="Lọc trạng thái (alias)"),
    type: Optional[str] = Query(None, description="Lọc loại yêu cầu (alias)"),
    search: Optional[str] = Query(None, description="Tìm kiếm tên, email TTS hoặc nội dung"),
    intern_id: Optional[int] = Query(None, description="Lọc theo mã TTS"),
    date_from: Optional[str] = Query(None, description="Từ ngày (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Đến ngày (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
):
    actor = require_role(request, "HR", "Admin", "ThucTapSinh")
    st = trang_thai or status
    tp = loai_yeu_cau or type
    if actor["vai_tro"] == "ThucTapSinh":
        return SupportRequestService(db).list_my_requests(
            intern_user_id=actor["ma_nguoi_dung"],
            status_filter=st,
            type_filter=tp,
            page=page,
            page_size=page_size,
        )
    return SupportRequestService(db).list_all_requests(
        status_filter=st,
        type_filter=tp,
        search=search,
        intern_id=intern_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get("/api/support-requests/{request_id}")
def get_support_request_detail_hr(
    request_id: int,
    request: Request,
    db=Depends(get_db),
):
    actor = require_role(request, "HR", "Admin", "ThucTapSinh")
    if actor["vai_tro"] == "ThucTapSinh":
        return SupportRequestService(db).get_my_request_detail(
            intern_user_id=actor["ma_nguoi_dung"],
            request_id=request_id,
        )
    return SupportRequestService(db).get_request_detail_hr(request_id)


@router.put("/api/support-requests/{request_id}/resolve")
async def resolve_support_request(
    request_id: int,
    request: Request,
    db=Depends(get_db),
):
    actor = require_role(request, "HR", "Admin")
    try:
        body = await request.json()
        payload = SupportRequestResolve.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Dữ liệu phản hồi không hợp lệ.") from exc

    return SupportRequestService(db).resolve_request(
        actor_id=actor["ma_nguoi_dung"],
        request_id=request_id,
        phan_hoi_hr=payload.phan_hoi_hr,
    )


@router.put("/api/support-requests/{request_id}/reject")
async def reject_support_request(
    request_id: int,
    request: Request,
    db=Depends(get_db),
):
    actor = require_role(request, "HR", "Admin")
    try:
        body = await request.json()
        payload = SupportRequestReject.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Dữ liệu từ chối không hợp lệ.") from exc

    return SupportRequestService(db).reject_request(
        actor_id=actor["ma_nguoi_dung"],
        request_id=request_id,
        ly_do_tu_choi=payload.ly_do_tu_choi,
    )


@router.get("/api/support-requests/{request_id}/files/{file_id}")
def download_support_request_file(
    request_id: int,
    file_id: int,
    request: Request,
    db=Depends(get_db),
):
    user = require_role(request, "ThucTapSinh", "HR", "Admin")
    file_record = SupportRequestService(db).get_attachment(
        request_id=request_id,
        file_id=file_id,
        user=user,
    )
    file_path = _support_file_path(file_record["storage_key"])
    return FileResponse(
        path=file_path,
        media_type=file_record["mime_type"],
        filename=file_record["original_filename"],
    )
