import re
import sqlite3
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from ..database import DB_FILE, get_db
from ..schemas import WeeklyReportCreate, WeeklyReportReview, WeeklyReportUpdate
from ..security import require_role
from ..weekly_report_service import WeeklyReportService
from .document_routes import valid_file_content


router = APIRouter(tags=["Weekly Reports - US17"])
REPORT_STORAGE_ROOT = Path(DB_FILE).parent / "uploads" / "weekly_reports"
MAX_REPORT_ATTACHMENT_SIZE = 10 * 1024 * 1024
ALLOWED_ATTACHMENTS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
}


@router.get("/api/interns/me/weekly-report-programs")
def list_weekly_report_programs(request: Request, db: sqlite3.Connection = Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    return WeeklyReportService(db).list_programs(intern["ma_nguoi_dung"])


@router.post("/api/interns/me/weekly-reports", status_code=status.HTTP_201_CREATED)
def create_weekly_report(data: WeeklyReportCreate, request: Request, db: sqlite3.Connection = Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    return WeeklyReportService(db).create(intern, data)


@router.get("/api/interns/me/weekly-reports")
def list_weekly_reports(
    request: Request,
    report_status: str | None = Query(default=None, alias="status", pattern="^(DRAFT|SUBMITTED)$"),
    program_id: int | None = Query(default=None, gt=0),
    db: sqlite3.Connection = Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return WeeklyReportService(db).list_for_intern(intern["ma_nguoi_dung"], report_status, program_id)


@router.get("/api/interns/me/weekly-reports/{report_id}")
def get_weekly_report(report_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    return WeeklyReportService(db).get(report_id, intern["ma_nguoi_dung"])


@router.patch("/api/interns/me/weekly-reports/{report_id}")
def update_weekly_report(
    report_id: int,
    data: WeeklyReportUpdate,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return WeeklyReportService(db).update(report_id, intern, data)


@router.post("/api/interns/me/weekly-reports/{report_id}/submit")
def submit_weekly_report(report_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    return WeeklyReportService(db).submit(report_id, intern)


def _attachment_path(storage_key: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}\.(pdf|docx|png)", storage_key or ""):
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp đính kèm.")
    root = REPORT_STORAGE_ROOT.resolve()
    path = (root / storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp đính kèm trên máy chủ.")
    return path


@router.post("/api/interns/me/weekly-reports/{report_id}/attachment")
async def upload_weekly_report_attachment(
    report_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: sqlite3.Connection = Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    original_name = file.filename or ""
    if (
        not original_name or len(original_name) > 255
        or "/" in original_name or "\\" in original_name or ":" in original_name
        or any(ord(char) < 32 for char in original_name)
    ):
        raise HTTPException(status_code=400, detail="Tên tệp đính kèm không hợp lệ.")
    extension = Path(original_name).suffix.lower()
    mime_type = ALLOWED_ATTACHMENTS.get(extension)
    if not mime_type:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ tệp PDF, DOCX hoặc PNG.")
    content = await file.read(MAX_REPORT_ATTACHMENT_SIZE + 1)
    if not content or len(content) > MAX_REPORT_ATTACHMENT_SIZE:
        raise HTTPException(status_code=400, detail="Tệp đính kèm phải có dung lượng từ 1 byte đến 10 MB.")
    if not valid_file_content(extension, content):
        raise HTTPException(status_code=400, detail="Nội dung tệp không đúng định dạng.")

    service = WeeklyReportService(db)
    storage_key = f"{uuid4().hex}{extension}"
    file_path = REPORT_STORAGE_ROOT / storage_key
    previous_key = None
    written = False
    try:
        db.execute("BEGIN IMMEDIATE")
        report = service.attachment_record(report_id, intern["ma_nguoi_dung"], for_update=True)
        if report["status"] != "DRAFT":
            raise HTTPException(status_code=409, detail="Báo cáo đã nộp và không thể thay đổi tệp đính kèm.")
        previous_key = db.execute(
            "SELECT attachment_storage_key FROM BAO_CAO_TUAN WHERE ma_bao_cao = ?", (report_id,)
        ).fetchone()["attachment_storage_key"]
        REPORT_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        with file_path.open("xb") as stored:
            stored.write(content)
            written = True
        db.execute("""
            UPDATE BAO_CAO_TUAN
            SET attachment_storage_key = ?, attachment_original_name = ?,
                attachment_mime_type = ?, attachment_file_size = ?, updated_at = CURRENT_TIMESTAMP
            WHERE ma_bao_cao = ? AND trang_thai = 'DRAFT'
        """, (storage_key, original_name, mime_type, len(content), report_id))
        db.commit()
    except Exception:
        db.rollback()
        if written:
            file_path.unlink(missing_ok=True)
        raise
    if previous_key:
        try:
            _attachment_path(previous_key).unlink(missing_ok=True)
        except HTTPException:
            pass
    return service.get(report_id, intern["ma_nguoi_dung"])


@router.get("/api/interns/me/weekly-reports/{report_id}/attachment")
def download_weekly_report_attachment(report_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    report = WeeklyReportService(db).attachment_record(report_id, intern["ma_nguoi_dung"])
    if not report["has_attachment"]:
        raise HTTPException(status_code=404, detail="Báo cáo chưa có tệp đính kèm.")
    row = db.execute("""
        SELECT attachment_storage_key, attachment_original_name, attachment_mime_type
        FROM BAO_CAO_TUAN WHERE ma_bao_cao = ?
    """, (report_id,)).fetchone()
    return FileResponse(
        _attachment_path(row["attachment_storage_key"]),
        media_type=row["attachment_mime_type"],
        filename=row["attachment_original_name"],
        content_disposition_type="attachment",
    )


@router.get("/api/mentor/me/weekly-reports")
def list_mentor_weekly_reports(
    request: Request,
    intern_user_id: int | None = Query(default=None, gt=0),
    program_id: int | None = Query(default=None, gt=0),
    week_start: date | None = None,
    reviewed: bool | None = None,
    db: sqlite3.Connection = Depends(get_db),
):
    mentor = require_role(request, "Mentor")
    return WeeklyReportService(db).list_for_mentor(
        mentor["ma_nguoi_dung"],
        intern_user_id=intern_user_id,
        program_id=program_id,
        week_start=week_start,
        reviewed=reviewed,
    )


@router.get("/api/mentor/weekly-reports/{report_id}")
def get_mentor_weekly_report(report_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    mentor = require_role(request, "Mentor")
    return WeeklyReportService(db).get_for_mentor(report_id, mentor["ma_nguoi_dung"])


@router.post("/api/mentor/weekly-reports/{report_id}/review")
def review_weekly_report(
    report_id: int,
    data: WeeklyReportReview,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    mentor = require_role(request, "Mentor")
    return WeeklyReportService(db).review(report_id, mentor, data)


@router.get("/api/mentor/weekly-reports/{report_id}/attachment")
def download_mentor_weekly_report_attachment(
    report_id: int,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    mentor = require_role(request, "Mentor")
    report = WeeklyReportService(db).mentor_attachment_record(report_id, mentor["ma_nguoi_dung"])
    if not report["has_attachment"]:
        raise HTTPException(status_code=404, detail="Báo cáo chưa có tệp đính kèm.")
    row = db.execute("""
        SELECT attachment_storage_key, attachment_original_name, attachment_mime_type
        FROM BAO_CAO_TUAN WHERE ma_bao_cao = ?
    """, (report_id,)).fetchone()
    return FileResponse(
        _attachment_path(row["attachment_storage_key"]),
        media_type=row["attachment_mime_type"],
        filename=row["attachment_original_name"],
        content_disposition_type="attachment",
    )
