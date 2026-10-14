from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from ..database import get_db
from ..meeting_service import MeetingService
from ..schemas import MeetingCancel, MeetingCreate, MeetingUpdate
from ..security import require_role

router = APIRouter(prefix="/api/meetings", tags=["Meetings - US35/US36"])


@router.get("/participants")
def list_meeting_participants(
    request: Request,
    search: str = Query(default="", max_length=100),
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    return MeetingService(db).list_participants(search)


@router.get("")
def list_meetings(request: Request, db=Depends(get_db)):
    user = require_role(request, "Admin", "HR", "Mentor", "ThucTapSinh")
    return MeetingService(db).list_meetings(user)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_meeting(
    data: MeetingCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    db=Depends(get_db),
):
    user = require_role(request, "Admin", "HR")
    if not idempotency_key.strip():
        raise HTTPException(status_code=422, detail="Thiếu Idempotency-Key cho thao tác tạo lịch.")
    result, created = MeetingService(db).create_meeting(
        user, data.model_dump(), idempotency_key.strip(),
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/{meeting_id}")
def get_meeting(meeting_id: int, request: Request, db=Depends(get_db)):
    user = require_role(request, "Admin", "HR", "Mentor", "ThucTapSinh")
    return MeetingService(db).get_meeting(meeting_id, user)


@router.put("/{meeting_id}")
def update_meeting(
    meeting_id: int,
    data: MeetingUpdate,
    request: Request,
    db=Depends(get_db),
):
    user = require_role(request, "Admin", "HR")
    return MeetingService(db).update_meeting(meeting_id, user, data.model_dump())


@router.post("/{meeting_id}/cancel")
def cancel_meeting(
    meeting_id: int,
    data: MeetingCancel,
    request: Request,
    db=Depends(get_db),
):
    user = require_role(request, "Admin", "HR")
    return MeetingService(db).cancel_meeting(meeting_id, user, data.expected_version)
