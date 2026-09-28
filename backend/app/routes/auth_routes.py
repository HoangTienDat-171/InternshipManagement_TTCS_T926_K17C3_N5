from fastapi import APIRouter, HTTPException, Depends, status, Request, Query, BackgroundTasks, File, Form, UploadFile
import sqlite3
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path, PurePosixPath
from uuid import uuid4
from ..database import get_db, hash_password, verify_password
from ..schemas import UserLogin, UserRegister, UserResponse, RoleAssign, UserStatusUpdate, UserProfileUpdate, PasswordChange
from ..security import new_session_token, token_digest, require_role, publish_force_logout, session_connections
from ..intern_workflow import sync_intern_approval
from ..notifications import create_notification
from .document_routes import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, UPLOAD_ROOT, valid_file_content

router = APIRouter(prefix="/api/auth", tags=["Authentication & Security"])

def validate_phone_number(phone: Optional[str]):
    if phone and not re.fullmatch(r"(03|05|07|08|09)\d{8}", phone):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 03, 05, 07, 08 hoặc 09.")

# Chuỗi hash Bcrypt giả lập phục vụ chống Timing Attack khi email không tồn tại
DUMMY_BCRYPT_HASH = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/Lew.nOQ2/y4g7e1xK"

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 5

def check_account_lockout(email: str, db: sqlite3.Connection):
    """Giai đoạn 3: Kiểm tra khóa tài khoản chống Brute-force"""
    cursor = db.cursor()
    cursor.execute("""
        SELECT failed_count, locked_until 
        FROM FAILED_LOGIN_ATTEMPTS 
        WHERE email = ?
    """, (email,))
    row = cursor.fetchone()
    if row and row["locked_until"]:
        try:
            locked_until_dt = datetime.fromisoformat(row["locked_until"])
            now = datetime.now()
            if locked_until_dt > now:
                remaining_seconds = int((locked_until_dt - now).total_seconds())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Phòng thủ Brute-force: Tài khoản tạm khóa do sai quá {MAX_FAILED_ATTEMPTS} lần! Vui lòng thử lại sau {remaining_seconds} giây."
                )
        except ValueError:
            pass
    return row

def record_login_attempt(email: str, success: bool, reason: str, ip: str, db: sqlite3.Connection):
    """Giai đoạn 3: Ghi vết nhật ký kiểm toán bảo mật và đếm số lần sai"""
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO NHAT_KY_DANG_NHAP (email, ip_address, thanh_cong, thong_tin)
        VALUES (?, ?, ?, ?)
    """, (email, ip, 1 if success else 0, reason))

    if success:
        cursor.execute("""
            INSERT INTO FAILED_LOGIN_ATTEMPTS (email, failed_count, locked_until, last_attempt)
            VALUES (?, 0, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(email) DO UPDATE SET failed_count = 0, locked_until = NULL, last_attempt = CURRENT_TIMESTAMP
        """, (email,))
    else:
        cursor.execute("SELECT failed_count FROM FAILED_LOGIN_ATTEMPTS WHERE email = ?", (email,))
        row = cursor.fetchone()
        new_count = (row["failed_count"] + 1) if row else 1
        
        locked_until_str = None
        if new_count >= MAX_FAILED_ATTEMPTS:
            locked_time = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
            locked_until_str = locked_time.isoformat()

        cursor.execute("""
            INSERT INTO FAILED_LOGIN_ATTEMPTS (email, failed_count, locked_until, last_attempt)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(email) DO UPDATE SET 
                failed_count = ?, 
                locked_until = ?, 
                last_attempt = CURRENT_TIMESTAMP
        """, (email, new_count, locked_until_str, new_count, locked_until_str))
    
    db.commit()

@router.post("/register", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def register_user(data: UserRegister, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """
    Yêu cầu:
    1. Khi tạo tài khoản thì mặc định là Thực tập sinh (vai_tro='ThucTapSinh').
    2. Sau khi tạo tài khoản thì phải đợi Quản lý thực tập sinh xét duyệt (trang_thai='ChoDuyet').
    """
    validate_phone_number(data.so_dien_thoai)
    if len(data.mat_khau) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chính sách bảo mật: Mật khẩu phải có độ dài tối thiểu 6 ký tự!"
        )

    email = data.email.strip().lower()
    cursor = db.cursor()
    cursor.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE LOWER(email) = ?", (email,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email đã được đăng ký trong hệ thống!"
        )

    # Mặc định là Thực tập sinh
    user_role = 'ThucTapSinh'
    # Trạng thái ban đầu: Phải đợi Quản lý thực tập sinh xét duyệt
    initial_status = 'ChoDuyet'

    hashed_pw = hash_password(data.mat_khau)

    cursor.execute("""
        INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, so_dien_thoai, vai_tro, trang_thai)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (data.ma_phong_ban, data.ho_ten, email, hashed_pw, data.so_dien_thoai, user_role, initial_status))
    
    new_user_id = cursor.lastrowid

    # Tạo hồ sơ thực tập sinh ban đầu ở trạng thái chờ duyệt
    cursor.execute("""
        INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
        VALUES (?, ?, 'ChoDuyet', 'DangThucTap')
    """, (new_user_id, "Chưa cập nhật"))

    client_ip = request.client.host if request.client else "127.0.0.1"
    record_login_attempt(email, True, "Đăng ký tài khoản (Chờ duyệt)", client_ip, db)

    managers = cursor.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro IN ('Admin', 'HR') AND trang_thai = 'HoatDong'").fetchall()
    for manager in managers:
        create_notification(db, manager["ma_nguoi_dung"], "Thực tập sinh mới chờ duyệt", f"{data.ho_ten.strip()} đã đăng ký tài khoản và đang chờ xét duyệt.")

    db.commit()

    return {
        "message": "Đăng ký tài khoản thành công! Tài khoản đang chờ Quản lý thực tập sinh xét duyệt trước khi có thể đăng nhập.",
        "ma_nguoi_dung": new_user_id,
        "email": email,
        "ho_ten": data.ho_ten,
        "vai_tro": user_role,
        "trang_thai": initial_status
    }


