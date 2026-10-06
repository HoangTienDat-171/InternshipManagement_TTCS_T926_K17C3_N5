import sqlite3
import os
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status

from ..database import get_db
from .. import database as database_module
from .document_routes import MAX_FILE_SIZE, UPLOAD_ROOT, valid_file_content
from ..notifications import create_notification
from ..schemas import (
    ProgramApplicationDetail,
    ProgramApplicationReview,
    ProgramCreate,
    ProgramDetail,
)
from ..security import require_role

router = APIRouter(prefix="/api/programs", tags=["Internship Programs"])


def _email_value(value: Any, fallback: str = "Chưa cập nhật") -> str:
    """Render optional or user-provided values as safe, single-line plain text."""
    normalized = " ".join(str(value or "").split())
    return normalized or fallback


def _email_date(value: Any) -> str:
    normalized = _email_value(value, "")
    return normalized[:10] if normalized else "Chưa xác định"


def parse_required_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} phải theo định dạng YYYY-MM-DD.",
        ) from exc


def validated_program_values(data: ProgramCreate) -> tuple[Any, ...]:
    start_date = parse_required_date(data.ngay_bat_dau, "Ngày bắt đầu")
    end_date = parse_required_date(data.ngay_ket_thuc, "Ngày kết thúc")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="Ngày kết thúc phải sau hoặc bằng ngày bắt đầu.")

    code = data.ma_ct.strip()
    name = data.ten_ct.strip()
    description = data.mo_ta_cong_viec.strip()
    requirements = data.yeu_cau.strip()
    if not all((code, name, description, requirements)):
        raise HTTPException(status_code=400, detail="Vui lòng nhập đầy đủ thông tin chương trình.")

    return (
        code,
        name,
        data.ma_phong_ban,
        start_date,
        end_date,
        data.chi_tieu,
        description,
        requirements,
        data.quyen_loi.strip() if data.quyen_loi else None,
    )


