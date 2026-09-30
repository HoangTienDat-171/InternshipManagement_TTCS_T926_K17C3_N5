import sqlite3
import os
import re
import bcrypt
import hashlib
from datetime import date, datetime
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

DB_FILE = os.path.abspath(os.getenv(
    "IMS_SQLITE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "internship.db"),
))
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _load_local_env():
    env_path = BACKEND_DIR / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_local_env()
DATABASE_BACKEND = os.getenv("IMS_DATABASE_BACKEND", "mysql").strip().lower()


class _HybridRow(dict):
    """Mapping row that preserves sqlite3.Row's integer-index behavior."""
    def __init__(self, row):
        super().__init__((key, _normalize_mysql_value(value)) for key, value in row.items())

    def __getitem__(self, key):
        if isinstance(key, int):
            key = tuple(self.keys())[key]
        return super().__getitem__(key)


def _normalize_mysql_value(value):
    # SQLite exposes DATE/DATETIME columns as ISO-like strings by default.
    # Keep that contract so existing response schemas and route callers work
    # identically after switching the storage backend to MySQL.
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _mysql_sql(statement: str) -> str:
    statement = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT IGNORE INTO", statement, flags=re.I)
    statement = re.sub(r"\bON\s+CONFLICT\s*\([^)]*\)\s*DO\s+UPDATE\s+SET\b", "ON DUPLICATE KEY UPDATE", statement, flags=re.I)
    statement = re.sub(r"\bexcluded\.([a-zA-Z_][\w]*)", r"VALUES(`\1`)", statement, flags=re.I)
    statement = re.sub(r"\s+COLLATE\s+NOCASE\b", "", statement, flags=re.I)
    statement = re.sub(r"^\s*BEGIN\s+IMMEDIATE\s*;?\s*$", "START TRANSACTION", statement, flags=re.I)
    return statement.replace("?", "%s")


class _MySQLCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, statement, params=()):
        try:
            self._cursor.execute(_mysql_sql(statement), params)
        except pymysql.err.IntegrityError as exc:
            raise sqlite3.IntegrityError(str(exc)) from exc
        return self

    def executemany(self, statement, params):
        try:
            self._cursor.executemany(_mysql_sql(statement), params)
        except pymysql.err.IntegrityError as exc:
            raise sqlite3.IntegrityError(str(exc)) from exc
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        return _HybridRow(row) if row is not None else None

    def fetchall(self):
        return [_HybridRow(row) for row in self._cursor.fetchall()]

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        self._cursor.close()


class _MySQLConnection:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        return _MySQLCursor(self._connection.cursor(DictCursor))

    def execute(self, statement, params=()):
        return self.cursor().execute(statement, params)

    def executemany(self, statement, params):
        return self.cursor().executemany(statement, params)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def _connect_mysql():
    required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Thiếu cấu hình MySQL: {', '.join(missing)}")
    connection = pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )
    return _MySQLConnection(connection)

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
    if DATABASE_BACKEND == "mysql":
        conn = _connect_mysql()
        try:
            yield conn
        finally:
            conn.close()
        return
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()

def get_db_connection():
    if DATABASE_BACKEND == "mysql":
        return _connect_mysql()
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _default_email_templates():
    return [
        ("MAU_DUYET_HO_SO", "Duyệt hồ sơ", "Hồ sơ thực tập của bạn đã được duyệt",
         "<p>Xin chào {ten_tts},</p><p>Hồ sơ đăng ký chương trình <strong>{ten_chuong_trinh}</strong> của bạn đã được duyệt.</p>",
         "KET_QUA_XET_DUYET"),
        ("MAU_TU_CHOI_HO_SO", "Từ chối hồ sơ", "Kết quả xét duyệt hồ sơ thực tập",
         "<p>Xin chào {ten_tts},</p><p>Hồ sơ đăng ký chương trình <strong>{ten_chuong_trinh}</strong> hiện chưa đáp ứng yêu cầu.</p>",
         "KET_QUA_XET_DUYET"),
        ("MAU_NHAC_BAO_CAO", "Nhắc nộp báo cáo", "Nhắc nộp báo cáo thực tập",
         "<p>Xin chào {ten_tts},</p><p>Vui lòng hoàn thành báo cáo thực tập trước ngày {ngay_het_han}.</p>",
         "THONG_BAO_CHUNG"),
        ("MAU_BO_SUNG_HO_SO", "Bổ sung hồ sơ", "Yêu cầu bổ sung hồ sơ thực tập",
         "<p>Xin chào {ten_tts},</p><p>Vui lòng kiểm tra và bổ sung các tài liệu còn thiếu trong hồ sơ.</p>",
         "BO_SUNG_HO_SO"),
        ("MAU_THONG_BAO_LICH", "Thông báo lịch", "Thông báo lịch thực tập",
         "<p>Xin chào {ten_tts},</p><p>Lịch thực tập của chương trình {ten_chuong_trinh} bắt đầu từ {ngay_bat_dau} đến {ngay_ket_thuc}.</p>",
         "THONG_BAO_CHUNG"),
    ]


