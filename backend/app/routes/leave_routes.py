import re
from pathlib import Path, PurePosixPath
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import ValidationError

from .. import database as database_module
from ..database import get_db
from ..leave_service import LeaveService
from ..schemas import LeaveRequestCreate, LeaveRequestReview
from ..security import require_role
from .document_routes import valid_file_content


router = APIRouter(tags=["Leave Requests - US24"])
MAX_EVIDENCE_FILE_SIZE = 5 * 1024 * 1024
EVIDENCE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _evidence_root() -> Path:
    return Path(database_module.DB_FILE).resolve().parent / "uploads" / "leave_requests"


def _evidence_path(storage_key: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}\.(pdf|doc|docx|png|jpg|jpeg)", storage_key or ""):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu minh chứng.")
    root = _evidence_root().resolve()
    path = (root / storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu minh chứng trên máy chủ.")
    return path


# ===================== INTERN ENDPOINTS =====================

@router.get("/api/interns/me/leave-programs")
def list_eligible_leave_programs(
    request: Request,
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return LeaveService(db).list_eligible_programs(intern["ma_nguoi_dung"])


@router.post("/api/interns/me/leave-requests", status_code=status.HTTP_201_CREATED)
async def create_leave_request(request: Request, db=Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    uploads = []
    saved_paths = []
    try:
        if request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
            async with request.form() as form:
                payload = {
                    "ma_ung_tuyen": form.get("ma_ung_tuyen"),
                    "start_date": form.get("start_date"),
                    "end_date": form.get("end_date"),
                    "ly_do": form.get("ly_do"),
                }
                uploads = [value for key, value in form.multi_items() if key == "files" and hasattr(value, "read") and hasattr(value, "filename")]
                try:
                    data = LeaveRequestCreate.model_validate(payload)
                except ValidationError as exc:
                    raise RequestValidationError(exc.errors()) from exc

                prepared = []
                for upload in uploads:
                    original_name = PurePosixPath((upload.filename or "").replace("\\", "/")).name
                    extension = Path(original_name).suffix.lower()
                    mime_type = EVIDENCE_TYPES.get(extension)
                    if not original_name or len(original_name) > 255 or any(ord(char) < 32 for char in original_name):
                        raise HTTPException(status_code=400, detail="Tên tệp minh chứng không hợp lệ.")
                    if not mime_type:
                        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ PNG, JPG, JPEG, PDF, DOC hoặc DOCX.")
                    content = await upload.read(MAX_EVIDENCE_FILE_SIZE + 1)
                    if not content or len(content) > MAX_EVIDENCE_FILE_SIZE:
                        raise HTTPException(status_code=400, detail="Mỗi tệp minh chứng phải có dung lượng từ 1 byte đến 5 MB.")
                    valid_content = content.startswith(b"\xff\xd8\xff") if extension in {".jpg", ".jpeg"} else valid_file_content(extension, content)
                    if not valid_content:
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
                    root = _evidence_root()
                    root.mkdir(parents=True, exist_ok=True)
                    for attachment in prepared:
                        path = root / attachment["storage_key"]
                        saved_paths.append(path)
                        with path.open("xb") as stored:
                            stored.write(attachment.pop("content"))
                        attachment["path"] = path
        else:
            try:
                payload = await request.json()
                data = LeaveRequestCreate.model_validate(payload)
            except ValidationError as exc:
                raise RequestValidationError(exc.errors()) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Dữ liệu đơn nghỉ phép không hợp lệ.") from exc

        metadata = []
        if request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
            metadata = [
                {key: value for key, value in item.items() if key != "path"}
                for item in prepared
            ]
        return LeaveService(db).create_request(
            intern["ma_nguoi_dung"],
            data.model_dump(),
            attachments=metadata,
        )
    except Exception:
        db.rollback()
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise


@router.get("/api/interns/me/leave-requests")
def list_my_leave_requests(
    request: Request,
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return LeaveService(db).list_intern_requests(intern["ma_nguoi_dung"])


@router.get("/api/interns/me/leave-requests/{request_id}")
def get_my_leave_request(
    request_id: int,
    request: Request,
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return LeaveService(db).get_intern_request_detail(intern["ma_nguoi_dung"], request_id)


@router.get("/api/interns/me/leave-requests/{request_id}/attachments/{attachment_id}")
def get_my_leave_attachment(
    request_id: int,
    attachment_id: int,
    request: Request,
    download: bool = Query(default=False),
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    service = LeaveService(db)
    service.get_intern_request_detail(intern["ma_nguoi_dung"], request_id)
    attachment = service.get_attachment(request_id, attachment_id)
    return FileResponse(
        _evidence_path(attachment["storage_key"]),
        media_type=attachment["mime_type"],
        filename=attachment["original_filename"],
        content_disposition_type="attachment" if download else "inline",
    )


@router.post("/api/interns/me/leave-requests/{request_id}/cancel")
def cancel_my_leave_request(
    request_id: int,
    request: Request,
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return LeaveService(db).cancel_intern_request(intern["ma_nguoi_dung"], request_id)


# ===================== HR / ADMIN ENDPOINTS =====================

@router.get("/api/leave-requests")
def list_leave_requests(
    request: Request,
    status_filter: Optional[Literal["ChoDuyet", "DaDuyet", "TuChoi", "DaHuy"]] = Query(default=None, alias="status"),
    program_id: Optional[int] = Query(default=None, gt=0),
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    return LeaveService(db).list_all_requests(status_filter=status_filter, program_id=program_id)


@router.get("/api/leave-requests/{request_id}")
def get_leave_request_detail(
    request_id: int,
    request: Request,
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    return LeaveService(db).get_request_for_review(request_id)


@router.get("/api/leave-requests/{request_id}/attachments/{attachment_id}")
def get_leave_attachment(
    request_id: int,
    attachment_id: int,
    request: Request,
    download: bool = Query(default=False),
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    service = LeaveService(db)
    service.get_request_for_review(request_id)
    attachment = service.get_attachment(request_id, attachment_id)
    return FileResponse(
        _evidence_path(attachment["storage_key"]),
        media_type=attachment["mime_type"],
        filename=attachment["original_filename"],
        content_disposition_type="attachment" if download else "inline",
    )


@router.post("/api/leave-requests/{request_id}/review")
def review_leave_request(
    request_id: int,
    data: LeaveRequestReview,
    request: Request,
    db=Depends(get_db),
):
    actor = require_role(request, "Admin", "HR")
    return LeaveService(db).review_request(
        reviewer_user_id=actor["ma_nguoi_dung"],
        request_id=request_id,
        decision=data.trang_thai,
        ly_do_tu_choi=data.ly_do_tu_choi,
    )
