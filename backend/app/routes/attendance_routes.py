from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..audit_service import record_request_event
from ..attendance_service import InternAttendanceService
from ..database import get_db
from ..schemas import InternAttendanceCheckIn, InternAttendanceCheckOut
from ..security import require_role


router = APIRouter(tags=["Intern Attendance - US21"])


class AttendanceQrCheckIn(BaseModel):
    token: str = Field(min_length=1, max_length=128)


@router.get("/api/interns/me/attendance/today")
def get_today_attendance(request: Request, db=Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    return InternAttendanceService(db).today(intern["ma_nguoi_dung"])


@router.get("/api/interns/me/attendance")
def get_attendance_history(
    request: Request,
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return InternAttendanceService(db).history(
        intern["ma_nguoi_dung"],
        month=month,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.post("/api/interns/me/attendance/check-in")
def check_in_attendance(
    data: InternAttendanceCheckIn,
    request: Request,
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return InternAttendanceService(db).check_in(intern["ma_nguoi_dung"], data.note, audit_actor=intern)


@router.post("/api/interns/me/attendance/check-out")
def check_out_attendance(
    data: InternAttendanceCheckOut,
    request: Request,
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return InternAttendanceService(db).check_out(intern["ma_nguoi_dung"], audit_actor=intern)


@router.post("/api/interns/me/attendance/qr-token")
def create_attendance_qr_token(request: Request, db=Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    return InternAttendanceService(db).issue_qr_credential(intern["ma_nguoi_dung"])


@router.post("/api/attendance/qr/check-in")
def check_in_by_qr(data: AttendanceQrCheckIn, request: Request, db=Depends(get_db)):
    scanner = require_role(request, "Admin", "HR")
    try:
        return InternAttendanceService(db).check_in_with_qr(data.token, scanner=scanner)
    except HTTPException as exc:
        record_request_event(
            request,
            action="ATTENDANCE_QR_REJECTED",
            resource="ATTENDANCE",
            outcome="FAILURE",
            metadata={"http_status": exc.status_code, "reason": "QR_VALIDATION_FAILED"},
        )
        raise


@router.get("/api/attendance/methods")
def attendance_methods(request: Request):
    require_role(request, "Admin", "HR")
    return {
        "manual": {"available": True, "description": "Luồng chấm công US21 hiện tại."},
        "qr": {"available": True, "description": "QR một lần do TTS đăng nhập tạo, Admin/HR quét."},
        "card": {"available": False, "status": "ADAPTER_CONTRACT_ONLY", "description": "Chưa có đầu đọc, UID contract hoặc nguồn thiết bị được cấu hình."},
    }
