import re
import sqlite3
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status

from ..database import get_db, hash_password
from ..account_credentials import create_temporary_password, queue_temporary_password_email, require_password_change_schema
from ..mentor_assignment_service import (
    assign_mentor_canonical,
    count_mentor_active_interns,
    get_timeline_status,
    unassign_mentor_canonical,
)
from ..schemas import (
    InternAssignmentCandidate,
    MentorAssignmentDetail,
    MentorBatchAssignment,
    MentorCreate,
    MentorDetail,
    MentorProfileUpdate,
)
from ..security import publish_workspace_updated, require_role

router = APIRouter(prefix="/api/mentors", tags=["Mentors"])


@router.get("/me/workspace")
def mentor_workspace(request: Request, db: sqlite3.Connection = Depends(get_db)):
    mentor = require_role(request, "Mentor")
    profile = db.execute("""
        SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               p.ten_phong_ban AS phong_ban, mp.chuyen_mon, mp.kinh_nghiem,
               COALESCE(mp.so_tts_toi_da, 3) AS so_tts_toi_da
        FROM NGUOI_DUNG u
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban=u.ma_phong_ban
        LEFT JOIN MENTOR_PROFILE mp ON mp.ma_nguoi_dung=u.ma_nguoi_dung
        WHERE u.ma_nguoi_dung=? AND u.vai_tro='Mentor'
    """, (mentor["ma_nguoi_dung"],)).fetchone()
    interns = db.execute("""
        SELECT h.ma_ho_so, u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               u.ma_phong_ban, p.ten_phong_ban AS phong_ban, t.ten_truong,
               h.chuyen_nganh, h.trang_thai_xet_duyet, h.trang_thai_thuc_tap,
               a.ngay_phan_cong,
               (SELECT COUNT(*) FROM TAI_LIEU_HO_SO d WHERE d.ma_ho_so=h.ma_ho_so) AS so_tai_lieu
        FROM PHAN_CONG_MENTOR_TTS a
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so=a.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung=h.ma_nguoi_dung
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban=u.ma_phong_ban
        LEFT JOIN TRUONG_DAI_HOC t ON t.ma_truong=h.ma_truong
        WHERE a.ma_nguoi_dung_mentor=?
        ORDER BY u.ho_ten
    """, (mentor["ma_nguoi_dung"],)).fetchall()
    return {"mentor": dict(profile) if profile else None, "interns": [dict(row) for row in interns]}


