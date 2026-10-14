"""HR/Admin reporting endpoints for Sprint 4."""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from ..database import get_db
from ..report_export import ReportColumn, make_excel, make_pdf
from ..reporting_service import InternStatisticsFilters, InternStatisticsService
from ..security import require_role


router = APIRouter(prefix="/api/reports", tags=["Statistics - US32/US34"])


def _filters(program_id, department_id, date_from, date_to, school_id, major, search):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    return InternStatisticsFilters(
        program_id=program_id,
        department_id=department_id,
        date_from=date_from,
        date_to=date_to,
        school_id=school_id,
        major=major.strip() if major else None,
        search=search.strip() if search else None,
    )


@router.get("/intern-statistics/options")
def intern_statistics_options(request: Request, db=Depends(get_db)):
    require_role(request, "Admin", "HR")
    return InternStatisticsService(db).options()


@router.get("/intern-statistics")
def intern_statistics(
    request: Request,
    program_id: int | None = Query(default=None, gt=0),
    department_id: int | None = Query(default=None, gt=0),
    date_from: date | None = None,
    date_to: date | None = None,
    school_id: int | None = Query(default=None, ge=0),
    major: str | None = Query(default=None, max_length=100),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    filters = _filters(program_id, department_id, date_from, date_to, school_id, major, search)
    return InternStatisticsService(db).overview(filters, page, page_size)


@router.get("/intern-statistics/export")
def export_intern_statistics(
    request: Request,
    format: Literal["xlsx", "pdf"],
    program_id: int | None = Query(default=None, gt=0),
    department_id: int | None = Query(default=None, gt=0),
    date_from: date | None = None,
    date_to: date | None = None,
    school_id: int | None = Query(default=None, ge=0),
    major: str | None = Query(default=None, max_length=100),
    search: str | None = Query(default=None, max_length=100),
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    filters = _filters(program_id, department_id, date_from, date_to, school_id, major, search)
    service = InternStatisticsService(db)
    report = service.overview(filters, 1, 1)
    summary = report["summary"]
    if not summary["unique_interns"]:
        raise HTTPException(status_code=404, detail="Không có hồ sơ phù hợp bộ lọc để xuất báo cáo.")

    options = service.options()
    program_name = next((item["name"] for item in options["programs"] if item["id"] == program_id), "Tất cả")
    department_name = next((item["name"] for item in options["departments"] if item["id"] == department_id), "Tất cả")
    school_name = report["schools"][0]["name"] if school_id is not None and report["schools"] else "Tất cả"
    metadata = [
        ("Chương trình", program_name),
        ("Phòng ban TTS", department_name),
        ("Ngày tạo hồ sơ", f"{date_from or 'Bắt đầu'} - {date_to or 'Hiện tại'}"),
        ("Trường", school_name),
        ("Ngành", major or "Tất cả"),
        ("Tìm kiếm", search or "Không"),
    ]
    totals = [
        ("TTS duy nhất", summary["unique_interns"]),
        ("Lượt tham gia được duyệt", summary["approved_participations"]),
        ("Trường có thông tin", summary["known_schools"]),
        ("Ngành có thông tin", summary["known_majors"]),
    ]
    columns = (
        ReportColumn("Mã HS", "ma_ho_so", 10, 55),
        ReportColumn("Thực tập sinh", "ho_ten", 25, 118),
        ReportColumn("Email", "email", 32, 150),
        ReportColumn("Trường đại học", "ten_truong", 35, 145),
        ReportColumn("Chuyên ngành", "chuyen_nganh", 27, 120),
        ReportColumn("Phòng ban", "ten_phong_ban", 25, 100),
        ReportColumn("Ngày tạo HS", "ngay_tao", 22, 86),
    )
    rows = service.iter_details(filters, summary["unique_interns"])
    try:
        content = make_excel("Thống kê thực tập sinh theo trường/ngành", metadata, totals, columns, rows) if format == "xlsx" else make_pdf(
            "Thống kê thực tập sinh theo trường/ngành", metadata, totals, columns, rows
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    filename = f"ims-intern-statistics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{format}"
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == "xlsx" else "application/pdf"
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    })
