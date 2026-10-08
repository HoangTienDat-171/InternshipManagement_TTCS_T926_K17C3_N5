import sqlite3
from datetime import date
from typing import Any, Optional

from fastapi import HTTPException, status


def parse_date_value(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    text = str(val).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except (ValueError, TypeError):
        return None


def get_timeline_status(
    start_date: Any,
    end_date: Any,
    program_status: Optional[str] = None,
    as_of: Optional[date] = None,
) -> str:
    """
    Xác định trạng thái dòng thời gian của chương trình:
    - 'HISTORICAL': Đã kết thúc (ngày kết thúc trước hôm nay hoặc chương trình đã đóng).
    - 'CURRENT': Đang diễn ra (hôm nay nằm trong khoảng bắt đầu - kết thúc).
    - 'UPCOMING': Sắp tới (ngày bắt đầu sau hôm nay).
    """
    ref_date = as_of or date.today()
    s = parse_date_value(start_date)
    e = parse_date_value(end_date)

    if program_status == "DaDong" or (e is not None and e < ref_date):
        return "HISTORICAL"
    if s is not None and ref_date < s:
        return "UPCOMING"
    return "CURRENT"


def check_program_overlap(
    db: sqlite3.Connection,
    profile_id: int,
    candidate_program_id: int,
) -> Optional[dict]:
    """
    Kiểm tra xem TTS (ma_ho_so) đã có đơn ứng tuyển được duyệt (DaDuyet) ở chương trình khác
    có khoảng thời gian overlap với chương trình candidate_program_id hay không.

    Quy tắc PO:
    - TTS có thể được duyệt trước cho chương trình tương lai nếu KHÔNG overlap chương trình hiện tại.
    - Nếu hai chương trình overlap: application duyệt trước được giữ nguyên, application duyệt sau bị chặn.
    - Trả về thông tin chương trình bị xung đột nếu có, ngược lại trả về None.
    """
    cand = db.execute("""
        SELECT ma_chuong_trinh, ma_ct, ten_ct, ngay_bat_dau, ngay_ket_thuc, trang_thai
        FROM CHUONG_TRINH_THUC_TAP
        WHERE ma_chuong_trinh = ?
    """, (candidate_program_id,)).fetchone()
    if not cand:
        return None

    c_start = parse_date_value(cand["ngay_bat_dau"])
    c_end = parse_date_value(cand["ngay_ket_thuc"])

    # Chỉ chương trình chưa đóng mới được tính là cam kết đang hoạt động.
    # Đơn và phân công của chương trình đóng vẫn được giữ lại để tra cứu lịch sử.
    approved_programs = db.execute("""
        SELECT c.ma_chuong_trinh, c.ma_ct, c.ten_ct, c.ngay_bat_dau, c.ngay_ket_thuc, c.trang_thai
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
        WHERE a.ma_ho_so = ? AND a.trang_thai = 'DaDuyet' AND a.ma_chuong_trinh != ?
          AND c.trang_thai <> 'DaDong'
    """, (profile_id, candidate_program_id)).fetchall()

    for row in approved_programs:
        o_start = parse_date_value(row["ngay_bat_dau"])
        o_end = parse_date_value(row["ngay_ket_thuc"])

        # Nếu cả 2 đều có ngày bắt đầu và kết thúc:
        # Overlap khi: c_start <= o_end AND o_start <= c_end
        if c_start and c_end and o_start and o_end:
            if c_start <= o_end and o_start <= c_end:
                return dict(row)
        else:
            # Nếu thiếu ngày cụ thể nhưng một trong hai chưa đóng
            if row["trang_thai"] != "DaDong" and cand["trang_thai"] != "DaDong":
                # Nếu có start date: kiểm tra nếu cùng một thời điểm
                if c_start and o_start and c_start == o_start:
                    return dict(row)
                if not c_start or not o_start:
                    return dict(row)

    return None


def get_intern_approved_programs(
    db: sqlite3.Connection,
    profile_id: int,
    as_of: Optional[date] = None,
) -> list[dict]:
    """
    Lấy danh sách các chương trình đã duyệt của TTS kèm trạng thái dòng thời gian
    (HISTORICAL / CURRENT / UPCOMING) và thông tin Mentor phân công nếu có.
    """
    ref_date = as_of or date.today()
    rows = db.execute("""
        SELECT a.ma_ung_tuyen, a.trang_thai AS trang_thai_ung_tuyen,
               c.ma_chuong_trinh, c.ma_ct, c.ten_ct, c.ngay_bat_dau, c.ngay_ket_thuc, c.trang_thai AS trang_thai_ct,
               m.ma_nguoi_dung AS mentor_id, m.ho_ten AS mentor_name, m.email AS mentor_email,
               m.so_dien_thoai AS mentor_so_dien_thoai,
               p.ngay_phan_cong, p.ma_phan_cong
        FROM UNG_TUYEN_CHUONG_TRINH a
        JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
        LEFT JOIN PHAN_CONG_MENTOR_TTS p ON p.ma_ho_so = a.ma_ho_so
             AND (p.ma_chuong_trinh = c.ma_chuong_trinh OR (p.ma_chuong_trinh IS NULL AND p.ma_ho_so = a.ma_ho_so))
        LEFT JOIN NGUOI_DUNG m ON m.ma_nguoi_dung = p.ma_nguoi_dung_mentor AND m.vai_tro = 'Mentor'
        WHERE a.ma_ho_so = ? AND a.trang_thai = 'DaDuyet'
        ORDER BY c.ngay_bat_dau ASC, c.ma_chuong_trinh ASC
    """, (profile_id,)).fetchall()

    results = []
    for r in rows:
        item = dict(r)
        item["timeline_status"] = get_timeline_status(
            r["ngay_bat_dau"], r["ngay_ket_thuc"], r["trang_thai_ct"], ref_date
        )
        results.append(item)
    return results


def get_intern_active_program(
    db: sqlite3.Connection,
    profile_id: int,
    as_of: Optional[date] = None,
) -> Optional[dict]:
    """
    Quy tắc PO 1: Một TTS chỉ tham gia 1 chương trình thực tập ACTIVE tại một thời điểm.
    Trả về chương trình có timeline_status == 'CURRENT'.
    """
    programs = get_intern_approved_programs(db, profile_id, as_of)
    for prog in programs:
        if prog["timeline_status"] == "CURRENT":
            return prog
    return None


def get_intern_active_assignment(
    db: sqlite3.Connection,
    profile_id: int,
    as_of: Optional[date] = None,
) -> Optional[dict]:
    """
    Quy tắc PO 2 & 9:
    Một TTS chỉ có tối đa 1 Mentor ACTIVE tại một thời điểm.
    Lấy thông tin Mentor của chương trình ACTIVE (CURRENT).
    Nếu không có chương trình CURRENT nhưng có phân công legacy duy nhất, trả về legacy assignment.
    """
    active_prog = get_intern_active_program(db, profile_id, as_of)
    if active_prog and active_prog.get("mentor_id"):
        return {
            "ma_nguoi_dung": active_prog["mentor_id"],
            "ho_ten": active_prog["mentor_name"],
            "email": active_prog["mentor_email"],
            "so_dien_thoai": active_prog.get("mentor_so_dien_thoai"),
            "ma_chuong_trinh": active_prog["ma_chuong_trinh"],
            "ten_ct": active_prog["ten_ct"],
            "ngay_phan_cong": active_prog.get("ngay_phan_cong"),
            "timeline_status": "CURRENT",
        }

    # Nếu không có active program, kiểm tra legacy assignment
    legacy = db.execute("""
        SELECT p.ma_phan_cong, p.ngay_phan_cong, p.ma_chuong_trinh,
               m.ma_nguoi_dung, m.ho_ten, m.email, m.so_dien_thoai,
               c.ten_ct, c.ngay_bat_dau, c.ngay_ket_thuc, c.trang_thai AS trang_thai_ct
        FROM PHAN_CONG_MENTOR_TTS p
        JOIN NGUOI_DUNG m ON m.ma_nguoi_dung = p.ma_nguoi_dung_mentor AND m.vai_tro = 'Mentor'
        LEFT JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = p.ma_chuong_trinh
        WHERE p.ma_ho_so = ?
        ORDER BY p.ma_phan_cong DESC
        LIMIT 1
    """, (profile_id,)).fetchone()
    if legacy:
        t_status = get_timeline_status(
            legacy["ngay_bat_dau"], legacy["ngay_ket_thuc"], legacy["trang_thai_ct"], as_of
        ) if legacy["ma_chuong_trinh"] else "CURRENT"
        if t_status == "CURRENT":
            return {
                "ma_nguoi_dung": legacy["ma_nguoi_dung"],
                "ho_ten": legacy["ho_ten"],
                "email": legacy["email"],
                "so_dien_thoai": legacy.get("so_dien_thoai"),
                "ma_chuong_trinh": legacy["ma_chuong_trinh"],
                "ten_ct": legacy["ten_ct"],
                "ngay_phan_cong": legacy.get("ngay_phan_cong"),
                "timeline_status": t_status,
            }

    return None


def count_mentor_active_interns(
    db: sqlite3.Connection,
    mentor_id: int,
    as_of: Optional[date] = None,
) -> int:
    """
    Đếm số TTS ACTIVE mà Mentor đang hướng dẫn:
    Một phân công được tính là ACTIVE nếu:
    - Thuộc một chương trình có timeline_status == 'CURRENT'
    - Hoặc là phân công legacy (ma_chuong_trinh IS NULL) và hồ sơ TTS ở trạng thái 'DangThucTap'.
    """
    ref_date = as_of or date.today()
    rows = db.execute("""
        SELECT p.ma_ho_so, p.ma_chuong_trinh,
               c.ngay_bat_dau, c.ngay_ket_thuc, c.trang_thai AS trang_thai_ct,
               h.trang_thai_thuc_tap
        FROM PHAN_CONG_MENTOR_TTS p
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = p.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        LEFT JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = p.ma_chuong_trinh
        WHERE p.ma_nguoi_dung_mentor = ? AND u.trang_thai = 'HoatDong'
    """, (mentor_id,)).fetchall()

    active_count = 0
    counted_interns = set()
    for r in rows:
        if r["ma_ho_so"] in counted_interns:
            continue
        if r["ma_chuong_trinh"]:
            t_status = get_timeline_status(
                r["ngay_bat_dau"], r["ngay_ket_thuc"], r["trang_thai_ct"], ref_date
            )
            if t_status == "CURRENT":
                active_count += 1
                counted_interns.add(r["ma_ho_so"])
        else:
            # Legacy assignment
            if r["trang_thai_thuc_tap"] == "DangThucTap":
                active_count += 1
                counted_interns.add(r["ma_ho_so"])

    return active_count


def assign_mentor_canonical(
    db: sqlite3.Connection,
    mentor_id: int,
    profile_id: int,
    program_id: Optional[int] = None,
    application_id: Optional[int] = None,
    assigned_by: Optional[int] = None,
) -> dict:
    """
    CANONICAL IMPLEMENTATION cho US12 và US30:
    Phân công Mentor cho Thực tập sinh gắn với ngữ cảnh Chương trình thực tập.

    Tuân thủ tuyệt đối Business Rules đã được PO chốt:
    1. Một TTS chỉ tham gia 1 chương trình ACTIVE tại một thời điểm.
    2. Một TTS chỉ có tối đa 1 Mentor ACTIVE tại một thời điểm.
    3. TTS có thể có nhiều Mentor theo thời gian:
       Program A -> Mentor X -> HISTORICAL
       Program B -> Mentor Y -> CURRENT
       Program C -> Mentor Z -> UPCOMING
    4. Không dùng UNIQUE(ma_ho_so) để giới hạn Mentor toàn đời.
    5. Kiểm tra sức chứa (capacity) của Mentor cho các đợt thực tập ACTIVE.
    """
    # 1. Kiểm tra Mentor hợp lệ và hoạt động
    mentor = db.execute("""
        SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.trang_thai,
               COALESCE(mp.so_tts_toi_da, 3) AS so_tts_toi_da
        FROM NGUOI_DUNG u
        LEFT JOIN MENTOR_PROFILE mp ON mp.ma_nguoi_dung = u.ma_nguoi_dung
        WHERE u.ma_nguoi_dung = ? AND u.vai_tro = 'Mentor'
    """, (mentor_id,)).fetchone()
    if not mentor:
        raise HTTPException(status_code=404, detail="Không tìm thấy Mentor.")
    mentor = dict(mentor)
    if mentor["trang_thai"] != "HoatDong":
        raise HTTPException(status_code=400, detail="Mentor chưa ở trạng thái hoạt động.")

    # 2. Kiểm tra TTS hợp lệ
    intern = db.execute("""
        SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten, u.email, h.trang_thai_xet_duyet, h.trang_thai_thuc_tap
        FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE h.ma_ho_so = ? AND u.vai_tro = 'ThucTapSinh' AND u.trang_thai = 'HoatDong'
    """, (profile_id,)).fetchone()
    if not intern:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ thực tập sinh hợp lệ.")
    intern = dict(intern)
    if intern["trang_thai_xet_duyet"] != "DaDuyet":
        raise HTTPException(status_code=400, detail="Chỉ có thể phân công TTS có hồ sơ đã được duyệt.")

    # 3. Xác định ngữ cảnh Chương trình thực tập (Program Context)
    target_program_id = program_id
    target_app_id = application_id

    if target_app_id and not target_program_id:
        app_row = db.execute("""
            SELECT ma_chuong_trinh, ma_ho_so, trang_thai
            FROM UNG_TUYEN_CHUONG_TRINH
            WHERE ma_ung_tuyen = ?
        """, (target_app_id,)).fetchone()
        if not app_row or app_row["ma_ho_so"] != profile_id:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn ứng tuyển của thực tập sinh.")
        if app_row["trang_thai"] != "DaDuyet":
            raise HTTPException(status_code=400, detail="Chỉ có thể phân công Mentor cho đơn ứng tuyển đã được duyệt.")
        target_program_id = app_row["ma_chuong_trinh"]

    if target_program_id:
        # Xác thực TTS đã được duyệt vào chương trình này
        app = db.execute("""
            SELECT ma_ung_tuyen, trang_thai
            FROM UNG_TUYEN_CHUONG_TRINH
            WHERE ma_ho_so = ? AND ma_chuong_trinh = ?
        """, (profile_id, target_program_id)).fetchone()
        if not app or app["trang_thai"] != "DaDuyet":
            raise HTTPException(
                status_code=400,
                detail="Thực tập sinh chưa có đơn ứng tuyển đã duyệt trong chương trình này.",
            )
        target_app_id = app["ma_ung_tuyen"]
    else:
        # Nếu không truyền program_id, tìm chương trình đã duyệt hợp lệ của TTS (ưu tiên CURRENT, rồi UPCOMING)
        approved_progs = get_intern_approved_programs(db, profile_id)
        if not approved_progs:
            if intern.get("trang_thai_thuc_tap") == "DangThucTap" or intern.get("trang_thai_xet_duyet") == "DaDuyet":
                target_program_id = None
                target_app_id = None
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Thực tập sinh chưa được duyệt vào chương trình thực tập nào.",
                )
        else:
            # Tìm chương trình chưa có mentor phân công
            unassigned_progs = [p for p in approved_progs if not p.get("mentor_id")]
            candidates = unassigned_progs or approved_progs
            # Ưu tiên CURRENT rồi UPCOMING rồi mới đến HISTORICAL
            current_progs = [p for p in candidates if p["timeline_status"] == "CURRENT"]
            upcoming_progs = [p for p in candidates if p["timeline_status"] == "UPCOMING"]
            selected = current_progs[0] if current_progs else (upcoming_progs[0] if upcoming_progs else candidates[0])

            target_program_id = selected["ma_chuong_trinh"]
            target_app_id = selected["ma_ung_tuyen"]

    # Lấy thông tin chương trình để kiểm tra timeline status
    if target_program_id:
        prog_info = db.execute("""
            SELECT ma_chuong_trinh, ten_ct, ngay_bat_dau, ngay_ket_thuc, trang_thai
            FROM CHUONG_TRINH_THUC_TAP WHERE ma_chuong_trinh = ?
        """, (target_program_id,)).fetchone()
        timeline_status = get_timeline_status(
            prog_info["ngay_bat_dau"], prog_info["ngay_ket_thuc"], prog_info["trang_thai"]
        )
        prog_title = f" ({prog_info['ten_ct']})"
    else:
        prog_info = None
        timeline_status = "CURRENT"
        prog_title = ""

    # 4. Kiểm tra sức chứa Mentor nếu chương trình là CURRENT (ACTIVE)
    if timeline_status == "CURRENT":
        active_load = count_mentor_active_interns(db, mentor_id)
        # Nếu chính TTS này đã được phân công cho mentor này ở chương trình này thì không tăng load
        existing_for_same = db.execute("""
            SELECT 1 FROM PHAN_CONG_MENTOR_TTS
            WHERE ma_nguoi_dung_mentor = ? AND ma_ho_so = ? AND ma_chuong_trinh = ?
        """, (mentor_id, profile_id, target_program_id)).fetchone()
        if not existing_for_same and active_load >= mentor["so_tts_toi_da"]:
            raise HTTPException(
                status_code=400,
                detail=f"Mentor đã đạt sức chứa tối đa ({mentor['so_tts_toi_da']} TTS đang thực tập).",
            )

    # 5. Lưu phân công (Idempotent / Upsert cho cùng program context)
    existing_assignment = db.execute("""
        SELECT ma_phan_cong, ma_nguoi_dung_mentor
        FROM PHAN_CONG_MENTOR_TTS
        WHERE ma_ho_so = ? AND (ma_chuong_trinh = ? OR (ma_chuong_trinh IS NULL AND ? IS NULL))
    """, (profile_id, target_program_id, target_program_id)).fetchone()

    if existing_assignment:
        if existing_assignment["ma_nguoi_dung_mentor"] == mentor_id:
            # Đã phân công cho chính Mentor này
            return {
                "message": f"Thực tập sinh {intern['ho_ten']} đã được phân công cho Mentor {mentor['ho_ten']}.",
                "ma_phan_cong": existing_assignment["ma_phan_cong"],
                "mentor_id": mentor_id,
                "profile_id": profile_id,
                "program_id": target_program_id,
                "timeline_status": timeline_status,
                "intern_user_id": intern["ma_nguoi_dung"],
            }
        else:
            # Cập nhật đổi sang Mentor mới
            db.execute("""
                UPDATE PHAN_CONG_MENTOR_TTS
                SET ma_nguoi_dung_mentor = ?, ma_ung_tuyen = ?, ma_nguoi_phan_cong = ?, ngay_phan_cong = CURRENT_TIMESTAMP
                WHERE ma_phan_cong = ?
            """, (mentor_id, target_app_id, assigned_by, existing_assignment["ma_phan_cong"]))
            assignment_id = existing_assignment["ma_phan_cong"]
    else:
        cursor = db.execute("""
            INSERT INTO PHAN_CONG_MENTOR_TTS
                (ma_nguoi_dung_mentor, ma_ho_so, ma_chuong_trinh, ma_ung_tuyen, ma_nguoi_phan_cong)
            VALUES (?, ?, ?, ?, ?)
        """, (mentor_id, profile_id, target_program_id, target_app_id, assigned_by))
        assignment_id = cursor.lastrowid

    return {
        "message": f"Đã phân công Mentor {mentor['ho_ten']} cho TTS {intern['ho_ten']}{prog_title}.",
        "ma_phan_cong": assignment_id,
        "mentor_id": mentor_id,
        "profile_id": profile_id,
        "program_id": target_program_id,
        "timeline_status": timeline_status,
        "intern_user_id": intern["ma_nguoi_dung"],
    }


