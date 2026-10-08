import re
from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import ValidationError

from .. import database as database_module
from ..allowance_service import AllowanceService
from ..database import get_db
from ..schemas import (AllowanceCreate, AllowanceReceiptReport,
                       AllowanceReportUpdate, AllowanceUpdate)
from ..security import require_role

router = APIRouter(tags=["Allowances - US25/26"])
Period = Annotated[str | None, Query(pattern=r"^[1-9][0-9]{3}-(0[1-9]|1[0-2])$")]
Year = Annotated[int | None, Query(ge=1000, le=9999)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Program = Annotated[int | None, Query(gt=0)]
Search = Annotated[str, Query(max_length=100)]
ReceiptStatus = Annotated[str | None, Query(pattern=r"^(ChoXacNhan|DaNhan|ChuaNhanDuoc|DangXuLy)$")]
ReportStatus = Annotated[str | None, Query(pattern=r"^(ChoXuLy|DangXuLy|DaXuLy)$")]
MAX_REPORT_IMAGE_SIZE = 5 * 1024 * 1024
MAX_REPORT_IMAGES = 5
REPORT_IMAGE_TYPES = {
    ".png": ("image/png", lambda content: content.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda content: content.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda content: content.startswith(b"\xff\xd8\xff")),
    ".webp": ("image/webp", lambda content: len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"),
}


def _report_image_root() -> Path:
    return Path(database_module.DB_FILE).resolve().parent / "uploads" / "allowance_reports"


def _report_image_path(storage_key: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}\.(png|jpg|jpeg|webp)", storage_key or ""):
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh minh chứng.")
    root = _report_image_root().resolve()
    path = (root / storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh minh chứng trên máy chủ.")
    return path


async def _prepare_report_images(form):
    uploads = [value for key, value in form.multi_items()
               if key == "files" and hasattr(value, "read") and hasattr(value, "filename")]
    if len(uploads) > MAX_REPORT_IMAGES:
        raise HTTPException(status_code=400, detail=f"Mỗi phản ánh được đính kèm tối đa {MAX_REPORT_IMAGES} ảnh.")
    prepared = []
    for upload in uploads:
        original_name = PurePosixPath((upload.filename or "").replace("\\", "/")).name
        extension = Path(original_name).suffix.lower()
        image_type = REPORT_IMAGE_TYPES.get(extension)
        if (not original_name or len(original_name) > 255
                or any(ord(char) < 32 for char in original_name)):
            raise HTTPException(status_code=400, detail="Tên ảnh minh chứng không hợp lệ.")
        if not image_type:
            raise HTTPException(status_code=400, detail="Chỉ hỗ trợ ảnh PNG, JPG, JPEG hoặc WEBP.")
        content = await upload.read(MAX_REPORT_IMAGE_SIZE + 1)
        if not content or len(content) > MAX_REPORT_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail="Mỗi ảnh minh chứng phải có dung lượng từ 1 byte đến 5 MB.")
        mime_type, content_check = image_type
        if not content_check(content):
            raise HTTPException(status_code=400, detail="Nội dung ảnh không khớp với định dạng đã chọn.")
        prepared.append({
            "storage_key": f"{uuid4().hex}{extension}",
            "original_filename": original_name,
            "mime_type": mime_type,
            "file_size": len(content),
            "content": content,
        })
    return prepared


@router.get("/api/allowances/profiles")
def allowance_profiles(request: Request, search: Search = "", program_id: Program = None,
                       page: Page = 1, page_size: PageSize = 25, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).options(search.strip(), program_id, page, page_size)


@router.get("/api/allowances/interns")
def allowance_interns(request: Request, search: Search = "", program_id: Program = None,
                      page: Page = 1, page_size: PageSize = 25, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).intern_options(search.strip(), program_id, page, page_size)


@router.get("/api/allowances/programs")
def allowance_programs(request: Request, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).programs()


@router.get("/api/allowances/eligible-programs")
def eligible_allowance_programs(request: Request, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).eligible_programs()


@router.get("/api/allowances")
def list_allowances(request: Request, search: Search = "", program_id: Program = None,
                    intern_id: Program = None, ky: Period = None, year: Year = None,
                    receipt_status: ReceiptStatus = None, page: Page = 1,
                    page_size: PageSize = 25, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).list_records(search=search.strip(), program_id=program_id,
        intern_id=intern_id, ky=ky, year=year, receipt_status=receipt_status,
        page=page, page_size=page_size)


@router.get("/api/allowances/reports")
def allowance_reports(request: Request, report_status: ReportStatus = None,
                      page: Page = 1, page_size: PageSize = 25, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).list_reports(status=report_status, page=page, page_size=page_size)


@router.put("/api/allowances/reports/{report_id}")
def update_allowance_report(report_id: int, payload: AllowanceReportUpdate,
                            request: Request, db=Depends(get_db)):
    actor = require_role(request, "HR", "Admin")
    return AllowanceService(db).update_report(report_id,
        status=payload.trang_thai_xu_ly, note=payload.ghi_chu_xu_ly,
        actor_id=actor["ma_nguoi_dung"])


@router.post("/api/allowances", status_code=201)
def create_allowance(payload: AllowanceCreate, request: Request, db=Depends(get_db)):
    actor = require_role(request, "HR", "Admin")
    return AllowanceService(db).save(payload.model_dump(), actor["ma_nguoi_dung"])


@router.get("/api/allowances/{record_id}")
def allowance_detail(record_id: int, request: Request, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).detail(record_id)


@router.put("/api/allowances/{record_id}")
def update_allowance(record_id: int, payload: AllowanceUpdate, request: Request, db=Depends(get_db)):
    actor = require_role(request, "HR", "Admin")
    return AllowanceService(db).save(payload.model_dump(), actor["ma_nguoi_dung"], record_id)


@router.get("/api/interns/me/allowances")
def my_allowances(request: Request, ky: Period = None, year: Year = None,
                  program_id: Program = None, receipt_status: ReceiptStatus = None, page: Page = 1,
                  page_size: PageSize = 25, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    return AllowanceService(db).list_records(owner_id=actor["ma_nguoi_dung"], ky=ky,
        year=year, program_id=program_id, receipt_status=receipt_status,
        page=page, page_size=page_size)


@router.get("/api/interns/me/allowance-programs")
def my_allowance_programs(request: Request, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    return AllowanceService(db).programs(owner_id=actor["ma_nguoi_dung"])


@router.get("/api/interns/me/allowances/{record_id}")
def my_allowance_detail(record_id: int, request: Request, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    return AllowanceService(db).detail(record_id, owner_id=actor["ma_nguoi_dung"])


@router.post("/api/interns/me/allowances/{record_id}/received")
def confirm_allowance_received(record_id: int, request: Request, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    return AllowanceService(db).confirm_received(record_id,
        owner_id=actor["ma_nguoi_dung"], actor_id=actor["ma_nguoi_dung"])


@router.post("/api/interns/me/allowances/{record_id}/reports")
async def report_allowance_unreceived(record_id: int, request: Request, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    saved_paths = []
    try:
        prepared = []
        if request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
            async with request.form() as form:
                try:
                    payload = AllowanceReceiptReport.model_validate({"noi_dung": form.get("noi_dung")})
                except ValidationError as exc:
                    raise RequestValidationError(exc.errors()) from exc
                prepared = await _prepare_report_images(form)
        else:
            try:
                payload = AllowanceReceiptReport.model_validate(await request.json())
            except ValidationError as exc:
                raise RequestValidationError(exc.errors()) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Dữ liệu phản ánh không hợp lệ.") from exc

        if prepared:
            root = _report_image_root()
            root.mkdir(parents=True, exist_ok=True)
            for attachment in prepared:
                path = root / attachment["storage_key"]
                saved_paths.append(path)
                with path.open("xb") as stored:
                    stored.write(attachment.pop("content"))

        metadata = [{key: value for key, value in item.items() if key != "content"}
                    for item in prepared]
        return AllowanceService(db).report_unreceived(record_id,
            owner_id=actor["ma_nguoi_dung"], actor_id=actor["ma_nguoi_dung"],
            note=payload.noi_dung, attachments=metadata)
    except Exception:
        db.rollback()
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise


@router.post("/api/interns/me/allowance-reports/{report_id}/acknowledge")
def acknowledge_allowance_report(report_id: int, request: Request, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    return AllowanceService(db).acknowledge_report(report_id,
        owner_id=actor["ma_nguoi_dung"], actor_id=actor["ma_nguoi_dung"])


@router.get("/api/allowance-reports/{report_id}/attachments/{attachment_id}")
def get_allowance_report_attachment(report_id: int, attachment_id: int, request: Request,
                                   download: bool = Query(default=False), db=Depends(get_db)):
    actor = require_role(request, "Admin", "HR", "ThucTapSinh")
    owner_id = actor["ma_nguoi_dung"] if actor["vai_tro"] == "ThucTapSinh" else None
    attachment = AllowanceService(db).get_report_attachment(report_id, attachment_id, owner_id=owner_id)
    return FileResponse(
        _report_image_path(attachment["storage_key"]),
        media_type=attachment["mime_type"],
        filename=attachment["original_filename"],
        content_disposition_type="attachment" if download else "inline",
    )