@router.post("/register-with-cv", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def register_user_with_cv(
    request: Request,
    ho_ten: str = Form(...),
    email: str = Form(...),
    mat_khau: str = Form(...),
    so_dien_thoai: Optional[str] = Form(None),
    cv: Optional[UploadFile] = File(None),
    db: sqlite3.Connection = Depends(get_db),
):
    """Đăng ký TTS và tùy chọn nộp CV trong cùng một giao dịch."""
    absolute_path = None
    try:
        validate_phone_number(so_dien_thoai)
        if len(mat_khau) < 6:
            raise HTTPException(status_code=400, detail="Mật khẩu phải có tối thiểu 6 ký tự.")
        clean_name = ho_ten.strip()
        clean_email = email.strip().lower()
        if not clean_name or len(clean_name) > 255 or not clean_email:
            raise HTTPException(status_code=400, detail="Vui lòng nhập họ tên và email hợp lệ.")

        cv_content = None
        original_name = None
        extension = None
        if cv is not None and cv.filename:
            original_name = PurePosixPath(cv.filename.replace("\\", "/")).name
            extension = Path(original_name).suffix.lower()
            if len(original_name) > 255 or extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(status_code=400, detail="CV phải là tệp PDF, DOCX hoặc PNG có tên hợp lệ.")
            cv_content = await cv.read(MAX_FILE_SIZE + 1)
            if not cv_content or len(cv_content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="CV phải có dung lượng từ 1 byte đến 15 MB.")
            if not valid_file_content(extension, cv_content):
                raise HTTPException(status_code=400, detail="Nội dung CV không khớp định dạng tệp.")

        cursor = db.cursor()
        if cursor.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE LOWER(email) = ?", (clean_email,)).fetchone():
            raise HTTPException(status_code=400, detail="Email đã được đăng ký trong hệ thống!")

        cursor.execute("""
            INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, so_dien_thoai, vai_tro, trang_thai)
            VALUES (NULL, ?, ?, ?, ?, 'ThucTapSinh', 'ChoDuyet')
        """, (clean_name, clean_email, hash_password(mat_khau), so_dien_thoai))
        new_user_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
            VALUES (?, ?, 'ChoDuyet', 'DangThucTap')
        """, (new_user_id, "Chưa cập nhật"))
        profile_id = cursor.lastrowid

        if cv_content is not None:
            storage_name = f"{uuid4().hex}{extension}"
            absolute_path = UPLOAD_ROOT / storage_name
            stored_path = PurePosixPath("documents", storage_name).as_posix()
            UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
            with absolute_path.open("xb") as stored_file:
                stored_file.write(cv_content)
            cursor.execute("""
                INSERT INTO TAI_LIEU_HO_SO
                    (ma_ho_so, loai_tai_lieu, duong_dan_file, ten_file, kich_thuoc)
                VALUES (?, 'CV', ?, ?, ?)
            """, (profile_id, stored_path, original_name, len(cv_content)))

        client_ip = request.client.host if request.client else "127.0.0.1"
        cursor.execute("""
            INSERT INTO NHAT_KY_DANG_NHAP (email, ip_address, thanh_cong, thong_tin)
            VALUES (?, ?, 1, 'Đăng ký tài khoản (Chờ duyệt)')
        """, (clean_email, client_ip))
        managers = cursor.execute("""
            SELECT ma_nguoi_dung FROM NGUOI_DUNG
            WHERE vai_tro IN ('Admin', 'HR') AND trang_thai = 'HoatDong'
        """).fetchall()
        for manager in managers:
            create_notification(
                db,
                manager["ma_nguoi_dung"],
                "Thực tập sinh mới chờ duyệt",
                f"{clean_name} đã đăng ký tài khoản" + (" và nộp CV" if cv_content is not None else "") + " đang chờ xét duyệt.",
            )
        db.commit()
        return {
            "message": "Đăng ký thành công. " + ("CV đã được gửi và đang chờ duyệt. " if cv_content is not None else "") + "Tài khoản đang chờ Admin/HR xét duyệt.",
            "ma_nguoi_dung": new_user_id,
            "email": clean_email,
            "ho_ten": clean_name,
            "vai_tro": "ThucTapSinh",
            "trang_thai": "ChoDuyet",
            "cv_da_nop": cv_content is not None,
        }
    except Exception:
        db.rollback()
        if absolute_path is not None:
            absolute_path.unlink(missing_ok=True)
        raise
    finally:
        if cv is not None:
            await cv.close()

@router.post("/login", response_model=Dict[str, Any])
def login(data: UserLogin, request: Request, background_tasks: BackgroundTasks, db: sqlite3.Connection = Depends(get_db)):
    """Đăng nhập hệ thống & kiểm tra trạng thái phê duyệt"""
    client_ip = request.client.host if request.client else "127.0.0.1"
    email_clean = data.email.strip().lower()

    # 1. Kiểm tra trạng thái khóa do Brute-force
    check_account_lockout(email_clean, db)

    cursor = db.cursor()
    cursor.execute("""
        SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.mat_khau, u.so_dien_thoai, 
               u.vai_tro, u.trang_thai, u.ma_phong_ban, p.ten_phong_ban
        FROM NGUOI_DUNG u
        LEFT JOIN PHONG_BAN p ON u.ma_phong_ban = p.ma_phong_ban
        WHERE LOWER(u.email) = ?
    """, (email_clean,))
    user = cursor.fetchone()

    # 2. Chống Timing Attack
    if not user:
        verify_password(data.mat_khau, DUMMY_BCRYPT_HASH)
        record_login_attempt(email_clean, False, "Tài khoản không tồn tại (Timing mitigation)", client_ip, db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác!"
        )

    # 3. Xác minh mật khẩu Bcrypt At-Rest
    is_valid = verify_password(data.mat_khau, user["mat_khau"])
    if not is_valid:
        record_login_attempt(email_clean, False, "Sai mật khẩu", client_ip, db)
        cursor.execute("SELECT failed_count FROM FAILED_LOGIN_ATTEMPTS WHERE email = ?", (email_clean,))
        row = cursor.fetchone()
        current_fails = row["failed_count"] if row else 1
        remaining = max(0, MAX_FAILED_ATTEMPTS - current_fails)

        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Tài khoản bị tạm khóa 5 phút do nhập sai {MAX_FAILED_ATTEMPTS} lần liên tiếp!"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Email hoặc mật khẩu không chính xác! (Còn {remaining} lần thử trước khi khóa)"
            )

    # 4. Yêu cầu: Sau khi tạo tài khoản thì phải đợi Quản lý thực tập sinh xét duyệt
    if user["trang_thai"] == "ChoDuyet":
        record_login_attempt(email_clean, False, "Đăng nhập bị từ chối: Đang chờ xét duyệt", client_ip, db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản của bạn đang chờ Quản lý thực tập sinh xét duyệt. Vui lòng quay lại sau khi được phê duyệt!"
        )
    elif user["trang_thai"] != "HoatDong":
        record_login_attempt(email_clean, False, "Tài khoản bị khóa", client_ip, db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa hoặc vô hiệu hóa bởi Quản trị viên!"
        )

    # 5. Đăng nhập thành công -> Reset bộ đếm brute force và ghi log
    record_login_attempt(email_clean, True, "Đăng nhập thành công", client_ip, db)

    user_dict = {
        "ma_nguoi_dung": user["ma_nguoi_dung"],
        "ho_ten": user["ho_ten"],
        "email": user["email"],
        "so_dien_thoai": user["so_dien_thoai"],
        "vai_tro": user["vai_tro"],
        "ma_phong_ban": user["ma_phong_ban"],
        "ten_phong_ban": user["ten_phong_ban"],
        "trang_thai": user["trang_thai"]
    }

    session_token, session_id = new_session_token()
    cursor.execute("SELECT session_id FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung = ?", (user["ma_nguoi_dung"],))
    previous_session = cursor.fetchone()
    cursor.execute("""
        INSERT INTO ACTIVE_SESSIONS (ma_nguoi_dung, token_hash, session_id)
        VALUES (?, ?, ?)
        ON CONFLICT(ma_nguoi_dung) DO UPDATE SET
            token_hash = excluded.token_hash, session_id = excluded.session_id
    """, (user["ma_nguoi_dung"], token_digest(session_token), session_id))
    db.commit()
    if previous_session:
        background_tasks.add_task(publish_force_logout, user["ma_nguoi_dung"], previous_session["session_id"])

    return {
        "message": "Đăng nhập thành công!",
        "token": session_token,
        "user": user_dict
    }

@router.post("/users", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def admin_create_user(data: UserRegister, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """
    Yêu cầu: Chức năng quản trị người dùng chỉ Admin mới được dùng.
    Admin trực tiếp tạo tài khoản mới với vai trò và phòng ban được chỉ định.
    """
    role_header = require_role(request)["vai_tro"]
    if role_header != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quyền truy cập bị từ chối: Chức năng quản trị người dùng chỉ Admin mới được dùng!"
        )

    validate_phone_number(data.so_dien_thoai)

    if len(data.mat_khau) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chính sách bảo mật: Mật khẩu phải có độ dài tối thiểu 6 ký tự!"
        )

    email = data.email.strip().lower()
    cursor = db.cursor()
    cursor.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE LOWER(email) = ?", (email,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email đã được đăng ký trong hệ thống!"
        )

    valid_roles = ['Admin', 'HR', 'Mentor', 'ThucTapSinh']
    user_role = data.vai_tro if data.vai_tro in valid_roles else 'ThucTapSinh'

    hashed_pw = hash_password(data.mat_khau)
    cursor.execute("""
        INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, so_dien_thoai, vai_tro, trang_thai)
        VALUES (?, ?, ?, ?, ?, ?, 'HoatDong')
    """, (data.ma_phong_ban, data.ho_ten, email, hashed_pw, data.so_dien_thoai, user_role))
    
    new_user_id = cursor.lastrowid

    # Nếu tạo tài khoản Thực tập sinh thì đồng thời khởi tạo hồ sơ thực tập
    if user_role == 'ThucTapSinh':
        cursor.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
            VALUES (?, 'Chưa cập nhật', 'DaDuyet', 'DangThucTap')
        """, (new_user_id,))
    elif user_role == 'Mentor':
        cursor.execute("INSERT INTO MENTOR_PROFILE (ma_nguoi_dung, so_tts_toi_da) VALUES (?, 3)", (new_user_id,))

    client_ip = request.client.host if request.client else "127.0.0.1"
    record_login_attempt(email, True, f"Admin tạo tài khoản ({user_role})", client_ip, db)

    db.commit()

    return {
        "message": f"Admin đã tạo tài khoản {data.ho_ten} ({user_role}) thành công!",
        "ma_nguoi_dung": new_user_id,
        "email": email,
        "ho_ten": data.ho_ten,
        "vai_tro": user_role,
        "trang_thai": "HoatDong"
    }

