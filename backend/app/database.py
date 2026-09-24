import sqlite3
import os
import bcrypt
import hashlib
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "internship.db")

# Giai đoạn 2: Khi xử lý & lưu trữ (At Rest Security)
# Sử dụng Bcrypt với Salt ngẫu nhiên 12 vòng (Cost factor 12)
def hash_password(password: str) -> str:
    """
    Bảo mật At Rest: Băm mật khẩu bằng Bcrypt kết hợp Salt ngẫu nhiên 128-bit.
    Hàm băm chậm (slow-hash) ngăn chặn các đòn tấn công Rainbow table và GPU brute-force.
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Xác minh mật khẩu sử dụng Constant-Time check của Bcrypt chống Timing Attacks.
    Tự động hỗ trợ cả bcrypt ($2b$) và SHA256 cũ trong quá trình nâng cấp.
    """
    try:
        if hashed_password.startswith("$2a$") or hashed_password.startswith("$2b$"):
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        else:
            # Fallback legacy SHA-256
            legacy_hash = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
            return legacy_hash == hashed_password
    except Exception:
        return False

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Bảng Danh mục Phòng Ban
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS PHONG_BAN (
        ma_phong_ban INTEGER PRIMARY KEY AUTOINCREMENT,
        ten_phong_ban TEXT NOT NULL,
        mo_ta TEXT
    );
    """)

    # 2. Bảng Danh mục Trường Đại Học
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TRUONG_DAI_HOC (
        ma_truong INTEGER PRIMARY KEY AUTOINCREMENT,
        ten_truong TEXT NOT NULL,
        dia_chi TEXT,
        nguoi_lien_he TEXT,
        email_lien_he TEXT
    );
    """)

    # 3. Bảng Người Dùng (Tài khoản & Phân quyền)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS NGUOI_DUNG (
        ma_nguoi_dung INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_phong_ban INTEGER NULL,
        ho_ten TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        mat_khau TEXT NOT NULL,
        so_dien_thoai TEXT,
        vai_tro TEXT NOT NULL CHECK(vai_tro IN ('Admin', 'HR', 'Mentor', 'ThucTapSinh')),
        trang_thai TEXT DEFAULT 'ChoDuyet' CHECK(trang_thai IN ('HoatDong', 'Khoa', 'ChoDuyet')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE SET NULL
    );
    """)

    # 4. Bảng Hồ Sơ Thực Tập (Khởi tạo & Xét duyệt)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS HO_SO_THUC_TAP (
        ma_ho_so INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_nguoi_dung INTEGER NOT NULL UNIQUE,
        ma_truong INTEGER NULL,
        chuyen_nganh TEXT,
        trang_thai_xet_duyet TEXT DEFAULT 'ChoDuyet' CHECK(trang_thai_xet_duyet IN ('ChoDuyet', 'DaDuyet', 'TuChoi')),
        trang_thai_thuc_tap TEXT DEFAULT 'DangThucTap' CHECK(trang_thai_thuc_tap IN ('DangThucTap', 'HoanThanh', 'ThoiHoc')),
        ngay_tao DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE,
        FOREIGN KEY (ma_truong) REFERENCES TRUONG_DAI_HOC(ma_truong) ON DELETE SET NULL
    );
    """)

    # 5. Bảng Tài Liệu Hồ Sơ
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TAI_LIEU_HO_SO (
        ma_tai_lieu INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_ho_so INTEGER NOT NULL,
        loai_tai_lieu TEXT NOT NULL CHECK(loai_tai_lieu IN ('CV', 'DonXinThucTap', 'GiayGioiThieu')),
        duong_dan_file TEXT NOT NULL,
        trang_thai_duyet TEXT DEFAULT 'ChoDuyet' CHECK(trang_thai_duyet IN ('ChoDuyet', 'DaDuyet', 'TuChoi')),
        ngay_tai_len DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE
    );
    """)

    # 6. Bảng Thông Báo
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS THONG_BAO (
        ma_thong_bao INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_nguoi_dung INTEGER NOT NULL,
        tieu_de TEXT NOT NULL,
        noi_dung TEXT,
        kenh TEXT DEFAULT 'Email' CHECK(kenh IN ('Email', 'App')),
        da_doc INTEGER DEFAULT 0,
        thoi_gian_gui DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
    );
    """)

    # Giai đoạn 3: Cơ chế phòng thủ tầng ứng dụng (Application Layer Defense)
    # 7. Bảng theo dõi số lần đăng nhập sai chống Brute-force & Account Lockout
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS FAILED_LOGIN_ATTEMPTS (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        failed_count INTEGER DEFAULT 0,
        locked_until DATETIME NULL,
        last_attempt DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 8. Bảng Nhật ký Đăng nhập & Kiểm toán Bảo mật (Security Audit Log)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS NHAT_KY_DANG_NHAP (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        ip_address TEXT,
        thanh_cong INTEGER NOT NULL, -- 1: Thành công, 0: Thất bại
        thong_tin TEXT,
        thoi_gian DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Seed master data if empty
    cursor.execute("SELECT COUNT(*) FROM PHONG_BAN")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
        INSERT INTO PHONG_BAN (ten_phong_ban, mo_ta) VALUES (?, ?)
        """, [
            ("Trung tâm Công nghệ Thông tin", "Phát triển phần mềm, giải pháp Web/App, AI và Cloud"),
            ("Khối Kỹ thuật Hạ tầng & An ninh mạng", "Vận hành hệ thống, DevOps và An toàn thông tin"),
            ("Phòng Dữ liệu & Trí tuệ nhân tạo (AI/Data)", "Phân tích dữ liệu lớn và giải pháp Machine Learning"),
            ("Phòng Kiểm thử & Đảm bảo chất lượng (QA/QC)", "Kiểm thử phần mềm và quản lý chất lượng dự án")
        ])

    cursor.execute("SELECT COUNT(*) FROM TRUONG_DAI_HOC")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
        INSERT INTO TRUONG_DAI_HOC (ten_truong, dia_chi, nguoi_lien_he, email_lien_he) VALUES (?, ?, ?, ?)
        """, [
            ("Đại học Bách Khoa Hà Nội", "Số 1 Đại Cồ Việt, Hai Bà Trưng, Hà Nội", "ThS. Nguyễn Văn A", "contact@hust.edu.vn"),
            ("Đại học Quốc gia Hà Nội (UET)", "144 Xuân Thủy, Cầu Giấy, Hà Nội", "TS. Trần Thị B", "contact@uet.vnu.edu.vn"),
            ("Học viện Công nghệ Bưu chính Viễn thông (PTIT)", "Km10 Đường Nguyễn Trãi, Hà Đông, Hà Nội", "ThS. Lê Hoàng C", "contact@ptit.edu.vn"),
            ("Đại học FPT", "Khu CNC Hòa Lạc, Thạch Thất, Hà Nội", "ThS. Phạm Tuấn D", "contact@fpt.edu.vn")
        ])

    # Seed users with Bcrypt hashes
    cursor.execute("SELECT COUNT(*) FROM NGUOI_DUNG")
    if cursor.fetchone()[0] == 0:
        pw_hash = hash_password("123456")
        cursor.executemany("""
        INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, so_dien_thoai, vai_tro, trang_thai)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, "Quản Trị Viên Hệ Thống", "admin@internship.vn", pw_hash, "0901111222", "Admin", "HoatDong"),
            (1, "Trần Thu Hà (Quản lý TTS)", "hr@internship.vn", pw_hash, "0903333444", "HR", "HoatDong"),
            (1, "Nguyễn Văn Hướng (Mentor)", "mentor@internship.vn", pw_hash, "0905555666", "Mentor", "HoatDong"),
            (1, "Lê Minh Tuấn (Thực tập sinh)", "tuan.lm@internship.vn", pw_hash, "0907777888", "ThucTapSinh", "HoatDong"),
            (3, "Hoàng Lan Anh (Thực tập sinh)", "lananh.hoang@internship.vn", pw_hash, "0909999000", "ThucTapSinh", "HoatDong")
        ])

        # Link sample interns in HO_SO_THUC_TAP
        cursor.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email = 'tuan.lm@internship.vn'")
        u1 = cursor.fetchone()
        if u1:
            cursor.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
            VALUES (?, ?, ?, ?, ?)
            """, (u1[0], 1, "Công nghệ thông tin - Kỹ thuật phần mềm", "DaDuyet", "DangThucTap"))

        cursor.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email = 'lananh.hoang@internship.vn'")
        u2 = cursor.fetchone()
        if u2:
            cursor.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
            VALUES (?, ?, ?, ?, ?)
            """, (u2[0], 2, "Khoa học Dữ liệu & Trí tuệ Nhân tạo", "ChoDuyet", "DangThucTap"))
    else:
        # Upgrade any existing non-bcrypt password to bcrypt for sample accounts
        cursor.execute("SELECT ma_nguoi_dung, email, mat_khau FROM NGUOI_DUNG")
        users = cursor.fetchall()
        for u in users:
            pw = u["mat_khau"]
            if not (pw.startswith("$2a$") or pw.startswith("$2b$")):
                # rehash with bcrypt
                new_bcrypt_hash = hash_password("123456")
                cursor.execute("UPDATE NGUOI_DUNG SET mat_khau = ? WHERE ma_nguoi_dung = ?", (new_bcrypt_hash, u["ma_nguoi_dung"]))

    conn.commit()
    conn.close()