def unassign_mentor_canonical(
    db: sqlite3.Connection,
    mentor_id: int,
    profile_id: int,
    program_id: Optional[int] = None,
) -> dict:
    """
    CANONICAL GỠ PHÂN CÔNG cho US12 và US30.
    """
    if program_id:
        assignment = db.execute("""
            SELECT p.ma_phan_cong, h.ma_nguoi_dung, p.ma_chuong_trinh,
                   c.ngay_bat_dau, c.ngay_ket_thuc, c.trang_thai AS trang_thai_ct,
                   h.trang_thai_thuc_tap
            FROM PHAN_CONG_MENTOR_TTS p
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = p.ma_ho_so
            LEFT JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = p.ma_chuong_trinh
            WHERE p.ma_nguoi_dung_mentor = ? AND p.ma_ho_so = ? AND p.ma_chuong_trinh = ?
        """, (mentor_id, profile_id, program_id)).fetchone()
    else:
        assignment = db.execute("""
            SELECT p.ma_phan_cong, h.ma_nguoi_dung, p.ma_chuong_trinh,
                   c.ngay_bat_dau, c.ngay_ket_thuc, c.trang_thai AS trang_thai_ct,
                   h.trang_thai_thuc_tap
            FROM PHAN_CONG_MENTOR_TTS p
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = p.ma_ho_so
            LEFT JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = p.ma_chuong_trinh
            WHERE p.ma_nguoi_dung_mentor = ? AND p.ma_ho_so = ?
            ORDER BY p.ma_phan_cong DESC LIMIT 1
        """, (mentor_id, profile_id)).fetchone()

    if not assignment:
        raise HTTPException(status_code=404, detail="Không tìm thấy phân công phù hợp để gỡ.")

    timeline_status = get_timeline_status(
        assignment["ngay_bat_dau"], assignment["ngay_ket_thuc"], assignment["trang_thai_ct"]
    ) if assignment["ma_chuong_trinh"] else (
        "CURRENT" if assignment["trang_thai_thuc_tap"] == "DangThucTap" else "HISTORICAL"
    )
    if timeline_status != "CURRENT":
        raise HTTPException(
            status_code=400,
            detail="Chỉ có thể gỡ phân công trong chương trình hiện tại.",
        )

    db.execute("DELETE FROM PHAN_CONG_MENTOR_TTS WHERE ma_phan_cong = ?", (assignment["ma_phan_cong"],))

    return {
        "message": "Đã gỡ phân công thực tập sinh.",
        "intern_user_id": assignment["ma_nguoi_dung"],
    }