def get_program(db: sqlite3.Connection, program_id: int):
    row = db.execute("""
        SELECT c.ma_chuong_trinh, c.ma_ct, c.ten_ct, c.ma_phong_ban,
               p.ten_phong_ban AS phong_ban, c.ngay_bat_dau, c.ngay_ket_thuc,
               c.chi_tieu, c.mo_ta_cong_viec, c.yeu_cau, c.quyen_loi, c.trang_thai,
               (SELECT COUNT(*) FROM UNG_TUYEN_CHUONG_TRINH a
                WHERE a.ma_chuong_trinh = c.ma_chuong_trinh) AS so_ung_vien,
               (SELECT COUNT(*) FROM UNG_TUYEN_CHUONG_TRINH a
                WHERE a.ma_chuong_trinh = c.ma_chuong_trinh AND a.trang_thai = 'ChoDuyet') AS so_cho_duyet
        FROM CHUONG_TRINH_THUC_TAP c
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = c.ma_phong_ban
        WHERE c.ma_chuong_trinh = ?
    """, (program_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy chương trình thực tập.")
    return row


@router.get("")
def list_programs(
    request: Request,
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, alias="pageSize", ge=1, le=100),
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request, "Admin", "HR", "ThucTapSinh")
    profile_id = None
    where_clause = ""
    if user["vai_tro"] == "ThucTapSinh":
        profile = db.execute(
            "SELECT ma_ho_so FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung = ?",
            (user["ma_nguoi_dung"],),
        ).fetchone()
        profile_id = profile["ma_ho_so"] if profile else None
        where_clause = "WHERE c.trang_thai = 'DangMo'"

    paginated = page is not None or page_size is not None
    effective_size = page_size or 10
    if paginated:
        count_clause = "WHERE c.trang_thai = 'DangMo'" if user["vai_tro"] == "ThucTapSinh" else ""
        total_items = db.execute(
            f"SELECT COUNT(*) AS total_items FROM CHUONG_TRINH_THUC_TAP c {count_clause}"
        ).fetchone()["total_items"]
        total_pages = (total_items + effective_size - 1) // effective_size if total_items else 0
        effective_page = min(page or 1, total_pages) if total_pages else 1
        limit_clause = " LIMIT ? OFFSET ?"
        paging_params = (effective_size, (effective_page - 1) * effective_size)
    else:
        total_items = total_pages = effective_page = None
        limit_clause = ""
        paging_params = ()
    rows = db.execute(f"""
        SELECT c.ma_chuong_trinh, c.ma_ct, c.ten_ct, c.ma_phong_ban,
               p.ten_phong_ban AS phong_ban, c.ngay_bat_dau, c.ngay_ket_thuc,
               c.chi_tieu, c.mo_ta_cong_viec, c.yeu_cau, c.quyen_loi, c.trang_thai,
               (SELECT COUNT(*) FROM UNG_TUYEN_CHUONG_TRINH a
                WHERE a.ma_chuong_trinh = c.ma_chuong_trinh) AS so_ung_vien,
               (SELECT COUNT(*) FROM UNG_TUYEN_CHUONG_TRINH a
                WHERE a.ma_chuong_trinh = c.ma_chuong_trinh AND a.trang_thai = 'ChoDuyet') AS so_cho_duyet,
               (SELECT a.trang_thai FROM UNG_TUYEN_CHUONG_TRINH a
                WHERE a.ma_chuong_trinh = c.ma_chuong_trinh AND a.ma_ho_so = ?) AS trang_thai_ung_tuyen
        FROM CHUONG_TRINH_THUC_TAP c
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = c.ma_phong_ban
        {where_clause}
        ORDER BY c.ma_chuong_trinh DESC
    """ + limit_clause, (profile_id, *paging_params)).fetchall()
    items = [dict(row) for row in rows]
    if not paginated:
        return items
    return {
        "items": items,
        "page": effective_page,
        "pageSize": effective_size,
        "totalItems": total_items,
        "totalPages": total_pages,
    }


@router.post("", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_program(data: ProgramCreate, request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin", "HR")
    values = validated_program_values(data)
    try:
        cursor = db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP
                (ma_ct, ten_ct, ma_phong_ban, ngay_bat_dau, ngay_ket_thuc,
                 chi_tieu, mo_ta_cong_viec, yeu_cau, quyen_loi)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, values)
        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Mã chương trình đã tồn tại hoặc phòng ban không hợp lệ.") from exc

    return {
        "message": f"Đã tạo chương trình {values[1]}.",
        "ma_chuong_trinh": cursor.lastrowid,
        "ma_ct": values[0],
    }


@router.put("/{program_id}", response_model=dict[str, Any])
def update_program(
    program_id: int,
    data: ProgramCreate,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    require_role(request, "Admin")
    get_program(db, program_id)
    values = validated_program_values(data)
    try:
        db.execute("""
            UPDATE CHUONG_TRINH_THUC_TAP
            SET ma_ct = ?, ten_ct = ?, ma_phong_ban = ?, ngay_bat_dau = ?,
                ngay_ket_thuc = ?, chi_tieu = ?, mo_ta_cong_viec = ?,
                yeu_cau = ?, quyen_loi = ?
            WHERE ma_chuong_trinh = ?
        """, (*values, program_id))
        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Mã chương trình đã tồn tại hoặc phòng ban không hợp lệ.") from exc
    return {"message": f"Đã cập nhật chương trình {values[1]}."}


@router.post("/{program_id}/close", response_model=dict[str, Any])
def close_program(program_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin")
    program = get_program(db, program_id)
    if program["trang_thai"] == "DaDong":
        return {"message": "Chương trình đã được đóng trước đó."}
    db.execute(
        "UPDATE CHUONG_TRINH_THUC_TAP SET trang_thai = 'DaDong' WHERE ma_chuong_trinh = ?",
        (program_id,),
    )
    applicants = db.execute("""
        SELECT DISTINCT h.ma_nguoi_dung
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
        WHERE a.ma_chuong_trinh = ?
    """, (program_id,)).fetchall()
    for applicant in applicants:
        create_notification(
            db,
            applicant["ma_nguoi_dung"],
            "Chương trình thực tập đã đóng",
            f"Chương trình {program['ten_ct']} đã ngừng nhận hồ sơ.",
        )
    db.commit()
    return {"message": f"Đã đóng chương trình {program['ten_ct']}."}


@router.post("/{program_id}/apply", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def apply_to_program(
    program_id: int, request: Request, cv: UploadFile | None = File(default=None),
    use_approved_profile: bool = Form(default=False),
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request, "ThucTapSinh")
    program = get_program(db, program_id)
    if program["trang_thai"] != "DangMo":
        raise HTTPException(status_code=400, detail="Chương trình đã ngừng nhận hồ sơ.")

    profile = db.execute("""
        SELECT h.ma_ho_so, h.trang_thai_xet_duyet
        FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE h.ma_nguoi_dung = ? AND u.vai_tro = 'ThucTapSinh'
    """, (user["ma_nguoi_dung"],)).fetchone()
    if not profile:
        raise HTTPException(status_code=400, detail="Tài khoản chưa có hồ sơ thực tập sinh hợp lệ.")

    filename = None
    extension = None
    content = None
    if use_approved_profile:
        if cv and cv.filename:
            raise HTTPException(status_code=400, detail="Chỉ chọn dùng hồ sơ đã duyệt hoặc tải CV mới.")
        if profile["trang_thai_xet_duyet"] != "DaDuyet":
            raise HTTPException(status_code=400, detail="Hồ sơ của bạn chưa được duyệt để dùng ứng tuyển.")
        approved_cv = db.execute("""
            SELECT ma_tai_lieu
            FROM TAI_LIEU_HO_SO
            WHERE ma_ho_so = ? AND loai_tai_lieu = 'CV' AND trang_thai_duyet = 'DaDuyet'
            ORDER BY ngay_tai_len DESC, ma_tai_lieu DESC
            LIMIT 1
        """, (profile["ma_ho_so"],)).fetchone()
        if not approved_cv:
            raise HTTPException(status_code=400, detail="Hồ sơ chưa có CV được duyệt để dùng ứng tuyển.")
    else:
        if not cv or not cv.filename:
            raise HTTPException(status_code=400, detail="Vui lòng chọn hồ sơ đã duyệt hoặc đính kèm CV mới.")
        filename = PurePosixPath(cv.filename.replace("\\", "/")).name
        extension = Path(filename).suffix.lower()
        if len(filename) > 255 or extension not in {".pdf", ".docx", ".png"}:
            raise HTTPException(status_code=400, detail="CV phải là tệp PDF, DOCX hoặc PNG có tên hợp lệ.")
        content = await cv.read(MAX_FILE_SIZE + 1)
        if not content or len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="CV phải có dung lượng từ 1 byte đến 15 MB.")
        if not valid_file_content(extension, content):
            raise HTTPException(status_code=400, detail="Nội dung tệp không khớp định dạng CV đã chọn.")

    absolute_path = None
    try:
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT 1 FROM UNG_TUYEN_CHUONG_TRINH WHERE ma_chuong_trinh=? AND ma_ho_so=?",
            (program_id, profile["ma_ho_so"]),
        ).fetchone():
            raise HTTPException(status_code=400, detail="Bạn đã ứng tuyển chương trình này.")

        if not use_approved_profile:
            storage_name = f"{uuid4().hex}{extension}"
            absolute_path = UPLOAD_ROOT / storage_name
            UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
            with absolute_path.open("xb") as stored_file:
                stored_file.write(content)
            db.execute("""
                INSERT INTO TAI_LIEU_HO_SO
                    (ma_ho_so, loai_tai_lieu, duong_dan_file, ten_file, kich_thuoc)
                VALUES (?, 'CV', ?, ?, ?)
            """, (profile["ma_ho_so"], PurePosixPath("documents", storage_name).as_posix(), filename, len(content)))
        cursor = db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai)
            VALUES (?, ?, 'ChoDuyet')
        """, (program_id, profile["ma_ho_so"]))
        managers = db.execute("""
            SELECT ma_nguoi_dung FROM NGUOI_DUNG
            WHERE vai_tro IN ('Admin', 'HR') AND trang_thai = 'HoatDong'
        """).fetchall()
        for manager in managers:
            create_notification(
                db, manager["ma_nguoi_dung"], "Ứng viên chương trình mới",
                f"{user['ho_ten']} vừa ứng tuyển chương trình {program['ten_ct']} và đang chờ duyệt.",
            )
        db.commit()
    except HTTPException:
        db.rollback()
        if absolute_path:
            absolute_path.unlink(missing_ok=True)
        raise
    except sqlite3.IntegrityError as exc:
        db.rollback()
        if absolute_path:
            absolute_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Bạn đã ứng tuyển chương trình này.") from exc
    except Exception:
        db.rollback()
        if absolute_path:
            absolute_path.unlink(missing_ok=True)
        raise
    finally:
        if cv is not None:
            await cv.close()
    return {
        "message": (
            "Đã gửi hồ sơ đã được duyệt. Đơn ứng tuyển đang chờ duyệt."
            if use_approved_profile
            else "Đã ghi nhận hồ sơ. Đơn ứng tuyển đang chờ duyệt."
        ),
        "ma_ung_tuyen": cursor.lastrowid,
        "trang_thai": "ChoDuyet",
        "su_dung_ho_so_da_duyet": use_approved_profile,
    }


@router.get("/{program_id}/applications")
def list_program_applications(
    program_id: int,
    request: Request,
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, alias="pageSize", ge=1, le=100),
    db: sqlite3.Connection = Depends(get_db),
):
    require_role(request, "Admin", "HR")
    get_program(db, program_id)
    paginated = page is not None or page_size is not None
    effective_size = page_size or 10
    if paginated:
        total_items = db.execute("""
        SELECT COUNT(*) AS total_items
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE a.ma_chuong_trinh = ? AND u.vai_tro = 'ThucTapSinh'
        """, (program_id,)).fetchone()["total_items"]
        total_pages = (total_items + effective_size - 1) // effective_size if total_items else 0
        effective_page = min(page or 1, total_pages) if total_pages else 1
        limit_clause = " LIMIT ? OFFSET ?"
        paging_params = (effective_size, (effective_page - 1) * effective_size)
    else:
        total_items = total_pages = effective_page = None
        limit_clause = ""
        paging_params = ()
    rows = db.execute("""
        SELECT a.ma_ung_tuyen, a.ma_chuong_trinh, a.ma_ho_so,
               u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               t.ten_truong, h.chuyen_nganh, a.trang_thai,
               a.ngay_ung_tuyen, a.ngay_xet_duyet
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        LEFT JOIN TRUONG_DAI_HOC t ON t.ma_truong = h.ma_truong
        WHERE a.ma_chuong_trinh = ? AND u.vai_tro = 'ThucTapSinh'
        ORDER BY CASE a.trang_thai WHEN 'ChoDuyet' THEN 0 WHEN 'DaDuyet' THEN 1 ELSE 2 END,
                 a.ngay_ung_tuyen DESC, a.ma_ung_tuyen DESC
    """ + limit_clause, (program_id, *paging_params)).fetchall()
    items = [dict(row) for row in rows]
    if not paginated:
        return items
    return {
        "items": items,
        "page": effective_page,
        "pageSize": effective_size,
        "totalItems": total_items,
        "totalPages": total_pages,
    }


@router.put("/{program_id}/applications/{application_id}", response_model=dict[str, Any])
def review_program_application(
    program_id: int,
    application_id: int,
    data: ProgramApplicationReview,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    reviewer = require_role(request, "Admin", "HR")
    if database_module.DATABASE_BACKEND == "sqlite":
        db.execute("BEGIN IMMEDIATE")
    else:
        db.execute(
            "SELECT ma_chuong_trinh FROM CHUONG_TRINH_THUC_TAP WHERE ma_chuong_trinh = ? FOR UPDATE",
            (program_id,),
        ).fetchone()
    program = get_program(db, program_id)
    application = db.execute("""
        SELECT a.ma_ung_tuyen, a.trang_thai, h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten, u.email
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE a.ma_ung_tuyen = ? AND a.ma_chuong_trinh = ?
    """, (application_id, program_id)).fetchone()
    if not application:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn ứng tuyển.")
    if application["trang_thai"] != "ChoDuyet":
        raise HTTPException(status_code=400, detail="Đơn ứng tuyển này đã được xử lý trước đó.")

    if data.trang_thai == "DaDuyet":
        approved_count = db.execute("""
            SELECT COUNT(*) FROM UNG_TUYEN_CHUONG_TRINH
            WHERE ma_chuong_trinh = ? AND trang_thai = 'DaDuyet'
        """, (program_id,)).fetchone()[0]
        if approved_count >= program["chi_tieu"]:
            raise HTTPException(status_code=400, detail="Chương trình đã đủ chỉ tiêu được duyệt.")

    cursor = db.execute("""
        UPDATE UNG_TUYEN_CHUONG_TRINH
        SET trang_thai = ?, ngay_xet_duyet = CURRENT_TIMESTAMP, nguoi_xet_duyet = ?
        WHERE ma_ung_tuyen = ? AND ma_chuong_trinh = ? AND trang_thai = 'ChoDuyet'
    """, (data.trang_thai, reviewer["ma_nguoi_dung"], application_id, program_id))
    if cursor.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Đơn ứng tuyển vừa được HR/Admin khác xử lý. Tải lại danh sách trước khi thử lại.",
        )

    approved = data.trang_thai == "DaDuyet"
    rejection_reason = _email_value(data.reject_reason, "") if not approved else ""
    company_name = _email_value(os.getenv("IMS_COMPANY_NAME"), "IMS Portal")
    student_name = _email_value(application["ho_ten"], "Ứng viên")
    program_name = _email_value(program["ten_ct"], "Chương trình thực tập")
    portal_url = _email_value(os.getenv("IMS_PORTAL_URL"), "")
    email_subject = f"[{company_name}] Thông báo kết quả xét duyệt hồ sơ thực tập sinh - {student_name}"[:255]
    if approved:
        mentor = db.execute("""
            SELECT u.ho_ten
            FROM PHAN_CONG_MENTOR_TTS assignment
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = assignment.ma_nguoi_dung_mentor
            WHERE assignment.ma_ho_so = ? AND u.vai_tro = 'Mentor'
            LIMIT 1
        """, (application["ma_ho_so"],)).fetchone()
        email_lines = [
            f"Xin chào {student_name},",
            "",
            f"Chúc mừng bạn đã được duyệt vào chương trình {program_name}.",
            f"Chương trình/vị trí: {program_name}",
            f"Đơn vị tiếp nhận: {company_name}",
            f"Phòng ban: {_email_value(program['phong_ban'])}",
            f"Thời gian dự kiến: {_email_date(program['ngay_bat_dau'])} đến {_email_date(program['ngay_ket_thuc'])}",
        ]
        if mentor:
            email_lines.append(f"Mentor hiện tại: {_email_value(mentor['ho_ten'])}")
        email_lines.extend([
            (f"Đăng nhập IMS Portal tại: {portal_url}" if portal_url
             else "Đăng nhập IMS Portal bằng địa chỉ hệ thống đã được đơn vị cung cấp."),
            "Bước tiếp theo: kiểm tra thông báo trong IMS Portal và xác nhận lịch nhận việc với bộ phận Nhân sự.",
            "Bộ phận Nhân sự sẽ hướng dẫn xác nhận hồ sơ và ký thỏa thuận/hợp đồng trước ngày bắt đầu.",
            "Bạn không cần gửi lại CV đã nộp; nếu cần bổ sung tài liệu, Nhân sự sẽ thông báo riêng.",
            "",
        ])
    else:
        email_lines = [
            f"Xin chào {student_name},",
            "",
            f"Cảm ơn bạn đã ứng tuyển chương trình {program_name} tại {company_name}.",
            "Rất tiếc, hồ sơ của bạn chưa được chọn trong đợt xét duyệt này.",
        ]
        if rejection_reason:
            email_lines.extend(["", f"Ghi chú từ HR: {rejection_reason}"])
        email_lines.extend([
            "Chúng tôi sẽ lưu hồ sơ của bạn để cân nhắc cho cơ hội phù hợp trong tương lai.",
            "Bạn có thể tiếp tục theo dõi các chương trình khác trên IMS Portal.",
            "",
        ])
    email_lines.extend(["Trân trọng,", f"Bộ phận Nhân sự - {company_name}"])
    notification_message = f"Đơn ứng tuyển {program_name} của bạn đã {'được duyệt' if approved else 'bị từ chối'}."
    if rejection_reason:
        notification_message += f" Lý do: {rejection_reason}"
    create_notification(
        db,
        application["ma_nguoi_dung"],
        "Kết quả ứng tuyển chương trình",
        notification_message,
        notification_type="program_application_result",
        reference_type="program_application", reference_id=application_id,
        email_recipient=application["email"],
        email_deduplication_key=f"us08:program_application:{application_id}:{data.trang_thai}",
        email_reference_type="program_application",
        email_reference_id=application_id,
        email_subject=email_subject,
        email_body="\n".join(email_lines),
    )
    db.commit()
    return {"message": f"Đã {'duyệt' if approved else 'từ chối'} ứng viên {application['ho_ten']}."}


@router.get("/{program_id}", response_model=ProgramDetail)
def program_detail(program_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request, "Admin", "HR", "ThucTapSinh")
    program = dict(get_program(db, program_id))
    if user["vai_tro"] == "ThucTapSinh":
        application = db.execute("""
            SELECT a.trang_thai
            FROM UNG_TUYEN_CHUONG_TRINH a
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
            WHERE a.ma_chuong_trinh = ? AND h.ma_nguoi_dung = ?
        """, (program_id, user["ma_nguoi_dung"])).fetchone()
        program["trang_thai_ung_tuyen"] = application["trang_thai"] if application else None
    return program
