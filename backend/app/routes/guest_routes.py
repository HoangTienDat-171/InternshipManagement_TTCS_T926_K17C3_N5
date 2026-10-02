"""Guest portal routes for unauthenticated users."""
import os
import re
import secrets
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile

from ..database import DB_FILE, get_db
from ..guest_security import (
    check_guest_rate_limit,
    generate_captcha,
    validate_guest_cv_file,
    verify_captcha,
)

router = APIRouter(prefix="/api/guest", tags=["Guest Portal"])
GUEST_UPLOAD_DIR = Path(DB_FILE).parent / "uploads" / "guest_cv"
GUEST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/captcha")
def get_captcha():
    token, question = generate_captcha()
    return {"captcha_token": token, "question": question}


@router.get("/programs")
def list_guest_programs(
    keyword: str | None = Query(None),
    department_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db = Depends(get_db),
):
    conditions = ["c.trang_thai = 'DangMo'"]
    params = []

    if keyword and keyword.strip():
        conditions.append("(c.ten_ct LIKE ? OR c.mo_ta_cong_viec LIKE ? OR c.yeu_cau LIKE ?)")
        kw = f"%{keyword.strip()}%"
        params.extend([kw, kw, kw])

    if department_id:
        conditions.append("c.ma_phong_ban = ?")
        params.append(department_id)

    where_sql = " AND ".join(conditions)
    count_sql = f"SELECT COUNT(*) AS total FROM CHUONG_TRINH_THUC_TAP c WHERE {where_sql}"
    total = db.execute(count_sql, tuple(params)).fetchone()["total"]

    offset = (page - 1) * page_size
    query_sql = f"""
        SELECT c.ma_chuong_trinh, c.ma_ct, c.ten_ct, c.ma_phong_ban,
               p.ten_phong_ban, c.ngay_bat_dau, c.ngay_ket_thuc, c.chi_tieu,
               c.mo_ta_cong_viec, c.yeu_cau, c.quyen_loi
        FROM CHUONG_TRINH_THUC_TAP c
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = c.ma_phong_ban
        WHERE {where_sql}
        ORDER BY c.ngay_tao DESC
        LIMIT ? OFFSET ?
    """
    rows = db.execute(query_sql, tuple(params + [page_size, offset])).fetchall()

    items = []
    for r in rows:
        req_lower = (r["yeu_cau"] or "").lower()
        skills = []
        for tech in ["Python", "Java", "React", "NodeJS", "SQL", "DevOps", "AI", "QA/QC", "Figma", "Marketing"]:
            if tech.lower() in req_lower:
                skills.append(tech)
        if not skills:
            skills = ["CNTT", "Kỹ năng mềm"]

        items.append({
            "id": r["ma_chuong_trinh"],
            "code": r["ma_ct"],
            "title": r["ten_ct"],
            "department_id": r["ma_phong_ban"],
            "department_name": r["ten_phong_ban"] or "Chung",
            "start_date": r["ngay_bat_dau"],
            "end_date": r["ngay_ket_thuc"],
            "deadline": r["ngay_ket_thuc"],
            "vacancies": r["chi_tieu"],
            "description": r["mo_ta_cong_viec"] or "",
            "requirements": r["yeu_cau"] or "",
            "benefits": r["quyen_loi"] or "",
            "location": "Hà Nội",
            "skills": skills,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


@router.get("/programs/{program_id}")
def get_guest_program_detail(program_id: int, db = Depends(get_db)):
    row = db.execute("""
        SELECT c.ma_chuong_trinh, c.ma_ct, c.ten_ct, c.ma_phong_ban,
               p.ten_phong_ban, c.ngay_bat_dau, c.ngay_ket_thuc, c.chi_tieu,
               c.mo_ta_cong_viec, c.yeu_cau, c.quyen_loi, c.trang_thai
        FROM CHUONG_TRINH_THUC_TAP c
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = c.ma_phong_ban
        WHERE c.ma_chuong_trinh = ? AND c.trang_thai = 'DangMo'
    """, (program_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Vị trí thực tập không tồn tại hoặc đã đóng.")

    req_lower = (row["yeu_cau"] or "").lower()
    skills = []
    for tech in ["Python", "Java", "React", "NodeJS", "SQL", "DevOps", "AI", "QA/QC", "Figma", "Marketing"]:
        if tech.lower() in req_lower:
            skills.append(tech)
    if not skills:
        skills = ["CNTT", "Kỹ năng mềm"]

    return {
        "id": row["ma_chuong_trinh"],
        "code": row["ma_ct"],
        "title": row["ten_ct"],
        "department_id": row["ma_phong_ban"],
        "department_name": row["ten_phong_ban"] or "Chung",
        "start_date": row["ngay_bat_dau"],
        "end_date": row["ngay_ket_thuc"],
        "deadline": row["ngay_ket_thuc"],
        "vacancies": row["chi_tieu"],
        "description": row["mo_ta_cong_viec"] or "",
        "requirements": row["yeu_cau"] or "",
        "benefits": row["quyen_loi"] or "",
        "location": "Hà Nội",
        "skills": skills,
    }


@router.post("/apply")
async def submit_guest_application(
    request: Request,
    program_id: int = Form(...),
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    university: str = Form(...),
    major: str = Form(...),
    year_of_study: str = Form(...),
    expected_duration: str = Form(...),
    portfolio_link: str | None = Form(None),
    captcha_token: str = Form(...),
    captcha_answer: str = Form(...),
    cv_file: UploadFile = File(...),
    db = Depends(get_db),
):
    # 1. Rate Limiting Check (5 per 10 mins)
    check_guest_rate_limit(request, limit=5, window_seconds=600)

    # 2. Anti-Bot Captcha Verification
    if not verify_captcha(captcha_token, captcha_answer):
        raise HTTPException(status_code=400, detail="Mã bảo vệ (Captcha) không chính xác hoặc đã hết hạn.")

    # 3. Input Sanitization & Validation
    clean_name = " ".join(full_name.strip().split())
    clean_email = email.strip().lower()
    clean_phone = re.sub(r"[\s.-]", "", phone.strip())
    if not re.match(r"^0\d{9,10}$", clean_phone):
        raise HTTPException(status_code=400, detail="Số điện thoại không hợp lệ (10-11 chữ số, bắt đầu bằng 0).")
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", clean_email):
        raise HTTPException(status_code=400, detail="Email không đúng định dạng.")

    # 4. Verify Active Program
    program = db.execute(
        "SELECT ten_ct FROM CHUONG_TRINH_THUC_TAP WHERE ma_chuong_trinh = ? AND trang_thai = 'DangMo'",
        (program_id,)
    ).fetchone()
    if not program:
        raise HTTPException(status_code=404, detail="Chương trình thực tập không tồn tại hoặc đã ngừng nhận hồ sơ.")

    # 5. File Validation & Secure Storage
    content = await cv_file.read()
    mime_type = validate_guest_cv_file(cv_file.filename or "", content, max_size=5 * 1024 * 1024)
    file_ext = os.path.splitext(cv_file.filename or "")[1].lower()
    storage_filename = f"{uuid4().hex}{file_ext}"
    target_path = GUEST_UPLOAD_DIR / storage_filename
    target_path.write_bytes(content)

    # 6. Secure Random Tracking Code Generation
    tracking_code = f"APP-{secrets.token_hex(4).upper()}"
    client_ip = request.client.host if request.client else ""

    # 7. Atomic DB Write
    cursor = db.execute("""
        INSERT INTO HO_SO_UNG_TUYEN_GUEST (
            ma_tracking, ma_chuong_trinh, ho_ten, email, so_dien_thoai,
            truong_dai_hoc, chuyen_nganh, nam_hoc, thoi_gian_thuc_tap,
            link_portfolio, duong_dan_cv, ten_file_cv, kich_thuoc_file,
            mime_type, trang_thai, ip_address
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
    """, (
        tracking_code, program_id, clean_name, clean_email, clean_phone,
        university.strip(), major.strip(), year_of_study.strip(),
        expected_duration.strip(), portfolio_link.strip() if portfolio_link else None,
        str(target_path), os.path.basename(cv_file.filename or "cv.pdf"),
        len(content), mime_type, client_ip
    ))
    guest_app_id = cursor.lastrowid

    # 8. Queue Confirmation Email
    base_url = os.getenv("IMS_PORTAL_URL", "http://127.0.0.1:3000").strip().rstrip("/")
    tracking_link = f"{base_url}/tracking?code={tracking_code}&email={clean_email}"
    email_body = f"""Xin chào {clean_name},

Cảm ơn bạn đã nộp hồ sơ ứng tuyển vị trí: {program['ten_ct']}.
Hồ sơ của bạn đã được tiếp nhận thành công vào hệ thống tuyển dụng IMS.

MÃ TRA CỨU HỒ SƠ: {tracking_code}

Bạn có thể theo dõi tiến độ xét duyệt trực tiếp tại hệ thống:
{tracking_link}

Trân trọng,
Phòng Tuyển dụng Nhân sự IMS."""

    dedup_key = f"guest_app_{guest_app_id}_{tracking_code}"
    db.execute("""
        INSERT INTO EMAIL_OUTBOX (
            recipient_email, subject, body, template_type,
            reference_type, reference_id, deduplication_key, status, max_retry
        ) VALUES (?, ?, ?, 'guest_application_received', 'guest_application', ?, ?, 'PENDING', 4)
    """, (
        clean_email, f"[IMS] Xác nhận tiếp nhận hồ sơ ứng tuyển - {tracking_code}",
        email_body, str(guest_app_id), dedup_key
    ))
    db.commit()

    return {
        "success": True,
        "message": "Nộp hồ sơ ứng tuyển thành công!",
        "tracking_code": tracking_code,
        "email": clean_email,
        "candidate_name": clean_name,
        "position_title": program["ten_ct"]
    }


@router.post("/track")
def track_guest_application(
    tracking_code: str = Form(...),
    email: str = Form(...),
    db = Depends(get_db)
):
    code_clean = tracking_code.strip().upper()
    email_clean = email.strip().lower()

    row = db.execute("""
        SELECT g.ma_tracking, g.ho_ten, c.ten_ct, p.ten_phong_ban,
               g.ngay_ung_tuyen, g.trang_thai
        FROM HO_SO_UNG_TUYEN_GUEST g
        LEFT JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = g.ma_chuong_trinh
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = c.ma_phong_ban
        WHERE g.ma_tracking = ? AND LOWER(g.email) = ?
    """, (code_clean, email_clean)).fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy hồ sơ với Mã tra cứu và Email tương ứng."
        )

    return {
        "tracking_code": row["ma_tracking"],
        "candidate_name": row["ho_ten"],
        "position_title": row["ten_ct"] or "Vị trí thực tập",
        "department_name": row["ten_phong_ban"] or "Chung",
        "submission_date": str(row["ngay_ung_tuyen"]),
        "status": row["trang_thai"]
    }