@router.get("/me/interns/{profile_id}")
def mentor_intern_detail(profile_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    mentor = require_role(request, "Mentor")
    intern = db.execute("""
        SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               u.ma_phong_ban, p.ten_phong_ban AS phong_ban, t.ten_truong,
               h.chuyen_nganh, h.trang_thai_xet_duyet, h.trang_thai_thuc_tap,
               a.ngay_phan_cong
        FROM PHAN_CONG_MENTOR_TTS a
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so=a.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung=h.ma_nguoi_dung
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban=u.ma_phong_ban
        LEFT JOIN TRUONG_DAI_HOC t ON t.ma_truong=h.ma_truong
        WHERE a.ma_nguoi_dung_mentor=? AND h.ma_ho_so=?
    """, (mentor["ma_nguoi_dung"], profile_id)).fetchone()
    if not intern:
        raise HTTPException(status_code=404, detail="Không tìm thấy thực tập sinh được phân công cho bạn.")
    documents = db.execute("""
        SELECT ma_tai_lieu, ma_ho_so, ten_file, loai_tai_lieu, kich_thuoc,
               ngay_tai_len, trang_thai_duyet
        FROM TAI_LIEU_HO_SO WHERE ma_ho_so=? ORDER BY ngay_tai_len DESC
    """, (profile_id,)).fetchall()
    programs = db.execute("""
        SELECT c.ma_chuong_trinh, c.ma_ct, c.ten_ct, c.ngay_bat_dau, c.ngay_ket_thuc,
               a.trang_thai AS trang_thai_ung_tuyen
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh=a.ma_chuong_trinh
        WHERE a.ma_ho_so=? ORDER BY a.ngay_ung_tuyen DESC
    """, (profile_id,)).fetchall()
    return {"intern": dict(intern), "documents": [dict(row) for row in documents], "programs": [dict(row) for row in programs]}


@router.get("")
def list_mentors(
    request: Request,
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, alias="pageSize", ge=1, le=100),
    db: sqlite3.Connection = Depends(get_db),
):
    require_role(request, "Admin", "HR")
    paginated = page is not None or page_size is not None
    effective_size = page_size or 10
    if paginated:
        total_items = db.execute(
            "SELECT COUNT(*) AS total_items FROM NGUOI_DUNG WHERE vai_tro = 'Mentor'"
        ).fetchone()["total_items"]
        total_pages = (total_items + effective_size - 1) // effective_size if total_items else 0
        effective_page = min(page or 1, total_pages) if total_pages else 1
        limit_clause = " LIMIT ? OFFSET ?"
        paging_params = (effective_size, (effective_page - 1) * effective_size)
    else:
        total_items = total_pages = effective_page = None
        limit_clause = ""
        paging_params = ()
    rows = db.execute("""
        SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               u.ma_phong_ban, p.ten_phong_ban AS phong_ban,
               mp.chuyen_mon, mp.kinh_nghiem, COALESCE(mp.so_tts_toi_da, 3) AS so_tts_toi_da,
               (SELECT COUNT(DISTINCT a.ma_ho_so)
                FROM PHAN_CONG_MENTOR_TTS a
                JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
                LEFT JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
                WHERE a.ma_nguoi_dung_mentor = u.ma_nguoi_dung
                  AND (
                      (a.ma_chuong_trinh IS NOT NULL
                       AND c.trang_thai != 'DaDong'
                       AND (c.ngay_bat_dau IS NULL OR CURRENT_DATE >= c.ngay_bat_dau)
                       AND (c.ngay_ket_thuc IS NULL OR CURRENT_DATE <= c.ngay_ket_thuc))
                      OR
                      (a.ma_chuong_trinh IS NULL AND h.trang_thai_thuc_tap = 'DangThucTap')
                  )
               ) AS so_tts_dang_huong_dan
        FROM NGUOI_DUNG u
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = u.ma_phong_ban
        LEFT JOIN MENTOR_PROFILE mp ON mp.ma_nguoi_dung = u.ma_nguoi_dung
        WHERE u.vai_tro = 'Mentor'
        ORDER BY u.ma_nguoi_dung DESC
    """ + limit_clause, paging_params).fetchall()
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


