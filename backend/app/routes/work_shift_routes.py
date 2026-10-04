from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status

from ..database import get_db
from ..schemas import WorkShiftCreate, WorkShiftUpdate
from ..security import require_role
from ..work_shift_service import WorkShiftService


router = APIRouter(prefix="/api/work-shifts", tags=["Work Shifts - US23"])


@router.get("")
def list_work_shifts(
    request: Request,
    status_filter: Literal["ACTIVE", "INACTIVE"] | None = Query(default=None, alias="status"),
    scope_type: Literal["GLOBAL", "PROGRAM"] | None = None,
    program_id: int | None = Query(default=None, gt=0),
    effective_date: date | None = None,
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    return WorkShiftService(db).list_shifts(
        status=status_filter,
        scope_type=scope_type,
        program_id=program_id,
        effective_date=effective_date,
    )


@router.get("/{shift_id}")
def get_work_shift(shift_id: int, request: Request, db=Depends(get_db)):
    require_role(request, "Admin", "HR")
    return WorkShiftService(db).get_shift(shift_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_work_shift(data: WorkShiftCreate, request: Request, db=Depends(get_db)):
    actor = require_role(request, "Admin", "HR")
    return WorkShiftService(db).create_shift(data.model_dump(), actor["ma_nguoi_dung"])


@router.patch("/{shift_id}")
def update_work_shift(
    shift_id: int,
    data: WorkShiftUpdate,
    request: Request,
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    return WorkShiftService(db).update_shift(shift_id, data.model_dump(exclude_unset=True))
