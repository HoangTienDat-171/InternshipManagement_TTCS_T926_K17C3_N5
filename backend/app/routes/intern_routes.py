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

    mentor = db.execute("""
        SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               p.ten_phong_ban AS phong_ban, mp.chuyen_mon, mp.kinh_nghiem
        FROM PHAN_CONG_MENTOR_TTS a JOIN NGUOI_DUNG u ON u.ma_nguoi_dung=a.ma_nguoi_dung_mentor
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban=u.ma_phong_ban
        LEFT JOIN MENTOR_PROFILE mp ON mp.ma_nguoi_dung=u.ma_nguoi_dung
        WHERE a.ma_ho_so=? AND u.vai_tro='Mentor'
    """, (profile["ma_ho_so"],)).fetchone()
    documents = db.execute("""
        SELECT d.ma_tai_lieu, d.ma_ho_so, d.ten_file, d.loai_tai_lieu, d.kich_thuoc,
               d.ngay_tai_len, d.trang_thai_duyet, d.reviewed_by,
               reviewer.ho_ten AS reviewer_name, d.reviewed_at, d.review_reason
        FROM TAI_LIEU_HO_SO d
        LEFT JOIN NGUOI_DUNG reviewer ON reviewer.ma_nguoi_dung=d.reviewed_by
        WHERE d.ma_ho_so=? ORDER BY d.ngay_tai_len DESC, d.ma_tai_lieu DESC
    """, (profile["ma_ho_so"],)).fetchall()
    applications = db.execute("""
        SELECT a.ma_ung_tuyen, c.ma_chuong_trinh, c.ma_ct, c.ten_ct, c.ngay_bat_dau, c.ngay_ket_thuc,
               a.trang_thai AS trang_thai_ung_tuyen, a.ngay_ung_tuyen
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh=a.ma_chuong_trinh
        WHERE a.ma_ho_so=? ORDER BY a.ngay_ung_tuyen DESC
    """, (profile["ma_ho_so"],)).fetchall()
    current_program = next((dict(row) for row in applications if row["trang_thai_ung_tuyen"] == "DaDuyet"), None)
    progress = None
    if current_program and current_program["ngay_bat_dau"] and current_program["ngay_ket_thuc"]:
        start = date.fromisoformat(str(current_program["ngay_bat_dau"])[:10])
        end = date.fromisoformat(str(current_program["ngay_ket_thuc"])[:10])
        total_days = max(1, (end - start).days)
        elapsed_days = min(total_days, max(0, (date.today() - start).days))
        progress = round(elapsed_days * 100 / total_days)
    return {
        "profile": dict(profile), "mentor": dict(mentor) if mentor else None,
        "documents": [dict(row) for row in documents],
        "applications": [dict(row) for row in applications],
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
               h.ngay_tao,
               mentor.ma_nguoi_dung AS mentor_ma_nguoi_dung,
               mentor.ho_ten AS mentor_ho_ten, mentor.email AS mentor_email,
               mentor.so_dien_thoai AS mentor_so_dien_thoai,
               mentor_department.ten_phong_ban AS mentor_phong_ban,
               mp.chuyen_mon AS mentor_chuyen_mon, mp.kinh_nghiem AS mentor_kinh_nghiem
        FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON h.ma_nguoi_dung = u.ma_nguoi_dung
        LEFT JOIN PHONG_BAN p ON u.ma_phong_ban = p.ma_phong_ban
        LEFT JOIN TRUONG_DAI_HOC t ON h.ma_truong = t.ma_truong
        LEFT JOIN PHAN_CONG_MENTOR_TTS assignment ON assignment.ma_ho_so = h.ma_ho_so
        LEFT JOIN NGUOI_DUNG mentor ON mentor.ma_nguoi_dung = assignment.ma_nguoi_dung_mentor
            AND mentor.vai_tro = 'Mentor'
        LEFT JOIN PHONG_BAN mentor_department ON mentor_department.ma_phong_ban = mentor.ma_phong_ban
        LEFT JOIN MENTOR_PROFILE mp ON mp.ma_nguoi_dung = mentor.ma_nguoi_dung
        WHERE h.ma_ho_so = ? AND u.vai_tro = 'ThucTapSinh'
    """, (id,))
    
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy hồ sơ thực tập sinh với ID = {id}"
        )

    return dict(row)

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
        SELECT h.ma_ho_so, h.ma_nguoi_dung, h.trang_thai_xet_duyet, h.trang_thai_thuc_tap
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
        LEFT JOIN PHAN_CONG_MENTOR_TTS assignment ON assignment.ma_ho_so = h.ma_ho_so
        LEFT JOIN NGUOI_DUNG mentor ON mentor.ma_nguoi_dung = assignment.ma_nguoi_dung_mentor
            AND mentor.vai_tro = 'Mentor'
        LEFT JOIN PHONG_BAN mentor_department ON mentor_department.ma_phong_ban = mentor.ma_phong_ban
        LEFT JOIN MENTOR_PROFILE mp ON mp.ma_nguoi_dung = mentor.ma_nguoi_dung
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
                ORDER BY e.id DESC LIMIT 1) AS email_status,
               mentor.ma_nguoi_dung AS mentor_ma_nguoi_dung,
               mentor.ho_ten AS mentor_ho_ten, mentor.email AS mentor_email,
               mentor.so_dien_thoai AS mentor_so_dien_thoai,
               mentor_department.ten_phong_ban AS mentor_phong_ban,
               mp.chuyen_mon AS mentor_chuyen_mon, mp.kinh_nghiem AS mentor_kinh_nghiem
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
