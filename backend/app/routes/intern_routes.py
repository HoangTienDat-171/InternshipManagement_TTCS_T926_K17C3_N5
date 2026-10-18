from fastapi import APIRouter, HTTPException, Depends, status, Query, Request
import sqlite3
import re
import math
from datetime import date
from typing import List, Optional, Dict, Any
from ..database import get_db, hash_password
from ..account_credentials import create_temporary_password, queue_temporary_password_email, require_password_change_schema
from ..schemas import InternCreate, InternUpdate, InternDetail
from ..security import require_role
from ..personal_schedule import PersonalScheduleService

router = APIRouter(prefix="/api/interns", tags=["Intern Profile - US01, US02, US03"])


def _validate_master_catalog_item(db, *, item_id: int | None, meta_table: str, id_column: str, label: str, unchanged_id: int | None = None) -> None:
    if item_id is None:
        return
    try:
        row = db.execute(
            f"SELECT is_active FROM {meta_table} WHERE {id_column} = ?", (item_id,)
        ).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Danh mục chưa sẵn sàng; quản trị viên cần áp dụng migration master-data.") from exc
    if not row:
        raise HTTPException(status_code=422, detail=f"{label} đã chọn không tồn tại trong danh mục IMS.")
    if not bool(row["is_active"]) and item_id != unchanged_id:
        raise HTTPException(status_code=422, detail=f"{label} đã ngừng sử dụng; hãy chọn mục đang hoạt động.")


@router.get("/me/schedule")
def intern_personal_schedule(
    request: Request,
    week_start: date | None = Query(None),
    program_id: int | None = Query(None, ge=1),
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request, "ThucTapSinh")
    return PersonalScheduleService(db).get_for_intern(
        user["ma_nguoi_dung"], week_start=week_start, program_id=program_id,
    )


@router.get("/me/workspace")
def intern_workspace(request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request, "ThucTapSinh")
    profile = db.execute("""
        SELECT h.ma_ho_so, h.ma_nguoi_dung, h.ma_truong, t.ten_truong,
               h.chuyen_nganh, h.trang_thai_xet_duyet,
               CASE WHEN h.trang_thai_xet_duyet = 'DaDuyet' THEN h.trang_thai_thuc_tap ELSE NULL END AS trang_thai_thuc_tap,
               u.ho_ten, u.email, u.so_dien_thoai, p.ten_phong_ban AS phong_ban
        FROM HO_SO_THUC_TAP h JOIN NGUOI_DUNG u ON u.ma_nguoi_dung=h.ma_nguoi_dung
        LEFT JOIN TRUONG_DAI_HOC t ON t.ma_truong=h.ma_truong
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban=u.ma_phong_ban
        WHERE h.ma_nguoi_dung=? AND u.vai_tro='ThucTapSinh'
    """, (user["ma_nguoi_dung"],)).fetchone()
    if not profile:
        raise HTTPException(status_code=404, detail="Tài khoản chưa có hồ sơ thực tập sinh.")

    from ..mentor_assignment_service import (
        get_intern_active_assignment,
        get_intern_active_program,
        get_timeline_status,
    )

    active_assignment = get_intern_active_assignment(db, profile["ma_ho_so"])
    mentor = None
    if active_assignment:
        mentor_row = db.execute("""
            SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
                   p.ten_phong_ban AS phong_ban, mp.chuyen_mon, mp.kinh_nghiem
            FROM NGUOI_DUNG u
            LEFT JOIN PHONG_BAN p ON p.ma_phong_ban=u.ma_phong_ban
            LEFT JOIN MENTOR_PROFILE mp ON mp.ma_nguoi_dung=u.ma_nguoi_dung
            WHERE u.ma_nguoi_dung=? AND u.vai_tro='Mentor'
        """, (active_assignment["ma_nguoi_dung"],)).fetchone()
        mentor = dict(mentor_row) if mentor_row else None

    documents = db.execute("""
        SELECT d.ma_tai_lieu, d.ma_ho_so, d.ten_file, d.loai_tai_lieu, d.kich_thuoc,
               d.ngay_tai_len, d.trang_thai_duyet, d.reviewed_by,
               reviewer.ho_ten AS reviewer_name, d.reviewed_at, d.review_reason
        FROM TAI_LIEU_HO_SO d
        LEFT JOIN NGUOI_DUNG reviewer ON reviewer.ma_nguoi_dung=d.reviewed_by
        WHERE d.ma_ho_so=? ORDER BY d.ngay_tai_len DESC, d.ma_tai_lieu DESC
    """, (profile["ma_ho_so"],)).fetchall()

    raw_apps = db.execute("""
        SELECT c.ma_chuong_trinh, c.ma_ct, c.ten_ct, c.ngay_bat_dau, c.ngay_ket_thuc, c.trang_thai AS trang_thai_ct,
               a.trang_thai AS trang_thai_ung_tuyen, a.ngay_ung_tuyen,
               m.ma_nguoi_dung AS mentor_id, m.ho_ten AS mentor_name, m.email AS mentor_email
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh=a.ma_chuong_trinh
        LEFT JOIN PHAN_CONG_MENTOR_TTS p ON p.ma_ho_so = a.ma_ho_so
             AND (p.ma_chuong_trinh = a.ma_chuong_trinh OR (p.ma_chuong_trinh IS NULL AND p.ma_ho_so = a.ma_ho_so))
        LEFT JOIN NGUOI_DUNG m ON m.ma_nguoi_dung = p.ma_nguoi_dung_mentor AND m.vai_tro = 'Mentor'
        WHERE a.ma_ho_so=? ORDER BY a.ngay_ung_tuyen DESC
    """, (profile["ma_ho_so"],)).fetchall()

    applications = []
    for app in raw_apps:
        item = dict(app)
        item["timeline_status"] = get_timeline_status(
            app["ngay_bat_dau"], app["ngay_ket_thuc"], app["trang_thai_ct"]
        )
        applications.append(item)

    active_prog = get_intern_active_program(db, profile["ma_ho_so"])
    current_program = active_prog if active_prog else next(
        (
            app for app in applications
            if app["trang_thai_ung_tuyen"] == "DaDuyet"
            and app["timeline_status"] != "HISTORICAL"
        ),
        None,
    )

    progress = None
    if current_program and current_program.get("ngay_bat_dau") and current_program.get("ngay_ket_thuc"):
        start = date.fromisoformat(str(current_program["ngay_bat_dau"])[:10])
        end = date.fromisoformat(str(current_program["ngay_ket_thuc"])[:10])
        total_days = max(1, (end - start).days)
        elapsed_days = min(total_days, max(0, (date.today() - start).days))
        progress = round(elapsed_days * 100 / total_days)

    return {
        "profile": dict(profile), "mentor": mentor,
        "documents": [dict(row) for row in documents],
        "applications": applications,
        "current_program": current_program, "progress_percent": progress,
    }

