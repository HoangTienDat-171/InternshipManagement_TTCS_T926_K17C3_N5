from typing import Literal, Optional
from fastapi import APIRouter, Depends, Query, Request

from ..database import get_db
from ..final_report_service import FinalReportService
from ..schemas import FinalReportDetail, FinalReportListResponse
from ..security import require_role

router = APIRouter(prefix="/api/reports", tags=["Final Reports - US20"])


@router.get("/final-evaluations", response_model=FinalReportListResponse)
def list_final_reports(
    request: Request,
    program_id: Optional[int] = Query(default=None, gt=0),
    internship_profile_id: Optional[int] = Query(default=None, gt=0),
    status: Optional[Literal["ALL", "DU_DU_LIEU", "CHUA_DU_LIEU"]] = Query(default="ALL"),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    return FinalReportService(db).list_final_reports(
        program_id=program_id,
        profile_id=internship_profile_id,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/final-evaluations/{profile_id}/{program_id}", response_model=FinalReportDetail)
def get_final_report(
    profile_id: int,
    program_id: int,
    request: Request,
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    return FinalReportService(db).get_final_report(profile_id, program_id)