def init_mysql_db():
    conn = get_db_connection()
    try:
        statements = [
            """CREATE TABLE IF NOT EXISTS ACTIVE_SESSIONS (
                ma_nguoi_dung INT PRIMARY KEY, token_hash VARCHAR(64) NOT NULL,
                session_id VARCHAR(64) NOT NULL,
                FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS FAILED_LOGIN_ATTEMPTS (
                id INT AUTO_INCREMENT PRIMARY KEY, email VARCHAR(254) NOT NULL UNIQUE,
                failed_count INT DEFAULT 0, locked_until DATETIME NULL,
                last_attempt DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS NHAT_KY_DANG_NHAP (
                id INT AUTO_INCREMENT PRIMARY KEY, email VARCHAR(254) NOT NULL,
                ip_address VARCHAR(64), thanh_cong TINYINT NOT NULL,
                thong_tin TEXT, thoi_gian DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS MENTOR_PROFILE (
                ma_nguoi_dung INT PRIMARY KEY, chuyen_mon VARCHAR(255),
                kinh_nghiem INT UNSIGNED, so_tts_toi_da INT UNSIGNED,
                FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS PHAN_CONG_MENTOR_TTS (
                ma_phan_cong INT AUTO_INCREMENT PRIMARY KEY,
                ma_nguoi_dung_mentor INT NOT NULL, ma_ho_so INT NOT NULL UNIQUE,
                ma_nguoi_phan_cong INT NULL, ngay_phan_cong DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                KEY idx_phan_cong_mentor (ma_nguoi_dung_mentor),
                FOREIGN KEY (ma_nguoi_dung_mentor) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE,
                FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
                FOREIGN KEY (ma_nguoi_phan_cong) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS CHUONG_TRINH_THUC_TAP (
                ma_chuong_trinh INT AUTO_INCREMENT PRIMARY KEY, ma_ct VARCHAR(40) NOT NULL UNIQUE,
                ten_ct VARCHAR(200) NOT NULL, ma_phong_ban INT NULL, ngay_bat_dau DATE NULL,
                ngay_ket_thuc DATE NULL, chi_tieu INT UNSIGNED NOT NULL,
                mo_ta_cong_viec TEXT, yeu_cau TEXT, quyen_loi TEXT,
                trang_thai ENUM('DangMo','TamDung','DaDong') NOT NULL DEFAULT 'DangMo',
                ngay_tao DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS UNG_TUYEN_CHUONG_TRINH (
                ma_ung_tuyen INT AUTO_INCREMENT PRIMARY KEY, ma_chuong_trinh INT NOT NULL,
                ma_ho_so INT NOT NULL, trang_thai ENUM('ChoDuyet','DaDuyet','TuChoi') NOT NULL DEFAULT 'ChoDuyet',
                ngay_ung_tuyen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, ngay_xet_duyet DATETIME NULL,
                nguoi_xet_duyet INT NULL, UNIQUE KEY uq_ung_tuyen_chuong_trinh (ma_chuong_trinh, ma_ho_so),
                KEY idx_ung_tuyen_chuong_trinh_trang_thai (ma_chuong_trinh, trang_thai),
                FOREIGN KEY (ma_chuong_trinh) REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE CASCADE,
                FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
                FOREIGN KEY (nguoi_xet_duyet) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS EMAIL_OUTBOX (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                recipient_email VARCHAR(254) NOT NULL, subject VARCHAR(255) NOT NULL,
                body TEXT NOT NULL, template_type VARCHAR(80) NOT NULL,
                reference_type VARCHAR(80), reference_id VARCHAR(100),
                deduplication_key VARCHAR(190) NOT NULL UNIQUE,
                status ENUM('PENDING','PROCESSING','SENT','FAILED','RETRY') NOT NULL DEFAULT 'PENDING',
                retry_count INT NOT NULL DEFAULT 0, max_retry INT NOT NULL DEFAULT 5,
                last_error TEXT, next_retry_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                sent_at DATETIME NULL,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                KEY idx_email_outbox_due (status, next_retry_at, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS EMAIL_TEMPLATES (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                template_code VARCHAR(100) NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL, subject VARCHAR(255) NOT NULL,
                body_html TEXT NOT NULL, category VARCHAR(50) NOT NULL,
                is_active TINYINT(1) NOT NULL DEFAULT 1, created_by INT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                deleted_at DATETIME NULL,
                KEY idx_email_templates_active (is_active, category),
                FOREIGN KEY (created_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
            """CREATE TABLE IF NOT EXISTS INTERNAL_MESSAGE_THREADS (
                id BIGINT AUTO_INCREMENT PRIMARY KEY, subject VARCHAR(255) NOT NULL,
                created_by INT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
            """CREATE TABLE IF NOT EXISTS INTERNAL_MESSAGES (
                id BIGINT AUTO_INCREMENT PRIMARY KEY, thread_id BIGINT NOT NULL,
                sender_id INT NULL, category VARCHAR(50) NOT NULL,
                subject VARCHAR(255) NOT NULL, content_html TEXT NOT NULL,
                parent_id BIGINT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                deleted_at DATETIME NULL,
                KEY idx_internal_messages_thread (thread_id, created_at),
                KEY idx_internal_messages_sender (sender_id, created_at),
                FOREIGN KEY (thread_id) REFERENCES INTERNAL_MESSAGE_THREADS(id) ON DELETE RESTRICT,
                FOREIGN KEY (sender_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL,
                FOREIGN KEY (parent_id) REFERENCES INTERNAL_MESSAGES(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
            """CREATE TABLE IF NOT EXISTS INTERNAL_MESSAGE_RECIPIENTS (
                id BIGINT AUTO_INCREMENT PRIMARY KEY, message_id BIGINT NOT NULL,
                receiver_id INT NULL, is_read TINYINT(1) NOT NULL DEFAULT 0,
                read_at DATETIME NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_internal_message_receiver (message_id, receiver_id),
                KEY idx_internal_recipient_inbox (receiver_id, is_read, created_at),
                KEY idx_internal_recipient_message (message_id),
                FOREIGN KEY (message_id) REFERENCES INTERNAL_MESSAGES(id) ON DELETE RESTRICT,
                FOREIGN KEY (receiver_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        ]
        for statement in statements:
            conn.execute(statement)

        columns = conn.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'TAI_LIEU_HO_SO'
        """).fetchall()
        column_names = {row["COLUMN_NAME"] for row in columns}
        if "ten_file" not in column_names:
            conn.execute("ALTER TABLE TAI_LIEU_HO_SO ADD COLUMN ten_file VARCHAR(255) NULL")
        if "kich_thuoc" not in column_names:
            conn.execute("ALTER TABLE TAI_LIEU_HO_SO ADD COLUMN kich_thuoc BIGINT UNSIGNED NULL")

        notification_columns = conn.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'THONG_BAO'
        """).fetchall()
        notification_column_names = {row["COLUMN_NAME"] for row in notification_columns}
        for name, definition in (
            ("loai", "VARCHAR(80) NOT NULL DEFAULT 'general'"),
            ("reference_type", "VARCHAR(80) NULL"),
            ("reference_id", "VARCHAR(100) NULL"),
            ("thoi_gian_doc", "DATETIME NULL"),
        ):
            if name not in notification_column_names:
                conn.execute(f"ALTER TABLE THONG_BAO ADD COLUMN {name} {definition}")

        if conn.execute("SELECT COUNT(*) AS total FROM PHONG_BAN").fetchone()["total"] == 0:
            conn.executemany("INSERT INTO PHONG_BAN (ten_phong_ban, mo_ta) VALUES (?, ?)", [
                ("Trung tâm Công nghệ Thông tin", "Phát triển phần mềm, giải pháp Web/App, AI và Cloud"),
                ("Khối Kỹ thuật Hạ tầng & An ninh mạng", "Vận hành hệ thống, DevOps và An toàn thông tin"),
                ("Phòng Dữ liệu & Trí tuệ nhân tạo (AI/Data)", "Phân tích dữ liệu lớn và giải pháp Machine Learning"),
                ("Phòng Kiểm thử & Đảm bảo chất lượng (QA/QC)", "Kiểm thử phần mềm và quản lý chất lượng dự án"),
            ])
        university_unique_key = conn.execute("""
            SELECT COUNT(*) AS total FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'TRUONG_DAI_HOC'
              AND INDEX_NAME = 'uq_truong_dai_hoc_ten'
        """).fetchone()["total"]
        if not university_unique_key:
            conn.execute("ALTER TABLE TRUONG_DAI_HOC ADD UNIQUE KEY uq_truong_dai_hoc_ten (ten_truong)")
        conn.execute("""
            INSERT IGNORE INTO MENTOR_PROFILE (ma_nguoi_dung, so_tts_toi_da)
            SELECT ma_nguoi_dung, 3 FROM NGUOI_DUNG WHERE vai_tro = 'Mentor'
        """)
        conn.execute("""
            INSERT IGNORE INTO HO_SO_THUC_TAP (ma_nguoi_dung)
            SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro = 'ThucTapSinh'
        """)
        conn.executemany("""
            INSERT IGNORE INTO EMAIL_TEMPLATES
                (template_code, title, subject, body_html, category)
            VALUES (?, ?, ?, ?, ?)
        """, _default_email_templates())
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    if DATABASE_BACKEND == "mysql":
        return init_mysql_db()
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

    # One active opaque session per account. Tokens themselves are never stored.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ACTIVE_SESSIONS (
        ma_nguoi_dung INTEGER PRIMARY KEY,
        token_hash TEXT NOT NULL,
        session_id TEXT NOT NULL,
        FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
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

    # Store upload metadata alongside the existing file path and review state.
    document_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(TAI_LIEU_HO_SO)")}
    if "ten_file" not in document_columns:
        cursor.execute("ALTER TABLE TAI_LIEU_HO_SO ADD COLUMN ten_file TEXT")
    if "kich_thuoc" not in document_columns:
        cursor.execute("ALTER TABLE TAI_LIEU_HO_SO ADD COLUMN kich_thuoc INTEGER")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS MENTOR_PROFILE (
        ma_nguoi_dung INTEGER PRIMARY KEY,
        chuyen_mon TEXT,
        kinh_nghiem INTEGER CHECK(kinh_nghiem IS NULL OR kinh_nghiem >= 0),
        so_tts_toi_da INTEGER CHECK(so_tts_toi_da IS NULL OR so_tts_toi_da >= 0),
        FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS PHAN_CONG_MENTOR_TTS (
        ma_phan_cong INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_nguoi_dung_mentor INTEGER NOT NULL,
        ma_ho_so INTEGER NOT NULL UNIQUE,
        ma_nguoi_phan_cong INTEGER,
        ngay_phan_cong DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_nguoi_dung_mentor) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE,
        FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
        FOREIGN KEY (ma_nguoi_phan_cong) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
    )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_phan_cong_mentor
        ON PHAN_CONG_MENTOR_TTS(ma_nguoi_dung_mentor)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS CHUONG_TRINH_THUC_TAP (
        ma_chuong_trinh INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_ct TEXT NOT NULL UNIQUE,
        ten_ct TEXT NOT NULL,
        ma_phong_ban INTEGER,
        ngay_bat_dau TEXT,
        ngay_ket_thuc TEXT,
        chi_tieu INTEGER NOT NULL CHECK(chi_tieu > 0),
        mo_ta_cong_viec TEXT,
        yeu_cau TEXT,
        quyen_loi TEXT,
        trang_thai TEXT NOT NULL DEFAULT 'DangMo' CHECK(trang_thai IN ('DangMo', 'TamDung', 'DaDong')),
        ngay_tao DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE SET NULL
    )
    """)

    program_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(CHUONG_TRINH_THUC_TAP)")}
    if "mo_ta_cong_viec" not in program_columns:
        cursor.execute("ALTER TABLE CHUONG_TRINH_THUC_TAP ADD COLUMN mo_ta_cong_viec TEXT")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS UNG_TUYEN_CHUONG_TRINH (
        ma_ung_tuyen INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_chuong_trinh INTEGER NOT NULL,
        ma_ho_so INTEGER NOT NULL,
        trang_thai TEXT NOT NULL DEFAULT 'ChoDuyet'
            CHECK(trang_thai IN ('ChoDuyet', 'DaDuyet', 'TuChoi')),
        ngay_ung_tuyen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ngay_xet_duyet DATETIME,
        nguoi_xet_duyet INTEGER,
        UNIQUE(ma_chuong_trinh, ma_ho_so),
        FOREIGN KEY (ma_chuong_trinh) REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE CASCADE,
        FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
        FOREIGN KEY (nguoi_xet_duyet) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
    )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ung_tuyen_chuong_trinh_trang_thai
        ON UNG_TUYEN_CHUONG_TRINH(ma_chuong_trinh, trang_thai)
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
        loai TEXT NOT NULL DEFAULT 'general',
        reference_type TEXT,
        reference_id TEXT,
        thoi_gian_doc DATETIME,
        FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
    );
    """)

    notification_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(THONG_BAO)")}
    for name, definition in (
        ("loai", "TEXT NOT NULL DEFAULT 'general'"),
        ("reference_type", "TEXT"),
        ("reference_id", "TEXT"),
        ("thoi_gian_doc", "DATETIME"),
    ):
        if name not in notification_columns:
            cursor.execute(f"ALTER TABLE THONG_BAO ADD COLUMN {name} {definition}")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS EMAIL_OUTBOX (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_email TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        template_type TEXT NOT NULL,
        reference_type TEXT,
        reference_id TEXT,
        deduplication_key TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'PENDING'
            CHECK(status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED', 'RETRY')),
        retry_count INTEGER NOT NULL DEFAULT 0,
        max_retry INTEGER NOT NULL DEFAULT 5,
        last_error TEXT,
        next_retry_at DATETIME,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        sent_at DATETIME,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_email_outbox_due
        ON EMAIL_OUTBOX(status, next_retry_at, created_at)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS EMAIL_TEMPLATES (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_code TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        subject TEXT NOT NULL,
        body_html TEXT NOT NULL,
        category TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deleted_at DATETIME,
        FOREIGN KEY (created_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
    )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_email_templates_active
        ON EMAIL_TEMPLATES(is_active, category)
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS INTERNAL_MESSAGE_THREADS (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        created_by INTEGER,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS INTERNAL_MESSAGES (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id INTEGER NOT NULL,
        sender_id INTEGER,
        category TEXT NOT NULL,
        subject TEXT NOT NULL,
        content_html TEXT NOT NULL,
        parent_id INTEGER,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deleted_at DATETIME,
        FOREIGN KEY (thread_id) REFERENCES INTERNAL_MESSAGE_THREADS(id) ON DELETE RESTRICT,
        FOREIGN KEY (sender_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL,
        FOREIGN KEY (parent_id) REFERENCES INTERNAL_MESSAGES(id) ON DELETE SET NULL
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_internal_messages_thread ON INTERNAL_MESSAGES(thread_id, created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_internal_messages_sender ON INTERNAL_MESSAGES(sender_id, created_at)")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS INTERNAL_MESSAGE_RECIPIENTS (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        receiver_id INTEGER,
        is_read INTEGER NOT NULL DEFAULT 0,
        read_at DATETIME,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(message_id, receiver_id),
        FOREIGN KEY (message_id) REFERENCES INTERNAL_MESSAGES(id) ON DELETE RESTRICT,
        FOREIGN KEY (receiver_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_internal_recipient_inbox ON INTERNAL_MESSAGE_RECIPIENTS(receiver_id, is_read, created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_internal_recipient_message ON INTERNAL_MESSAGE_RECIPIENTS(message_id)")
    cursor.executemany("""
        INSERT OR IGNORE INTO EMAIL_TEMPLATES
            (template_code, title, subject, body_html, category)
        VALUES (?, ?, ?, ?, ?)
    """, _default_email_templates())

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

    # Add a larger, repeatable demo roster without replacing users created by the team.
    demo_users = [
        (1, "Nguyễn Minh Khôi (Thực tập sinh)", "minh.khoi.nguyen@internship.vn", "0911000001", "ThucTapSinh", "HoatDong"),
        (2, "Trần Thị Ngọc (Thực tập sinh)", "ngoc.tran@internship.vn", "0381000002", "ThucTapSinh", "HoatDong"),
        (3, "Lê Quang Huy (Thực tập sinh)", "quang.huy.le@internship.vn", "0971000003", "ThucTapSinh", "HoatDong"),
        (4, "Phạm Gia Hân (Thực tập sinh)", "gia.han.pham@internship.vn", "0851000004", "ThucTapSinh", "HoatDong"),
        (1, "Võ Đức Long (Thực tập sinh)", "duc.long.vo@internship.vn", "0831000005", "ThucTapSinh", "HoatDong"),
        (3, "Bùi Thanh Trúc (Thực tập sinh)", "thanh.truc.bui@internship.vn", "0701000006", "ThucTapSinh", "HoatDong"),
        (2, "Đặng Hoàng Nam (Thực tập sinh)", "hoang.nam.dang@internship.vn", "0921000007", "ThucTapSinh", "HoatDong"),
        (4, "Đỗ Khánh Linh (Thực tập sinh)", "khanh.linh.do@internship.vn", "0861000008", "ThucTapSinh", "ChoDuyet"),
        (1, "Hoàng Tuấn Kiệt (Thực tập sinh)", "tuan.kiet.hoang@internship.vn", "0391000009", "ThucTapSinh", "Khoa"),
        (3, "Mai Phương Anh (Thực tập sinh)", "phuong.anh.mai@internship.vn", "0561000010", "ThucTapSinh", "HoatDong"),
        (1, "Nguyễn Hải Đăng (Mentor)", "hai.dang.nguyen@internship.vn", "0905555667", "Mentor", "HoatDong"),
        (2, "Trần Quốc Bảo (Mentor)", "quoc.bao.tran@internship.vn", "0905555668", "Mentor", "HoatDong"),
        (3, "Lê Thu Trang (HR)", "thu.trang.le@internship.vn", "0903333445", "HR", "HoatDong"),
        (1, "Quản trị viên dự phòng", "admin.demo2@internship.vn", "0901111223", "Admin", "HoatDong"),
    ]
    demo_emails = [user[2] for user in demo_users]
    placeholders = ",".join("?" for _ in demo_emails)
    cursor.execute(f"SELECT COUNT(*) FROM NGUOI_DUNG WHERE email IN ({placeholders})", demo_emails)
    missing_demo_users = cursor.fetchone()[0] < len(demo_users)
    if missing_demo_users:
        demo_password_hash = hash_password("123456")
        cursor.executemany("""
            INSERT OR IGNORE INTO NGUOI_DUNG
                (ma_phong_ban, ho_ten, email, mat_khau, so_dien_thoai, vai_tro, trang_thai)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [(*user[:3], demo_password_hash, *user[3:]) for user in demo_users])

    # Seed internship profiles for the demo interns so management screens are populated too.
    demo_profiles = [
        ("minh.khoi.nguyen@internship.vn", 1, "Kỹ thuật phần mềm", "DaDuyet", "DangThucTap"),
        ("ngoc.tran@internship.vn", 2, "An toàn thông tin", "DaDuyet", "DangThucTap"),
        ("quang.huy.le@internship.vn", 3, "Hệ thống thông tin", "ChoDuyet", "DangThucTap"),
        ("gia.han.pham@internship.vn", 4, "Trí tuệ nhân tạo", "DaDuyet", "DangThucTap"),
        ("duc.long.vo@internship.vn", 1, "Kỹ thuật phần mềm", "DaDuyet", "HoanThanh"),
        ("thanh.truc.bui@internship.vn", 2, "Khoa học dữ liệu", "DaDuyet", "DangThucTap"),
        ("hoang.nam.dang@internship.vn", 3, "Mạng máy tính", "DaDuyet", "DangThucTap"),
        ("khanh.linh.do@internship.vn", 4, "Thiết kế giao diện", "ChoDuyet", "DangThucTap"),
        ("tuan.kiet.hoang@internship.vn", 1, "Phát triển ứng dụng", "DaDuyet", "ThoiHoc"),
        ("phuong.anh.mai@internship.vn", 2, "Phân tích dữ liệu", "DaDuyet", "DangThucTap"),
    ]
    for email, university_id, major, approval, internship_status in demo_profiles:
        cursor.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email = ?", (email,))
        demo_user = cursor.fetchone()
        if demo_user:
            cursor.execute("""
                INSERT OR IGNORE INTO HO_SO_THUC_TAP
                    (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
                VALUES (?, ?, ?, ?, ?)
            """, (demo_user[0], university_id, major, approval, internship_status))

    conn.commit()
    conn.close()