@router.get("/unassigned-interns", response_model=list[InternAssignmentCandidate])
def list_unassigned_interns(request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin", "HR")
    # Lấy các ứng viên có chương trình đã duyệt (CURRENT hoặc UPCOMING) chưa có mentor trong chương trình đó
    rows = db.execute("""
        SELECT h.ma_ho_so, u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               t.ten_truong, h.chuyen_nganh,
               a.ma_chuong_trinh, c.ten_ct, c.ma_ct, a.ma_ung_tuyen,
               c.ngay_bat_dau, c.ngay_ket_thuc, c.trang_thai AS trang_thai_ct
        FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        LEFT JOIN TRUONG_DAI_HOC t ON t.ma_truong = h.ma_truong
        JOIN UNG_TUYEN_CHUONG_TRINH a ON a.ma_ho_so = h.ma_ho_so AND a.trang_thai = 'DaDuyet'
        JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh AND c.trang_thai != 'DaDong'
        WHERE u.vai_tro = 'ThucTapSinh' AND u.trang_thai = 'HoatDong'
          AND h.trang_thai_xet_duyet = 'DaDuyet'
          AND NOT EXISTS (
              SELECT 1 FROM PHAN_CONG_MENTOR_TTS p
              WHERE p.ma_ho_so = h.ma_ho_so
                AND (p.ma_chuong_trinh = a.ma_chuong_trinh OR (p.ma_chuong_trinh IS NULL AND p.ma_ho_so = h.ma_ho_so))
          )
        ORDER BY u.ho_ten COLLATE NOCASE
    """).fetchall()

    results = []
    seen = set()
    for row in rows:
        t_status = get_timeline_status(row["ngay_bat_dau"], row["ngay_ket_thuc"], row["trang_thai_ct"])
        if t_status != "HISTORICAL":
            d = dict(row)
            d["timeline_status"] = t_status
            results.append(d)
            seen.add(row["ma_ho_so"])

    # Fallback cho TTS hồ sơ duyệt nhưng chưa có record trong UNG_TUYEN_CHUONG_TRINH (test fixtures cũ)
    legacy_rows = db.execute("""
        SELECT h.ma_ho_so, u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               t.ten_truong, h.chuyen_nganh
        FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        LEFT JOIN TRUONG_DAI_HOC t ON t.ma_truong = h.ma_truong
        WHERE u.vai_tro = 'ThucTapSinh' AND u.trang_thai = 'HoatDong'
          AND h.trang_thai_xet_duyet = 'DaDuyet'
          AND h.trang_thai_thuc_tap = 'DangThucTap'
          AND NOT EXISTS (
              SELECT 1 FROM PHAN_CONG_MENTOR_TTS a WHERE a.ma_ho_so = h.ma_ho_so
          )
        ORDER BY u.ho_ten COLLATE NOCASE
    """).fetchall()
    for row in legacy_rows:
        if row["ma_ho_so"] not in seen:
            d = dict(row)
            d["timeline_status"] = "CURRENT"
            results.append(d)
            seen.add(row["ma_ho_so"])

    return results


@router.get("/{mentor_id}/interns", response_model=list[MentorAssignmentDetail])
def list_mentor_interns(mentor_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin", "HR")
    if not db.execute("SELECT 1 FROM NGUOI_DUNG WHERE ma_nguoi_dung = ? AND vai_tro = 'Mentor'", (mentor_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Không tìm thấy Mentor.")
    rows = db.execute("""
        SELECT h.ma_ho_so, u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
               t.ten_truong, h.chuyen_nganh, a.ngay_phan_cong, a.ma_phan_cong,
               a.ma_chuong_trinh, a.ma_ung_tuyen,
               c.ten_ct, c.ma_ct, c.ngay_bat_dau, c.ngay_ket_thuc, c.trang_thai AS trang_thai_ct,
               h.trang_thai_thuc_tap
        FROM PHAN_CONG_MENTOR_TTS a
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        LEFT JOIN TRUONG_DAI_HOC t ON t.ma_truong = h.ma_truong
        LEFT JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
        WHERE a.ma_nguoi_dung_mentor = ?
        ORDER BY u.ho_ten COLLATE NOCASE
    """, (mentor_id,)).fetchall()
    items = []
    for row in rows:
        d = dict(row)
        d["timeline_status"] = get_timeline_status(
            row["ngay_bat_dau"], row["ngay_ket_thuc"], row["trang_thai_ct"]
        ) if row["ma_chuong_trinh"] else (
            "CURRENT" if row["trang_thai_thuc_tap"] == "DangThucTap" else "HISTORICAL"
        )
        items.append(d)
    return items


@router.put("/{mentor_id}/profile", response_model=dict[str, str])
def update_mentor_profile(
    mentor_id: int, data: MentorProfileUpdate, request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    require_role(request, "Admin", "HR")
    if not db.execute("SELECT 1 FROM NGUOI_DUNG WHERE ma_nguoi_dung = ? AND vai_tro = 'Mentor'", (mentor_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Không tìm thấy Mentor.")
    capacity = data.so_tts_toi_da if data.so_tts_toi_da is not None else 3
    try:
        db.execute("BEGIN IMMEDIATE")
        assigned_count = count_mentor_active_interns(db, mentor_id)
        if capacity < assigned_count:
            raise HTTPException(status_code=400, detail=f"Sức chứa không thể thấp hơn {assigned_count} TTS đang được phân công.")
        db.execute("""
            INSERT INTO MENTOR_PROFILE (ma_nguoi_dung, chuyen_mon, kinh_nghiem, so_tts_toi_da)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ma_nguoi_dung) DO UPDATE SET
                chuyen_mon = excluded.chuyen_mon,
                kinh_nghiem = excluded.kinh_nghiem,
                so_tts_toi_da = excluded.so_tts_toi_da
        """, (
            mentor_id,
            data.chuyen_mon.strip() if data.chuyen_mon and data.chuyen_mon.strip() else None,
            data.kinh_nghiem,
            capacity,
        ))
        db.commit()
    except HTTPException:
        db.rollback()
    return {"message": "Đã cập nhật hồ sơ Mentor."}


@router.post("/{mentor_id}/interns/{profile_id}", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
def assign_intern(
    mentor_id: int, profile_id: int, request: Request,
    background_tasks: BackgroundTasks,
    program_id: int | None = Query(None),
    db: sqlite3.Connection = Depends(get_db),
):
    actor = require_role(request, "Admin", "HR")
    try:
        db.execute("BEGIN IMMEDIATE")
        res = assign_mentor_canonical(
            db,
            mentor_id=mentor_id,
            profile_id=profile_id,
            program_id=program_id,
            assigned_by=actor["ma_nguoi_dung"],
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="TTS đã được phân công cho Mentor khác hoặc bị trùng lặp.") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(publish_workspace_updated, mentor_id)
    background_tasks.add_task(publish_workspace_updated, res["intern_user_id"])
    return res


@router.post("/{mentor_id}/assignments/batch", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
def assign_interns_batch(
    mentor_id: int, data: MentorBatchAssignment, request: Request,
    background_tasks: BackgroundTasks,
    db: sqlite3.Connection = Depends(get_db),
):
    actor = require_role(request, "Admin", "HR")
    if len(set(data.ma_ho_so_list)) != len(data.ma_ho_so_list):
        raise HTTPException(status_code=400, detail="Danh sách có thực tập sinh bị lặp.")
    try:
        db.execute("BEGIN IMMEDIATE")
        intern_user_ids = []
        for profile_id in data.ma_ho_so_list:
            res = assign_mentor_canonical(
                db,
                mentor_id=mentor_id,
                profile_id=profile_id,
                program_id=data.ma_chuong_trinh,
                assigned_by=actor["ma_nguoi_dung"],
            )
            intern_user_ids.append(res["intern_user_id"])
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Có hồ sơ TTS vừa được phân công hoặc trùng lặp.") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(publish_workspace_updated, mentor_id)
    for intern_user_id in intern_user_ids:
        background_tasks.add_task(publish_workspace_updated, intern_user_id)
    return {
        "message": f"Đã phân công {len(data.ma_ho_so_list)} thực tập sinh.",
        "so_tts_da_phan_cong": len(data.ma_ho_so_list),
    }


@router.delete("/{mentor_id}/interns/{profile_id}", response_model=dict[str, str])
def unassign_intern(
    mentor_id: int, profile_id: int, request: Request,
    background_tasks: BackgroundTasks,
    program_id: int | None = Query(None),
    db: sqlite3.Connection = Depends(get_db),
):
    require_role(request, "Admin", "HR")
    try:
        db.execute("BEGIN IMMEDIATE")
        res = unassign_mentor_canonical(
            db,
            mentor_id=mentor_id,
            profile_id=profile_id,
            program_id=program_id,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(publish_workspace_updated, mentor_id)
    background_tasks.add_task(publish_workspace_updated, res["intern_user_id"])
    return {"message": "Đã gỡ phân công thực tập sinh."}


@router.post("", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_mentor(data: MentorCreate, request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin", "HR")
    require_password_change_schema(db)
    if data.so_dien_thoai and not re.fullmatch(r"(03|05|07|08|09)\d{8}", data.so_dien_thoai):
        raise HTTPException(status_code=400, detail="Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 03, 05, 07, 08 hoặc 09.")
    email = data.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="Email không hợp lệ.")
    if db.execute("SELECT 1 FROM NGUOI_DUNG WHERE LOWER(email) = ?", (email,)).fetchone():
        raise HTTPException(status_code=400, detail="Email đã được đăng ký trong hệ thống.")

    cursor = db.cursor()
    temporary_password = create_temporary_password()
    try:
        cursor.execute("""
            INSERT INTO NGUOI_DUNG
                (ma_phong_ban, ho_ten, email, mat_khau, must_change_password, so_dien_thoai, vai_tro, trang_thai)
            VALUES (?, ?, ?, ?, 1, ?, 'Mentor', 'HoatDong')
        """, (data.ma_phong_ban, data.ho_ten.strip(), email, hash_password(temporary_password), data.so_dien_thoai or None))
        user_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO MENTOR_PROFILE (ma_nguoi_dung, chuyen_mon, kinh_nghiem, so_tts_toi_da)
            VALUES (?, ?, ?, ?)
        """, (user_id, data.chuyen_mon.strip() if data.chuyen_mon else None, data.kinh_nghiem, data.so_tts_toi_da))
        queue_temporary_password_email(db, user_id, data.ho_ten.strip(), email, temporary_password)
        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Phòng ban không hợp lệ hoặc email đã được sử dụng.") from exc

    return {"message": f"Đã thêm Mentor {data.ho_ten.strip()}; email mật khẩu tạm đang được gửi.", "ma_nguoi_dung": user_id}
