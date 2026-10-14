"""HR/Admin reporting endpoints for Sprint 4."""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from ..database import get_db
from ..report_export import ReportColumn, make_excel, make_pdf
from ..reporting_service import CompletionStatisticsService, InternStatisticsFilters, InternStatisticsService
from ..security import require_role
from .. import database as database_module


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


@router.get("/completion")
def completion_statistics(
    request: Request,
    program_id: int | None = Query(default=None, gt=0),
    department_id: int | None = Query(default=None, gt=0),
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Ngày kết thúc bộ lọc phải sau hoặc bằng ngày bắt đầu.")
    return CompletionStatisticsService(db).overview(
        program_id=program_id, department_id=department_id,
        date_from=date_from, date_to=date_to, search=search,
        page=page, page_size=page_size,
    )


@router.get("/completion/export")
def export_completion_statistics(
    request: Request,
    format: Literal["xlsx", "pdf"],
    program_id: int | None = Query(default=None, gt=0),
    department_id: int | None = Query(default=None, gt=0),
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = Query(default=None, max_length=100),
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Ngày kết thúc bộ lọc phải sau hoặc bằng ngày bắt đầu.")
    service = CompletionStatisticsService(db)
    report = service.overview(
        program_id=program_id, department_id=department_id,
        date_from=date_from, date_to=date_to, search=search,
        page=1, page_size=1,
    )
    summary = report["summary"]
    if not summary["eligible"]:
        raise HTTPException(status_code=404, detail="Chưa có lượt tham gia đủ điều kiện trong bộ lọc để xuất báo cáo.")
    programs = service.db.execute(
        "SELECT ma_chuong_trinh AS id, ten_ct AS name FROM CHUONG_TRINH_THUC_TAP"
    ).fetchall()
    program_name = next((row["name"] for row in programs if row["id"] == program_id), "Tất cả")
    departments = service.db.execute("SELECT ma_phong_ban AS id, ten_phong_ban AS name FROM PHONG_BAN").fetchall()
    department_name = next((row["name"] for row in departments if row["id"] == department_id), "Tất cả")
    metadata = [
        ("Chương trình", program_name),
        ("Phòng ban chương trình", department_name),
        ("Ngày kết thúc chương trình", f"{date_from or 'Bắt đầu'} - {date_to or report['filters']['as_of']}"),
        ("Tìm kiếm", search or "Không"),
        ("Eligible", "Đơn đã duyệt thuộc chương trình đã kết thúc"),
    ]
    totals = [
        ("Đủ điều kiện (Eligible)", summary["eligible"]),
        ("Hoàn thành (Completed)", summary["completed"]),
        ("Chưa hoàn thành", summary["incomplete"]),
        ("Tỷ lệ hoàn thành", f"{summary['completion_rate']}%" if summary["completion_rate"] is not None else "—"),
    ]
    columns = (
        ReportColumn("Mã đơn", "application_id", 12, 55),
        ReportColumn("Mã HS", "profile_id", 10, 48),
        ReportColumn("Thực tập sinh", "intern_name", 25, 110),
        ReportColumn("Email", "intern_email", 32, 140),
        ReportColumn("Chương trình", "program_name", 30, 130),
        ReportColumn("Ngày kết thúc", "program_end_date", 18, 80),
        ReportColumn("Phòng ban", "department_name", 25, 100),
        ReportColumn("Trạng thái", "completion_label", 22, 102),
        ReportColumn("Cập nhật lúc", "completion_updated_at", 22, 90),
        ReportColumn("Cập nhật bởi", "completion_updated_by_name", 25, 110),
    )

    def export_rows():
        for row in service.iter_details(
            summary["eligible"], program_id=program_id, department_id=department_id,
            date_from=date_from, date_to=date_to, search=search,
            as_of=date.fromisoformat(report["filters"]["as_of"]),
        ):
            row["completion_label"] = "Hoàn thành" if row["completion_status"] == "HoanThanh" else "Chưa hoàn thành"
            yield row

    try:
        content = make_excel("Tỷ lệ hoàn thành chương trình thực tập", metadata, totals, columns, export_rows()) if format == "xlsx" else make_pdf(
            "Tỷ lệ hoàn thành chương trình thực tập", metadata, totals, columns, export_rows()
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    filename = f"ims-completion-statistics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{format}"
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == "xlsx" else "application/pdf"
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    })


@router.patch("/completion/applications/{application_id}")
def update_application_completion(
    application_id: int,
    request: Request,
    completion_status: Literal["ChuaHoanThanh", "HoanThanh"] = Body(embed=True),
    db=Depends(get_db),
):
    actor = require_role(request, "Admin", "HR")
    today = date.today()
    if database_module.DATABASE_BACKEND == "sqlite":
        db.execute("BEGIN IMMEDIATE")
    else:
        db.execute(
            "SELECT ma_ung_tuyen FROM UNG_TUYEN_CHUONG_TRINH WHERE ma_ung_tuyen = ? FOR UPDATE",
            (application_id,),
        ).fetchone()
    application = db.execute("""
        SELECT a.ma_ung_tuyen, a.trang_thai, a.completion_status,
               c.ngay_ket_thuc
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
        WHERE a.ma_ung_tuyen = ?
    """, (application_id,)).fetchone()
    if not application:
        db.rollback()
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt tham gia.")
    end_value = application["ngay_ket_thuc"]
    end_date = date.fromisoformat(str(end_value)[:10]) if end_value else None
    if application["trang_thai"] != "DaDuyet" or end_date is None or end_date > today:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Chỉ cập nhật hoàn thành cho lượt đã duyệt thuộc chương trình đã kết thúc.",
        )
    if application["completion_status"] != completion_status:
        db.execute("""
            UPDATE UNG_TUYEN_CHUONG_TRINH
            SET completion_status = ?, completion_updated_by = ?, completion_updated_at = CURRENT_TIMESTAMP
            WHERE ma_ung_tuyen = ? AND trang_thai = 'DaDuyet'
        """, (completion_status, actor["ma_nguoi_dung"], application_id))
    db.commit()
    return {
        "application_id": application_id,
        "completion_status": completion_status,
        "message": "Đã cập nhật trạng thái hoàn thành.",
    }
