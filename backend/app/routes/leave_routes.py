from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, status

from ..database import get_db
from ..leave_service import LeaveService
from ..schemas import LeaveRequestCreate, LeaveRequestReview
from ..security import require_role


router = APIRouter(tags=["Leave Requests - US24"])


# ===================== INTERN ENDPOINTS =====================

@router.post("/api/interns/me/leave-requests", status_code=status.HTTP_201_CREATED)
def create_leave_request(
    data: LeaveRequestCreate,
    request: Request,
    db=Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return LeaveService(db).create_request(intern["ma_nguoi_dung"], data.model_dump())


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
