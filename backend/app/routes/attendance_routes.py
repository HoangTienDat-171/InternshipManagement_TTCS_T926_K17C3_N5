from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from ..attendance_service import InternAttendanceService
from ..database import get_db
from ..schemas import InternAttendanceCheckIn, InternAttendanceCheckOut
from ..security import require_role


router = APIRouter(tags=["Intern Attendance - US21"])


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
    return InternAttendanceService(db).check_in(intern["ma_nguoi_dung"], data.note)


@router.post("/api/interns/me/attendance/check-out")
def check_out_attendance(
    data: InternAttendanceCheckOut,
    request: Request,
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return InternAttendanceService(db).check_out(intern["ma_nguoi_dung"])
