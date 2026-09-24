from fastapi import APIRouter, HTTPException, Depends, status, Query
import sqlite3
from typing import List, Optional, Dict, Any
from ..database import get_db, hash_password
from ..schemas import InternCreate, InternUpdate, InternDetail

router = APIRouter(prefix="/api/interns", tags=["Intern Profile - US01, US02, US03"])

@router.post("", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_intern(data: InternCreate, db: sqlite3.Connection = Depends(get_db)):
    """
    US01 – Thêm mới hồ sơ thực tập sinh (Quản lý hồ sơ)
    Viết API lưu thông tin vào CSDL (Backend).
    Tạo tài khoản NGUOI_DUNG với vai_tro='ThucTapSinh' và tạo bản ghi HO_SO_THUC_TAP.
    """
    cursor = db.cursor()

    # Kiểm tra email trùng
    cursor.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email = ?", (data.email,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email '{data.email}' đã tồn tại trong hệ thống!"
        )

    # 1. Tạo tài khoản trong NGUOI_DUNG
    hashed_pw = hash_password(data.mat_khau or "123456")
    cursor.execute("""
        INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, so_dien_thoai, vai_tro, trang_thai)
        VALUES (?, ?, ?, ?, ?, 'ThucTapSinh', 'HoatDong')
    """, (data.ma_phong_ban, data.ho_ten, data.email, hashed_pw, data.so_dien_thoai))
    
    ma_nguoi_dung = cursor.lastrowid

    # 2. Tạo hồ sơ trong HO_SO_THUC_TAP
    cursor.execute("""
        INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
        VALUES (?, ?, ?, ?, ?)
    """, (
        ma_nguoi_dung,
        data.ma_truong,
        data.chuyen_nganh,
        data.trang_thai_xet_duyet or 'ChoDuyet',
        data.trang_thai_thuc_tap or 'DangThucTap'
    ))

    ma_ho_so = cursor.lastrowid
    db.commit()

    return {
        "message": "Thêm mới hồ sơ thực tập sinh thành công!",
        "ma_ho_so": ma_ho_so,
        "ma_nguoi_dung": ma_nguoi_dung,
        "ho_ten": data.ho_ten,
        "email": data.email
    }

@router.get("/{id}", response_model=InternDetail)
def get_intern_by_id(id: int, db: sqlite3.Connection = Depends(get_db)):
    """
    US02 – Cập nhật/Chỉnh sửa hồ sơ thực tập sinh (Quản lý hồ sơ)
    Viết API lấy thông tin chi tiết theo ID thực tập sinh (ma_ho_so hoặc ma_nguoi_dung).
    """
    cursor = db.cursor()
    cursor.execute("""
        SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               u.ma_phong_ban, p.ten_phong_ban, h.ma_truong, t.ten_truong,
               h.chuyen_nganh, h.trang_thai_xet_duyet, h.trang_thai_thuc_tap,
               h.ngay_tao
        FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON h.ma_nguoi_dung = u.ma_nguoi_dung
        LEFT JOIN PHONG_BAN p ON u.ma_phong_ban = p.ma_phong_ban
        LEFT JOIN TRUONG_DAI_HOC t ON h.ma_truong = t.ma_truong
        WHERE h.ma_ho_so = ? OR h.ma_nguoi_dung = ?
    """, (id, id))
    
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy hồ sơ thực tập sinh với ID = {id}"
        )

    return dict(row)

@router.put("/{id}", response_model=Dict[str, Any])
def update_intern(id: int, data: InternUpdate, db: sqlite3.Connection = Depends(get_db)):
    """
    US02 – Cập nhật/Chỉnh sửa hồ sơ thực tập sinh (Quản lý hồ sơ)
    Viết API Cập nhật (Update) dữ liệu.
    """
    cursor = db.cursor()
    
    # Kiểm tra hồ sơ có tồn tại không
    cursor.execute("""
        SELECT h.ma_ho_so, h.ma_nguoi_dung FROM HO_SO_THUC_TAP h WHERE h.ma_ho_so = ?
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
        SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email = ? AND ma_nguoi_dung != ?
    """, (data.email, ma_nguoi_dung))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email '{data.email}' đã được sử dụng bởi người dùng khác!"
        )

    # 1. Cập nhật bảng NGUOI_DUNG
    cursor.execute("""
        UPDATE NGUOI_DUNG
        SET ho_ten = ?, email = ?, so_dien_thoai = ?, ma_phong_ban = ?
        WHERE ma_nguoi_dung = ?
    """, (data.ho_ten, data.email, data.so_dien_thoai, data.ma_phong_ban, ma_nguoi_dung))

    # 2. Cập nhật bảng HO_SO_THUC_TAP
    cursor.execute("""
        UPDATE HO_SO_THUC_TAP
        SET ma_truong = ?, chuyen_nganh = ?, trang_thai_xet_duyet = ?, trang_thai_thuc_tap = ?
        WHERE ma_ho_so = ?
    """, (data.ma_truong, data.chuyen_nganh, data.trang_thai_xet_duyet, data.trang_thai_thuc_tap, id))

    db.commit()

    return {
        "message": "Cập nhật hồ sơ thực tập sinh thành công!",
        "ma_ho_so": id,
        "ho_ten": data.ho_ten,
        "email": data.email
    }

@router.get("", response_model=List[InternDetail])
def list_interns(
    search: Optional[str] = Query(None, description="Tìm kiếm theo họ tên, email, chuyên ngành"),
    trang_thai_xet_duyet: Optional[str] = Query(None, description="Lọc theo ChoDuyet, DaDuyet, TuChoi"),
    trang_thai_thuc_tap: Optional[str] = Query(None, description="Lọc theo DangThucTap, HoanThanh, ThoiHoc"),
    ma_phong_ban: Optional[int] = Query(None, description="Lọc theo phòng ban"),
    ma_truong: Optional[int] = Query(None, description="Lọc theo trường đại học"),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Hỗ trợ giao diện US03 – Tìm kiếm & Lọc danh sách thực tập sinh
    """
    cursor = db.cursor()
    query = """
        SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               u.ma_phong_ban, p.ten_phong_ban, h.ma_truong, t.ten_truong,
               h.chuyen_nganh, h.trang_thai_xet_duyet, h.trang_thai_thuc_tap,
               h.ngay_tao
        FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON h.ma_nguoi_dung = u.ma_nguoi_dung
        LEFT JOIN PHONG_BAN p ON u.ma_phong_ban = p.ma_phong_ban
        LEFT JOIN TRUONG_DAI_HOC t ON h.ma_truong = t.ma_truong
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND (u.ho_ten LIKE ? OR u.email LIKE ? OR h.chuyen_nganh LIKE ?)"
        keyword = f"%{search}%"
        params.extend([keyword, keyword, keyword])

    if trang_thai_xet_duyet:
        query += " AND h.trang_thai_xet_duyet = ?"
        params.append(trang_thai_xet_duyet)

    if trang_thai_thuc_tap:
        query += " AND h.trang_thai_thuc_tap = ?"
        params.append(trang_thai_thuc_tap)

    if ma_phong_ban:
        query += " AND u.ma_phong_ban = ?"
        params.append(ma_phong_ban)

    if ma_truong:
        query += " AND h.ma_truong = ?"
        params.append(ma_truong)

    query += " ORDER BY h.ma_ho_so DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    return [dict(row) for row in rows]
