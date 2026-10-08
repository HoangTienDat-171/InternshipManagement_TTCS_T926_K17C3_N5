from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from ..allowance_service import AllowanceService
from ..database import get_db
from ..schemas import (AllowanceCreate, AllowanceReceiptReport,
                       AllowanceReportUpdate, AllowanceUpdate)
from ..security import require_role

router = APIRouter(tags=["Allowances - US25/26"])
Period = Annotated[str | None, Query(pattern=r"^[1-9][0-9]{3}-(0[1-9]|1[0-2])$")]
Year = Annotated[int | None, Query(ge=1000, le=9999)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Program = Annotated[int | None, Query(gt=0)]
Search = Annotated[str, Query(max_length=100)]
ReceiptStatus = Annotated[str | None, Query(pattern=r"^(ChoXacNhan|DaNhan|ChuaNhanDuoc|DangXuLy)$")]
ReportStatus = Annotated[str | None, Query(pattern=r"^(ChoXuLy|DangXuLy|DaXuLy)$")]


@router.get("/api/allowances/profiles")
def allowance_profiles(request: Request, search: Search = "", program_id: Program = None,
                       page: Page = 1, page_size: PageSize = 25, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).options(search.strip(), program_id, page, page_size)


@router.get("/api/allowances/interns")
def allowance_interns(request: Request, search: Search = "", program_id: Program = None,
                      page: Page = 1, page_size: PageSize = 25, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).intern_options(search.strip(), program_id, page, page_size)


@router.get("/api/allowances/programs")
def allowance_programs(request: Request, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).programs()


@router.get("/api/allowances")
def list_allowances(request: Request, search: Search = "", program_id: Program = None,
                    intern_id: Program = None, ky: Period = None, year: Year = None,
                    receipt_status: ReceiptStatus = None, page: Page = 1,
                    page_size: PageSize = 25, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).list_records(search=search.strip(), program_id=program_id,
        intern_id=intern_id, ky=ky, year=year, receipt_status=receipt_status,
        page=page, page_size=page_size)


@router.get("/api/allowances/reports")
def allowance_reports(request: Request, report_status: ReportStatus = None,
                      page: Page = 1, page_size: PageSize = 25, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).list_reports(status=report_status, page=page, page_size=page_size)


@router.put("/api/allowances/reports/{report_id}")
def update_allowance_report(report_id: int, payload: AllowanceReportUpdate,
                            request: Request, db=Depends(get_db)):
    actor = require_role(request, "HR", "Admin")
    return AllowanceService(db).update_report(report_id,
        status=payload.trang_thai_xu_ly, note=payload.ghi_chu_xu_ly,
        actor_id=actor["ma_nguoi_dung"])


@router.post("/api/allowances", status_code=201)
def create_allowance(payload: AllowanceCreate, request: Request, db=Depends(get_db)):
    actor = require_role(request, "HR", "Admin")
    return AllowanceService(db).save(payload.model_dump(), actor["ma_nguoi_dung"])


@router.get("/api/allowances/{record_id}")
def allowance_detail(record_id: int, request: Request, db=Depends(get_db)):
    require_role(request, "HR", "Admin")
    return AllowanceService(db).detail(record_id)


@router.put("/api/allowances/{record_id}")
def update_allowance(record_id: int, payload: AllowanceUpdate, request: Request, db=Depends(get_db)):
    actor = require_role(request, "HR", "Admin")
    return AllowanceService(db).save(payload.model_dump(), actor["ma_nguoi_dung"], record_id)


@router.get("/api/interns/me/allowances")
def my_allowances(request: Request, ky: Period = None, year: Year = None,
                  program_id: Program = None, receipt_status: ReceiptStatus = None, page: Page = 1,
                  page_size: PageSize = 25, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    return AllowanceService(db).list_records(owner_id=actor["ma_nguoi_dung"], ky=ky,
        year=year, program_id=program_id, receipt_status=receipt_status,
        page=page, page_size=page_size)


@router.get("/api/interns/me/allowance-programs")
def my_allowance_programs(request: Request, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    return AllowanceService(db).programs(owner_id=actor["ma_nguoi_dung"])


@router.get("/api/interns/me/allowances/{record_id}")
def my_allowance_detail(record_id: int, request: Request, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    return AllowanceService(db).detail(record_id, owner_id=actor["ma_nguoi_dung"])


@router.post("/api/interns/me/allowances/{record_id}/received")
def confirm_allowance_received(record_id: int, request: Request, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    return AllowanceService(db).confirm_received(record_id,
        owner_id=actor["ma_nguoi_dung"], actor_id=actor["ma_nguoi_dung"])


@router.post("/api/interns/me/allowances/{record_id}/reports")
def report_allowance_unreceived(record_id: int, payload: AllowanceReceiptReport,
                                request: Request, db=Depends(get_db)):
    actor = require_role(request, "ThucTapSinh")
    return AllowanceService(db).report_unreceived(record_id,
        owner_id=actor["ma_nguoi_dung"], actor_id=actor["ma_nguoi_dung"],
        note=payload.noi_dung)
