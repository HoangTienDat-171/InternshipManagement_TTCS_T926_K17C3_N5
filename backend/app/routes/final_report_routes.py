from datetime import datetime
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from ..database import get_db
from ..final_report_service import FinalReportService
from ..report_export import ReportColumn, make_excel, make_pdf
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


@router.get("/final-evaluations/export")
def export_final_reports(
    request: Request,
    format: Literal["xlsx", "pdf"],
    program_id: Optional[int] = Query(default=None, gt=0),
    internship_profile_id: Optional[int] = Query(default=None, gt=0),
    status: Literal["ALL", "DU_DU_LIEU", "CHUA_DU_LIEU"] = "ALL",
    search: Optional[str] = Query(default=None, max_length=100),
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    report = FinalReportService(db).list_final_reports(
        program_id=program_id,
        profile_id=internship_profile_id,
        status=status,
        search=search,
        page=1,
        page_size=1_000_000,
    )
    items = report["items"]
    if not items:
        raise HTTPException(status_code=404, detail="Không có báo cáo cuối kỳ phù hợp bộ lọc để xuất.")
    metadata = [
        ("Chương trình", items[0]["program_name"] if program_id else "Tất cả"),
        ("Hồ sơ TTS", internship_profile_id or "Tất cả"),
        ("Trạng thái dữ liệu", {"ALL": "Tất cả", "DU_DU_LIEU": "Đủ dữ liệu", "CHUA_DU_LIEU": "Chưa đủ dữ liệu"}[status]),
        ("Tìm kiếm", search or "Không"),
    ]
    totals = [
        ("Số báo cáo theo bộ lọc", len(items)),
        ("Đủ dữ liệu", sum(item["data_status"] == "DU_DU_LIEU" for item in items)),
        ("Chưa đủ dữ liệu", sum(item["data_status"] == "CHUA_DU_LIEU" for item in items)),
    ]
    columns = (
        ReportColumn("Mã HS", "internship_profile_id", 10, 51),
        ReportColumn("Thực tập sinh", "intern_name", 26, 113),
        ReportColumn("Chương trình", "program_name", 30, 126),
        ReportColumn("Mentor", "mentor_name", 25, 105),
        ReportColumn("Giữa kỳ", "midterm_average_score", 12, 60),
        ReportColumn("Cuối kỳ", "final_average_score", 12, 60),
        ReportColumn("Trạng thái", "status_label", 19, 95),
        ReportColumn("Chi tiết thiếu", "status_message", 34, 120),
    )
    rows = (
        {**item, "status_label": "Đủ dữ liệu" if item["data_status"] == "DU_DU_LIEU" else "Chưa đủ dữ liệu"}
        for item in items
    )
    try:
        content = make_excel("Báo cáo đánh giá cuối kỳ", metadata, totals, columns, rows) if format == "xlsx" else make_pdf(
            "Báo cáo đánh giá cuối kỳ", metadata, totals, columns, rows
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    filename = f"ims-final-reports-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{format}"
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == "xlsx" else "application/pdf"
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    })