def validate_phone_number(phone: Optional[str]):
    if phone and not re.fullmatch(r"(03|05|07|08|09)\d{8}", phone):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 03, 05, 07, 08 hoặc 09.")

@router.post("", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_intern(data: InternCreate, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """
    US01 – Thêm mới hồ sơ thực tập sinh (Quản lý hồ sơ)
    Viết API lưu thông tin vào CSDL (Backend).
    Tạo tài khoản NGUOI_DUNG với vai_tro='ThucTapSinh' và tạo bản ghi HO_SO_THUC_TAP.
    """
    require_role(request, "Admin", "HR")
    require_password_change_schema(db)
    validate_phone_number(data.so_dien_thoai)
    _validate_master_catalog_item(
        db, item_id=data.ma_phong_ban, meta_table="IMS_DEPARTMENT_CATALOG_META",
        id_column="ma_phong_ban", label="Phòng ban",
    )
    _validate_master_catalog_item(
        db, item_id=data.ma_truong, meta_table="IMS_UNIVERSITY_CATALOG_META",
        id_column="ma_truong", label="Trường đại học",
    )
    email = data.email.strip().lower()
    cursor = db.cursor()

    # Kiểm tra email trùng
    cursor.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE LOWER(email) = ?", (email,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email '{data.email}' đã tồn tại trong hệ thống!"
        )

    # 1. Tạo tài khoản trong NGUOI_DUNG
    temporary_password = create_temporary_password()
    hashed_pw = hash_password(temporary_password)
    cursor.execute("""
        INSERT INTO NGUOI_DUNG
            (ma_phong_ban, ho_ten, email, mat_khau, must_change_password, so_dien_thoai, vai_tro, trang_thai)
        VALUES (?, ?, ?, ?, 1, ?, 'ThucTapSinh', 'HoatDong')
    """, (data.ma_phong_ban, data.ho_ten.strip(), email, hashed_pw, data.so_dien_thoai))
    
    ma_nguoi_dung = cursor.lastrowid

    # 2. Tạo hồ sơ trong HO_SO_THUC_TAP
    cursor.execute("""
        INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
        VALUES (?, ?, ?, ?, ?)
    """, (
        ma_nguoi_dung,
        data.ma_truong,
        data.chuyen_nganh,
        'DaDuyet',
        data.trang_thai_thuc_tap or 'DangThucTap'
    ))

    ma_ho_so = cursor.lastrowid
    queue_temporary_password_email(db, ma_nguoi_dung, data.ho_ten.strip(), email, temporary_password)
    db.commit()

    return {
        "message": "Đã tạo tài khoản thực tập sinh; email mật khẩu tạm đang được gửi.",
        "ma_ho_so": ma_ho_so,
        "ma_nguoi_dung": ma_nguoi_dung,
        "ho_ten": data.ho_ten,
        "email": email
    }

@router.get("/{id}", response_model=InternDetail)
def get_intern_by_id(id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """
    US02 – Cập nhật/Chỉnh sửa hồ sơ thực tập sinh (Quản lý hồ sơ)
    Viết API lấy thông tin chi tiết theo ID thực tập sinh (ma_ho_so hoặc ma_nguoi_dung).
    """
    require_role(request, "Admin", "HR")
    cursor = db.cursor()
    cursor.execute("""
        SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               u.ma_phong_ban, p.ten_phong_ban, u.trang_thai AS trang_thai_tai_khoan,
               h.ma_truong, t.ten_truong, h.chuyen_nganh, h.trang_thai_xet_duyet,
               CASE WHEN h.trang_thai_xet_duyet = 'DaDuyet' THEN h.trang_thai_thuc_tap ELSE NULL END AS trang_thai_thuc_tap,
               h.ngay_tao
        FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON h.ma_nguoi_dung = u.ma_nguoi_dung
        LEFT JOIN PHONG_BAN p ON u.ma_phong_ban = p.ma_phong_ban
        LEFT JOIN TRUONG_DAI_HOC t ON h.ma_truong = t.ma_truong
        WHERE h.ma_ho_so = ? AND u.vai_tro = 'ThucTapSinh'
    """, (id,))
    
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy hồ sơ thực tập sinh với ID = {id}"
        )

    detail = dict(row)

    # A profile can participate in several programs. Keep each approved
    # application as its own detail row and associate only the assignment for
    # that program; never select an arbitrary historical Mentor for the profile.
    from ..mentor_assignment_service import get_timeline_status

    program_rows = db.execute("""
        SELECT a.ma_ung_tuyen, a.ma_chuong_trinh,
               c.ma_ct, c.ten_ct, c.ngay_bat_dau, c.ngay_ket_thuc,
               c.trang_thai AS trang_thai_chuong_trinh,
               mentor.ma_nguoi_dung AS mentor_ma_nguoi_dung,
               mentor.ho_ten AS mentor_ho_ten, mentor.email AS mentor_email,
               mentor.so_dien_thoai AS mentor_so_dien_thoai,
               mentor_department.ten_phong_ban AS mentor_phong_ban,
               mp.chuyen_mon AS mentor_chuyen_mon, mp.kinh_nghiem AS mentor_kinh_nghiem,
               assignment.ngay_phan_cong
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
        LEFT JOIN PHAN_CONG_MENTOR_TTS assignment
            ON assignment.ma_ho_so = a.ma_ho_so
            AND assignment.ma_chuong_trinh = a.ma_chuong_trinh
        LEFT JOIN NGUOI_DUNG mentor
            ON mentor.ma_nguoi_dung = assignment.ma_nguoi_dung_mentor
            AND mentor.vai_tro = 'Mentor'
        LEFT JOIN PHONG_BAN mentor_department
            ON mentor_department.ma_phong_ban = mentor.ma_phong_ban
        LEFT JOIN MENTOR_PROFILE mp ON mp.ma_nguoi_dung = mentor.ma_nguoi_dung
        WHERE a.ma_ho_so = ? AND a.trang_thai = 'DaDuyet'
        ORDER BY c.ngay_bat_dau ASC, c.ma_chuong_trinh ASC, a.ma_ung_tuyen ASC
    """, (id,)).fetchall()

    programs = []
    for program_row in program_rows:
        program = dict(program_row)
        program["ngay_bat_dau"] = str(program["ngay_bat_dau"]) if program["ngay_bat_dau"] else None
        program["ngay_ket_thuc"] = str(program["ngay_ket_thuc"]) if program["ngay_ket_thuc"] else None
        program["ngay_phan_cong"] = str(program["ngay_phan_cong"]) if program["ngay_phan_cong"] else None
        program["timeline_status"] = get_timeline_status(
            program["ngay_bat_dau"], program["ngay_ket_thuc"], program["trang_thai_chuong_trinh"]
        )
        programs.append(program)

    unscoped_assignments = db.execute("""
        SELECT mentor.ma_nguoi_dung AS mentor_ma_nguoi_dung,
               mentor.ho_ten AS mentor_ho_ten, mentor.email AS mentor_email,
               mentor.so_dien_thoai AS mentor_so_dien_thoai,
               mentor_department.ten_phong_ban AS mentor_phong_ban,
               mp.chuyen_mon AS mentor_chuyen_mon, mp.kinh_nghiem AS mentor_kinh_nghiem,
               assignment.ngay_phan_cong
        FROM PHAN_CONG_MENTOR_TTS assignment
        JOIN NGUOI_DUNG mentor
            ON mentor.ma_nguoi_dung = assignment.ma_nguoi_dung_mentor
            AND mentor.vai_tro = 'Mentor'
        LEFT JOIN PHONG_BAN mentor_department
            ON mentor_department.ma_phong_ban = mentor.ma_phong_ban
        LEFT JOIN MENTOR_PROFILE mp ON mp.ma_nguoi_dung = mentor.ma_nguoi_dung
        WHERE assignment.ma_ho_so = ? AND assignment.ma_chuong_trinh IS NULL
        ORDER BY assignment.ngay_phan_cong DESC, assignment.ma_phan_cong DESC
    """, (id,)).fetchall()

    detail["chuong_trinh_tham_gia"] = programs
    detail["mentor_chua_gan_chuong_trinh"] = [
        {**dict(assignment_row), "ngay_phan_cong": str(assignment_row["ngay_phan_cong"]) if assignment_row["ngay_phan_cong"] else None}
        for assignment_row in unscoped_assignments
    ]

    # Keep the legacy flat Mentor fields scoped to the currently active
    # program only. Historical assignments remain available in the arrays.
    active_program = next(
        (program for program in programs if program["timeline_status"] == "CURRENT"),
        None,
    )
    if active_program:
        for field in (
            "mentor_ma_nguoi_dung", "mentor_ho_ten", "mentor_email",
            "mentor_so_dien_thoai", "mentor_phong_ban", "mentor_chuyen_mon",
            "mentor_kinh_nghiem",
        ):
            detail[field] = active_program.get(field)
    return detail

@router.put("/{id}", response_model=Dict[str, Any])
def update_intern(id: int, data: InternUpdate, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """
    US02 – Cập nhật/Chỉnh sửa hồ sơ thực tập sinh (Quản lý hồ sơ)
    Viết API Cập nhật (Update) dữ liệu.
    """
    require_role(request, "Admin", "HR")
    validate_phone_number(data.so_dien_thoai)
    cursor = db.cursor()
    
    # Kiểm tra hồ sơ có tồn tại không
    cursor.execute("""
        SELECT h.ma_ho_so, h.ma_nguoi_dung, h.ma_truong, u.ma_phong_ban,
               h.trang_thai_xet_duyet, h.trang_thai_thuc_tap
        FROM HO_SO_THUC_TAP h JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE h.ma_ho_so = ? AND u.vai_tro = 'ThucTapSinh'
    """, (id,))
    record = cursor.fetchone()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy hồ sơ thực tập sinh với ID = {id}"
        )

    ma_nguoi_dung = record["ma_nguoi_dung"]

    _validate_master_catalog_item(
        db, item_id=data.ma_phong_ban, meta_table="IMS_DEPARTMENT_CATALOG_META",
        id_column="ma_phong_ban", label="Phòng ban", unchanged_id=record["ma_phong_ban"],
    )
    _validate_master_catalog_item(
        db, item_id=data.ma_truong, meta_table="IMS_UNIVERSITY_CATALOG_META",
        id_column="ma_truong", label="Trường đại học", unchanged_id=record["ma_truong"],
    )

    # Kiểm tra nếu đổi email thì email mới không được trùng với người dùng khác
    cursor.execute("""
        SELECT ma_nguoi_dung FROM NGUOI_DUNG
        WHERE LOWER(email) = LOWER(?) AND ma_nguoi_dung != ?
    """, (data.email.strip().lower(), ma_nguoi_dung))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email '{data.email}' đã được sử dụng bởi người dùng khác!"
        )

    # Approval is intentionally immutable here. Only the dedicated approve/reject
    # endpoints may change review state, account access, notifications, or email.
    internship_status = record["trang_thai_thuc_tap"]
    if record["trang_thai_xet_duyet"] == "DaDuyet" and data.trang_thai_thuc_tap is not None:
        internship_status = data.trang_thai_thuc_tap
    cursor.execute("""
        UPDATE HO_SO_THUC_TAP
        SET ma_truong = ?, chuyen_nganh = ?, trang_thai_thuc_tap = ?
        WHERE ma_ho_so = ?
    """, (data.ma_truong, data.chuyen_nganh, internship_status, id))

    # 2. Cập nhật thông tin tài khoản
    cursor.execute("""
        UPDATE NGUOI_DUNG
        SET ho_ten = ?, email = ?, so_dien_thoai = ?, ma_phong_ban = ?
        WHERE ma_nguoi_dung = ?
    """, (data.ho_ten.strip(), data.email.strip().lower(), data.so_dien_thoai, data.ma_phong_ban, ma_nguoi_dung))

    db.commit()

    return {
        "message": "Cập nhật hồ sơ thực tập sinh thành công!",
        "ma_ho_so": id,
        "ho_ten": data.ho_ten,
        "email": data.email.strip().lower()
    }