@router.put("/users/{id}/approve")
def approve_user(id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """
    Quản lý thực tập sinh (hoặc Admin) phê duyệt kích hoạt tài khoản
    """
    role_header = require_role(request)["vai_tro"]
    if role_header not in ["Admin", "HR"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quyền truy cập bị từ chối: Chỉ Quản lý thực tập sinh hoặc Admin mới có quyền phê duyệt!"
        )

    cursor = db.cursor()
    cursor.execute("""
        SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.vai_tro, u.trang_thai,
               h.trang_thai_xet_duyet AS trang_thai_ho_so
        FROM NGUOI_DUNG u LEFT JOIN HO_SO_THUC_TAP h ON h.ma_nguoi_dung = u.ma_nguoi_dung
        WHERE u.ma_nguoi_dung = ?
    """, (id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng")
    if user["vai_tro"] != "ThucTapSinh":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chỉ có thể duyệt tài khoản thực tập sinh.")

    cursor.execute("UPDATE HO_SO_THUC_TAP SET trang_thai_xet_duyet = 'DaDuyet' WHERE ma_nguoi_dung = ?", (id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy hồ sơ thực tập sinh")
    sync_intern_approval(cursor, id, "DaDuyet")
    if user["trang_thai_ho_so"] != "DaDuyet" or user["trang_thai"] != "HoatDong":
        create_notification(db, id, "Hồ sơ thực tập đã được duyệt", "Hồ sơ của bạn đã được duyệt và tài khoản đã được kích hoạt.")
    db.commit()

    return {
        "message": f"Đã phê duyệt tài khoản {user['ho_ten']} thành công!",
        "ma_nguoi_dung": id,
        "trang_thai": "HoatDong"
    }

@router.put("/users/{id}/reject")
def reject_user(id: int, request: Request, background_tasks: BackgroundTasks, db: sqlite3.Connection = Depends(get_db)):
    """
    Quản lý thực tập sinh (hoặc Admin) từ chối / khóa tài khoản
    """
    role_header = require_role(request)["vai_tro"]
    if role_header not in ["Admin", "HR"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quyền truy cập bị từ chối: Chỉ Quản lý thực tập sinh hoặc Admin mới có quyền từ chối/khóa!"
        )

    cursor = db.cursor()
    cursor.execute("""
        SELECT u.ma_nguoi_dung, u.ho_ten, u.vai_tro, u.trang_thai,
               h.trang_thai_xet_duyet AS trang_thai_ho_so, s.session_id
        FROM NGUOI_DUNG u LEFT JOIN ACTIVE_SESSIONS s ON s.ma_nguoi_dung = u.ma_nguoi_dung
        LEFT JOIN HO_SO_THUC_TAP h ON h.ma_nguoi_dung = u.ma_nguoi_dung
        WHERE u.ma_nguoi_dung = ?
    """, (id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng")
    if user["vai_tro"] != "ThucTapSinh":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chỉ có thể từ chối hồ sơ thực tập sinh.")

    cursor.execute("UPDATE HO_SO_THUC_TAP SET trang_thai_xet_duyet = 'TuChoi' WHERE ma_nguoi_dung = ?", (id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy hồ sơ thực tập sinh")
    sync_intern_approval(cursor, id, "TuChoi")
    if user["trang_thai_ho_so"] != "TuChoi" or user["trang_thai"] != "Khoa":
        create_notification(db, id, "Hồ sơ thực tập bị từ chối", "Hồ sơ của bạn đã bị từ chối. Hãy liên hệ Quản lý thực tập sinh để biết thêm chi tiết.")
    db.commit()
    if user["session_id"]:
        background_tasks.add_task(publish_force_logout, id, user["session_id"])

    return {
        "message": f"Đã từ chối/khóa tài khoản {user['ho_ten']}!",
        "ma_nguoi_dung": id,
        "trang_thai": "Khoa"
    }

@router.put("/users/{id}/role")
def assign_role(id: int, data: RoleAssign, request: Request, background_tasks: BackgroundTasks, db: sqlite3.Connection = Depends(get_db)):
    """
    Yêu cầu: Admin có thể phân quyền cho các role dưới
    (Admin, Quản lý thực tập sinh [HR], Mentor, Thực tập sinh)
    Chỉ Admin mới có quyền thao tác.
    """
    role_header = require_role(request)["vai_tro"]
    if role_header != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quyền truy cập bị từ chối: Chức năng quản trị người dùng chỉ Admin mới được dùng!"
        )

    valid_roles = ['Admin', 'HR', 'Mentor', 'ThucTapSinh']
    if data.vai_tro not in valid_roles:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Vai trò không hợp lệ: {data.vai_tro}")

    cursor = db.cursor()
    cursor.execute("SELECT ma_nguoi_dung, ho_ten, vai_tro, trang_thai FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?", (id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng")

    cursor.execute("""
        UPDATE NGUOI_DUNG 
        SET vai_tro = ?, ma_phong_ban = COALESCE(?, ma_phong_ban) 
        WHERE ma_nguoi_dung = ?
    """, (data.vai_tro, data.ma_phong_ban, id))

    # Nếu được phân quyền làm Thực tập sinh mà chưa có hồ sơ thì tự động tạo
    if data.vai_tro == 'ThucTapSinh':
        cursor.execute("SELECT ma_ho_so FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung = ?", (id,))
        if not cursor.fetchone():
            approval_status = "ChoDuyet" if user["trang_thai"] == "ChoDuyet" else "DaDuyet"
            cursor.execute("""
                INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
                VALUES (?, 'Chưa cập nhật', ?, 'DangThucTap')
            """, (id, approval_status))
    elif data.vai_tro == 'Mentor':
        cursor.execute("INSERT OR IGNORE INTO MENTOR_PROFILE (ma_nguoi_dung, so_tts_toi_da) VALUES (?, 3)", (id,))

    db.commit()
    cursor.execute("""
        SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai, u.vai_tro,
               u.trang_thai, u.ma_phong_ban, p.ten_phong_ban
        FROM NGUOI_DUNG u LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = u.ma_phong_ban
        WHERE u.ma_nguoi_dung = ?
    """, (id,))
    background_tasks.add_task(session_connections.publish, id, {"type": "ACCOUNT_UPDATED", "user": dict(cursor.fetchone())})

    return {
        "message": f"Admin đã phân quyền vai trò '{data.vai_tro}' cho người dùng {user['ho_ten']}",
        "ma_nguoi_dung": id,
        "vai_tro": data.vai_tro
    }

@router.put("/users/{id}/status")
def update_user_status(id: int, data: UserStatusUpdate, request: Request, background_tasks: BackgroundTasks, db: sqlite3.Connection = Depends(get_db)):
    """Cập nhật trạng thái người dùng (HoatDong, Khoa, ChoDuyet) - Chỉ Admin"""
    role_header = require_role(request)["vai_tro"]
    if role_header != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quyền truy cập bị từ chối: Chức năng quản trị người dùng chỉ Admin mới được dùng!"
        )

    if data.trang_thai not in ['HoatDong', 'Khoa', 'ChoDuyet']:
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ")

    cursor = db.cursor()
    cursor.execute("SELECT ma_nguoi_dung, ho_ten, vai_tro, trang_thai FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?", (id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng")

    if user["ma_nguoi_dung"] == 1 and data.trang_thai != 'HoatDong':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Không thể khóa tài khoản Quản trị viên gốc của hệ thống!")

    profile_status_changed = False
    if user["vai_tro"] == "ThucTapSinh" and data.trang_thai in ("HoatDong", "ChoDuyet"):
        approval_status = "DaDuyet" if data.trang_thai == "HoatDong" else "ChoDuyet"
        cursor.execute("SELECT ma_ho_so, trang_thai_xet_duyet FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung = ?", (id,))
        profile = cursor.fetchone()
        profile_status_changed = not profile or profile["trang_thai_xet_duyet"] != approval_status
        if profile:
            cursor.execute("UPDATE HO_SO_THUC_TAP SET trang_thai_xet_duyet = ? WHERE ma_nguoi_dung = ?", (approval_status, id))
        else:
            cursor.execute("""
                INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet)
                VALUES (?, 'Chưa cập nhật', ?)
            """, (id, approval_status))
    cursor.execute("UPDATE NGUOI_DUNG SET trang_thai = ? WHERE ma_nguoi_dung = ?", (data.trang_thai, id))
    if user["trang_thai"] != data.trang_thai or profile_status_changed:
        title, message = {
            "HoatDong": ("Tài khoản đã được kích hoạt", "Tài khoản của bạn đã được kích hoạt."),
            "ChoDuyet": ("Tài khoản đang chờ duyệt", "Tài khoản của bạn đang chờ xét duyệt."),
            "Khoa": ("Tài khoản đã bị khóa", "Tài khoản của bạn đã bị khóa. Vui lòng liên hệ quản trị viên."),
        }[data.trang_thai]
        create_notification(db, id, title, message)
    if data.trang_thai != "HoatDong":
        cursor.execute("DELETE FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung = ?", (id,))
    db.commit()
    if data.trang_thai != "HoatDong":
        background_tasks.add_task(session_connections.publish, id, {"type": "FORCE_LOGOUT", "message": "Tài khoản đã bị vô hiệu hóa."})
    return {"message": f"Admin đã cập nhật trạng thái của {user['ho_ten']} thành '{data.trang_thai}'!", "trang_thai": data.trang_thai}

@router.delete("/users/{id}")
def delete_user(id: int, request: Request, background_tasks: BackgroundTasks, db: sqlite3.Connection = Depends(get_db)):
    """Xóa tài khoản người dùng - Chỉ Admin mới có quyền thực hiện"""
    role_header = require_role(request)["vai_tro"]
    if role_header != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quyền truy cập bị từ chối: Chức năng quản trị người dùng chỉ Admin mới được dùng!"
        )

    if id == 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Không được phép xóa tài khoản Quản trị viên mặc định!")

    cursor = db.cursor()
    cursor.execute("SELECT ma_nguoi_dung, ho_ten FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?", (id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng")

    cursor.execute("DELETE FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung = ?", (id,))
    cursor.execute("DELETE FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?", (id,))
    db.commit()
    background_tasks.add_task(session_connections.publish, id, {"type": "FORCE_LOGOUT", "message": "Tài khoản đã bị xóa."})

    return {"message": f"Admin đã xóa tài khoản {user['ho_ten']} thành công!", "ma_nguoi_dung": id}

@router.post("/logout")
def logout(request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    token = request.headers.get("authorization", "").partition(" ")[2]
    db.execute("DELETE FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung = ? AND token_hash = ?", (user["ma_nguoi_dung"], token_digest(token)))
    db.commit()
    return {"message": "Đăng xuất thành công!", "status": "success"}


@router.get("/me")
def get_current_user(request: Request):
    user = require_role(request).copy()
    user.pop("session_id", None)
    return user

@router.put("/users/{user_id}/profile")
def update_profile(user_id: int, data: UserProfileUpdate, request: Request, background_tasks: BackgroundTasks, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    if user["ma_nguoi_dung"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn chỉ có thể cập nhật thông tin tài khoản của mình.")
    if not data.ho_ten.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Họ và tên không được để trống.")
    validate_phone_number(data.so_dien_thoai)
    cursor = db.cursor()
    cursor.execute("UPDATE NGUOI_DUNG SET ho_ten = ?, so_dien_thoai = ? WHERE ma_nguoi_dung = ?", (data.ho_ten.strip(), data.so_dien_thoai or None, user_id))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản.")
    db.commit()
    background_tasks.add_task(session_connections.publish, user_id, {
        "type": "ACCOUNT_UPDATED",
        "user": {key: value for key, value in {**user, "ho_ten": data.ho_ten.strip(), "so_dien_thoai": data.so_dien_thoai}.items() if key != "session_id"},
    })
    return {"message": "Đã cập nhật thông tin tài khoản.", "ho_ten": data.ho_ten.strip(), "so_dien_thoai": data.so_dien_thoai}

@router.put("/users/{user_id}/password")
def change_password(user_id: int, data: PasswordChange, request: Request, background_tasks: BackgroundTasks, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    if user["ma_nguoi_dung"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn chỉ có thể đổi mật khẩu tài khoản của mình.")
    if len(data.mat_khau_moi) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mật khẩu mới phải có tối thiểu 6 ký tự.")
    cursor = db.cursor()
    cursor.execute("SELECT mat_khau FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản.")
    if not verify_password(data.mat_khau_hien_tai, user["mat_khau"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mật khẩu hiện tại không chính xác.")
    cursor.execute("UPDATE NGUOI_DUNG SET mat_khau = ? WHERE ma_nguoi_dung = ?", (hash_password(data.mat_khau_moi), user_id))
    cursor.execute("DELETE FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung = ?", (user_id,))
    db.commit()
    background_tasks.add_task(session_connections.publish, user_id, {
        "type": "FORCE_LOGOUT", "message": "Mật khẩu đã được thay đổi. Vui lòng đăng nhập lại.",
    })
    return {"message": "Đổi mật khẩu thành công."}

@router.get("/users")
def get_all_users(
    request: Request,
    trang_thai: Optional[str] = Query(None, description="Lọc theo HoatDong, ChoDuyet, Khoa"),
    vai_tro: Optional[str] = Query(None, description="Lọc theo vai trò"),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, alias="pageSize", ge=1, le=100),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Yêu cầu: Chức năng quản trị người dùng chỉ Admin mới được dùng.
    Danh sách toàn bộ người dùng và vai trò chỉ phục vụ Quản trị viên (Admin).
    """
    role_header = require_role(request)["vai_tro"]
    if role_header != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quyền truy cập bị từ chối: Chức năng quản trị người dùng chỉ Admin mới được dùng!"
        )

    cursor = db.cursor()
    query = """
        SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai, u.vai_tro, 
               u.trang_thai, u.ma_phong_ban, p.ten_phong_ban, u.created_at
        FROM NGUOI_DUNG u
        LEFT JOIN PHONG_BAN p ON u.ma_phong_ban = p.ma_phong_ban
        WHERE 1=1
    """
    params = []
    if trang_thai and isinstance(trang_thai, str):
        query += " AND u.trang_thai = ?"
        params.append(trang_thai)
    if vai_tro and isinstance(vai_tro, str):
        query += " AND u.vai_tro = ?"
        params.append(vai_tro)

    # Giữ phản hồi dạng mảng cho các client cũ chưa truyền tham số phân trang.
    if page is None and page_size is None:
        query += " ORDER BY u.ma_nguoi_dung DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    effective_size = page_size or 10
    count_query = "SELECT COUNT(*) AS total_items FROM NGUOI_DUNG u LEFT JOIN PHONG_BAN p ON u.ma_phong_ban = p.ma_phong_ban WHERE 1=1"
    if trang_thai and isinstance(trang_thai, str):
        count_query += " AND u.trang_thai = ?"
    if vai_tro and isinstance(vai_tro, str):
        count_query += " AND u.vai_tro = ?"
    cursor.execute(count_query, params)
    total_items = cursor.fetchone()["total_items"]
    total_pages = (total_items + effective_size - 1) // effective_size if total_items else 0
    effective_page = min(page or 1, total_pages) if total_pages else 1
    query += " ORDER BY u.ma_nguoi_dung DESC LIMIT ? OFFSET ?"
    params.extend([effective_size, (effective_page - 1) * effective_size])
    cursor.execute(query, params)
    rows = cursor.fetchall()
    return {
        "items": [dict(row) for row in rows],
        "page": effective_page,
        "pageSize": effective_size,
        "totalItems": total_items,
        "totalPages": total_pages,
    }

@router.get("/security-audit-logs")
def get_security_audit_logs(request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Nhật ký bảo mật chỉ phục vụ Quản trị viên (Admin)"""
    role_header = require_role(request)["vai_tro"]
    if role_header != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quyền truy cập bị từ chối: Chỉ Quản trị viên (Admin) mới có quyền xem nhật ký bảo mật!"
        )

    cursor = db.cursor()
    cursor.execute("""
        SELECT id, email, ip_address, thanh_cong, thong_tin, thoi_gian
        FROM NHAT_KY_DANG_NHAP
        ORDER BY id DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()
    return [dict(r) for r in rows]