@router.get("")
def list_interns(
    request: Request,
    search: Optional[str] = Query(None, description="Tìm kiếm theo họ tên, email, chuyên ngành"),
    trang_thai_xet_duyet: Optional[str] = Query(None, description="Lọc theo ChoDuyet, DaDuyet, TuChoi"),
    trang_thai_thuc_tap: Optional[str] = Query(None, description="Lọc theo DangThucTap, HoanThanh, ThoiHoc"),
    ma_phong_ban: Optional[int] = Query(None, description="Lọc theo phòng ban"),
    ma_truong: Optional[int] = Query(None, description="Lọc theo trường đại học"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=100),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Hỗ trợ giao diện US03 – Tìm kiếm & Lọc danh sách thực tập sinh
    """
    require_role(request, "Admin", "HR")
    from_clause = """
        FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON h.ma_nguoi_dung = u.ma_nguoi_dung
        LEFT JOIN PHONG_BAN p ON u.ma_phong_ban = p.ma_phong_ban
        LEFT JOIN TRUONG_DAI_HOC t ON h.ma_truong = t.ma_truong
        WHERE u.vai_tro = 'ThucTapSinh'
    """
    filters = []
    params = []

    if search:
        filters.append("(u.ho_ten LIKE ? OR u.email LIKE ? OR h.chuyen_nganh LIKE ?)")
        keyword = f"%{search}%"
        params.extend([keyword, keyword, keyword])

    if trang_thai_xet_duyet:
        filters.append("h.trang_thai_xet_duyet = ?")
        params.append(trang_thai_xet_duyet)

    if trang_thai_thuc_tap:
        filters.append("h.trang_thai_xet_duyet = 'DaDuyet' AND h.trang_thai_thuc_tap = ?")
        params.append(trang_thai_thuc_tap)

    if ma_phong_ban:
        filters.append("u.ma_phong_ban = ?")
        params.append(ma_phong_ban)

    if ma_truong:
        filters.append("h.ma_truong = ?")
        params.append(ma_truong)

    if filters:
        from_clause += " AND " + " AND ".join(filters)

    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) AS total_items " + from_clause, params)
    total_items = cursor.fetchone()["total_items"]
    total_pages = math.ceil(total_items / page_size) if total_items else 0
    effective_page = min(page, total_pages) if total_pages else 1
    offset = (effective_page - 1) * page_size

    query = """
        SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               u.ma_phong_ban, p.ten_phong_ban, u.trang_thai AS trang_thai_tai_khoan,
               h.ma_truong, t.ten_truong,
               h.chuyen_nganh, h.trang_thai_xet_duyet,
               CASE WHEN h.trang_thai_xet_duyet = 'DaDuyet' THEN h.trang_thai_thuc_tap ELSE NULL END AS trang_thai_thuc_tap,
               h.ngay_tao,
               (SELECT e.status
                FROM EMAIL_OUTBOX e
                WHERE (e.reference_type = 'intern_profile'
                       AND e.reference_id = CAST(h.ma_ho_so AS CHAR))
                   OR (e.reference_type = 'account'
                       AND e.reference_id = CAST(h.ma_nguoi_dung AS CHAR)
                       AND e.template_type = 'temporary_credentials')
                ORDER BY e.id DESC LIMIT 1) AS email_status
    """
    query += from_clause + " ORDER BY h.ma_ho_so DESC LIMIT ? OFFSET ?"
    cursor.execute(query, [*params, page_size, offset])
    rows = cursor.fetchall()
    return {
        "items": [dict(row) for row in rows],
        "page": effective_page,
        "pageSize": page_size,
        "totalItems": total_items,
        "totalPages": total_pages,
    }
