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


def has_password_change_column(db) -> bool:
    """Return whether the configured schema supports forced first-login password changes."""
    if DATABASE_BACKEND == "mysql":
        return db.execute("""
            SELECT 1 AS present FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'NGUOI_DUNG'
              AND COLUMN_NAME = 'must_change_password' LIMIT 1
        """).fetchone() is not None
    return any(row["name"] == "must_change_password" for row in db.execute("PRAGMA table_info(NGUOI_DUNG)").fetchall())


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
            """CREATE TABLE IF NOT EXISTS NHIEM_VU_THUC_TAP (
                ma_nhiem_vu BIGINT AUTO_INCREMENT PRIMARY KEY,
                ma_ho_so INT NOT NULL,
                ma_nguoi_dung_mentor INT NOT NULL,
                tieu_de VARCHAR(200) NOT NULL,
                noi_dung TEXT NULL,
                han_hoan_thanh DATE NOT NULL,
                do_uu_tien ENUM('LOW','MEDIUM','HIGH','URGENT') NOT NULL DEFAULT 'MEDIUM',
                trang_thai ENUM('TODO','IN_PROGRESS','COMPLETED','CANCELLED') NOT NULL DEFAULT 'TODO',
                progress_percent TINYINT UNSIGNED NOT NULL DEFAULT 0,
                progress_note VARCHAR(2000) NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                KEY idx_nhiem_vu_mentor (ma_nguoi_dung_mentor, created_at),
                KEY idx_nhiem_vu_ho_so (ma_ho_so, created_at),
                KEY idx_nhiem_vu_filters (trang_thai, do_uu_tien, han_hoan_thanh),
                FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
                FOREIGN KEY (ma_nguoi_dung_mentor) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS LICH_SU_TIEN_DO_CONG_VIEC (
                ma_lich_su BIGINT AUTO_INCREMENT PRIMARY KEY,
                ma_nhiem_vu BIGINT NOT NULL,
                updated_by INT NOT NULL,
                old_progress TINYINT UNSIGNED NOT NULL,
                new_progress TINYINT UNSIGNED NOT NULL,
                old_status ENUM('TODO','IN_PROGRESS','COMPLETED','CANCELLED') NOT NULL,
                new_status ENUM('TODO','IN_PROGRESS','COMPLETED','CANCELLED') NOT NULL,
                note VARCHAR(2000) NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                KEY idx_task_progress_history (ma_nhiem_vu, created_at, ma_lich_su),
                KEY idx_task_progress_actor (updated_by),
                FOREIGN KEY (ma_nhiem_vu) REFERENCES NHIEM_VU_THUC_TAP(ma_nhiem_vu) ON DELETE RESTRICT,
                FOREIGN KEY (updated_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
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
            """CREATE TABLE IF NOT EXISTS BAO_CAO_TUAN (
                ma_bao_cao BIGINT AUTO_INCREMENT PRIMARY KEY,
                ma_ho_so INT NOT NULL,
                ma_chuong_trinh INT NOT NULL,
                week_start DATE NOT NULL,
                week_end DATE NOT NULL,
                work_content TEXT NOT NULL,
                results TEXT NOT NULL,
                difficulties TEXT NOT NULL,
                trang_thai ENUM('DRAFT','SUBMITTED') NOT NULL DEFAULT 'DRAFT',
                submitted_at DATETIME NULL,
                attachment_storage_key VARCHAR(80) NULL UNIQUE,
                attachment_original_name VARCHAR(255) NULL,
                attachment_mime_type VARCHAR(127) NULL,
                attachment_file_size BIGINT UNSIGNED NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_bao_cao_tuan_context (ma_ho_so, ma_chuong_trinh, week_start),
                KEY idx_bao_cao_tuan_profile_status (ma_ho_so, trang_thai, week_start),
                KEY idx_bao_cao_tuan_program (ma_chuong_trinh, week_start),
                FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
                FOREIGN KEY (ma_chuong_trinh) REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE RESTRICT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS NHAN_XET_BAO_CAO_TUAN (
                ma_nhan_xet BIGINT AUTO_INCREMENT PRIMARY KEY,
                ma_bao_cao BIGINT NOT NULL,
                reviewed_by INT NOT NULL,
                comment TEXT NOT NULL,
                reviewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_nhan_xet_bao_cao (ma_bao_cao),
                KEY idx_nhan_xet_mentor (reviewed_by, reviewed_at),
                FOREIGN KEY (ma_bao_cao) REFERENCES BAO_CAO_TUAN(ma_bao_cao) ON DELETE RESTRICT,
                FOREIGN KEY (reviewed_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS HOP_DONG_THUC_TAP (
                ma_hop_dong BIGINT AUTO_INCREMENT PRIMARY KEY,
                ma_ho_so INT NOT NULL,
                original_file_name VARCHAR(255) NOT NULL,
                storage_key VARCHAR(80) NOT NULL UNIQUE,
                mime_type VARCHAR(127) NOT NULL,
                file_size BIGINT UNSIGNED NOT NULL,
                trang_thai VARCHAR(40) NOT NULL DEFAULT 'PENDING_CONFIRMATION',
                uploaded_by INT NULL,
                confirmed_by INT NULL,
                confirmed_at DATETIME NULL,
                rejected_by INT NULL,
                rejected_at DATETIME NULL,
                rejection_reason VARCHAR(500) NULL,
                uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                CONSTRAINT chk_hop_dong_status CHECK (trang_thai IN ('PENDING_CONFIRMATION','CONFIRMED','REJECTED')),
                KEY idx_hop_dong_profile (ma_ho_so),
                KEY idx_hop_dong_uploaded_at (uploaded_at),
                FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
                FOREIGN KEY (uploaded_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL,
                FOREIGN KEY (confirmed_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL,
                FOREIGN KEY (rejected_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS HOP_DONG_THUC_TAP_LICH_SU (
                history_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                ma_hop_dong BIGINT NOT NULL,
                action VARCHAR(20) NOT NULL,
                old_status VARCHAR(40) NULL,
                new_status VARCHAR(40) NOT NULL,
                actor_id INT NULL,
                actor_name VARCHAR(120) NOT NULL,
                actor_role VARCHAR(40) NOT NULL,
                reason VARCHAR(500) NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT chk_contract_history_action CHECK (action IN ('UPLOADED','CONFIRMED','REJECTED')),
                UNIQUE KEY uq_contract_history_action (ma_hop_dong, action),
                KEY idx_contract_history_timeline (ma_hop_dong, created_at, history_id),
                FOREIGN KEY (ma_hop_dong) REFERENCES HOP_DONG_THUC_TAP(ma_hop_dong) ON DELETE RESTRICT,
                FOREIGN KEY (actor_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS EMAIL_OUTBOX (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                recipient_email VARCHAR(254) NOT NULL, subject VARCHAR(255) NOT NULL,
                body TEXT NOT NULL, body_html LONGTEXT NULL,
                has_attachments TINYINT(1) NOT NULL DEFAULT 0,
                template_type VARCHAR(80) NOT NULL,
                reference_type VARCHAR(80), reference_id VARCHAR(100),
                deduplication_key VARCHAR(190) NOT NULL UNIQUE,
                dedup_hash VARCHAR(64) NULL,
                status ENUM('PENDING','PROCESSING','SENT','FAILED','RETRY') NOT NULL DEFAULT 'PENDING',
                retry_count INT NOT NULL DEFAULT 0, max_retry INT NOT NULL DEFAULT 4,
                last_error TEXT, next_retry_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                sent_at DATETIME NULL,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                KEY idx_email_outbox_due (status, next_retry_at, created_at),
                KEY idx_email_dedup (recipient_email, dedup_hash, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS EMAIL_DEDUP_LOCKS (
                recipient_email VARCHAR(254) NOT NULL,
                dedup_hash VARCHAR(64) NOT NULL,
                expires_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_outbox_id BIGINT NULL,
                PRIMARY KEY (recipient_email, dedup_hash),
                KEY idx_email_dedup_expires (expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
            """CREATE TABLE IF NOT EXISTS EMAIL_ATTACHMENTS (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                email_id BIGINT NOT NULL,
                filename VARCHAR(255) NOT NULL,
                file_path VARCHAR(500) NOT NULL,
                mime_type VARCHAR(127) NOT NULL,
                file_size BIGINT UNSIGNED NOT NULL,
                disposition ENUM('attachment', 'inline') NOT NULL DEFAULT 'attachment',
                content_id VARCHAR(100) NULL,
                checksum_sha256 CHAR(64) NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                KEY idx_email_attachments_email_id (email_id, disposition),
                CONSTRAINT fk_email_attachments_outbox FOREIGN KEY (email_id) REFERENCES EMAIL_OUTBOX(id) ON DELETE CASCADE
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

        user_columns = conn.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'NGUOI_DUNG'
        """).fetchall()
        user_column_names = {row["COLUMN_NAME"] for row in user_columns}
        if "must_change_password" not in user_column_names:
            conn.execute("ALTER TABLE NGUOI_DUNG ADD COLUMN must_change_password TINYINT(1) NOT NULL DEFAULT 0 AFTER mat_khau")

        outbox_columns = conn.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'EMAIL_OUTBOX'
        """).fetchall()
        outbox_column_names = {row["COLUMN_NAME"] for row in outbox_columns}
        if "body_html" not in outbox_column_names:
            conn.execute("ALTER TABLE EMAIL_OUTBOX ADD COLUMN body_html LONGTEXT NULL AFTER body")
        if "has_attachments" not in outbox_column_names:
            conn.execute("ALTER TABLE EMAIL_OUTBOX ADD COLUMN has_attachments TINYINT(1) NOT NULL DEFAULT 0 AFTER body_html")
        if "dedup_hash" not in outbox_column_names:
            conn.execute("ALTER TABLE EMAIL_OUTBOX ADD COLUMN dedup_hash VARCHAR(64) NULL AFTER deduplication_key")

        task_columns = conn.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'NHIEM_VU_THUC_TAP'
        """).fetchall()
        task_column_names = {row["COLUMN_NAME"] for row in task_columns}
        if "progress_percent" not in task_column_names:
            conn.execute("""
                ALTER TABLE NHIEM_VU_THUC_TAP
                ADD COLUMN progress_percent TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER trang_thai
            """)
        if "progress_note" not in task_column_names:
            conn.execute("""
                ALTER TABLE NHIEM_VU_THUC_TAP
                ADD COLUMN progress_note VARCHAR(2000) NULL AFTER progress_percent
            """)

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
            INSERT IGNORE INTO HO_SO_THUC_TAP
                (ma_nguoi_dung, trang_thai_xet_duyet, trang_thai_thuc_tap)
            SELECT ma_nguoi_dung,
                   CASE WHEN trang_thai = 'ChoDuyet' THEN 'ChoDuyet' ELSE 'DaDuyet' END,
                   CASE WHEN trang_thai = 'ChoDuyet' THEN NULL ELSE 'DangThucTap' END
            FROM NGUOI_DUNG WHERE vai_tro = 'ThucTapSinh'
        """)
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
        must_change_password INTEGER NOT NULL DEFAULT 0,
        so_dien_thoai TEXT,
        vai_tro TEXT NOT NULL CHECK(vai_tro IN ('Admin', 'HR', 'Mentor', 'ThucTapSinh')),
        trang_thai TEXT DEFAULT 'ChoDuyet' CHECK(trang_thai IN ('HoatDong', 'Khoa', 'ChoDuyet')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE SET NULL
    );
    """)

    user_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(NGUOI_DUNG)")}
    if "must_change_password" not in user_columns:
        cursor.execute("ALTER TABLE NGUOI_DUNG ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")

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
    CREATE TABLE IF NOT EXISTS NHIEM_VU_THUC_TAP (
        ma_nhiem_vu INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_ho_so INTEGER NOT NULL,
        ma_nguoi_dung_mentor INTEGER NOT NULL,
        tieu_de TEXT NOT NULL CHECK(length(tieu_de) BETWEEN 1 AND 200),
        noi_dung TEXT CHECK(noi_dung IS NULL OR length(noi_dung) <= 5000),
        han_hoan_thanh TEXT NOT NULL,
        do_uu_tien TEXT NOT NULL DEFAULT 'MEDIUM'
            CHECK(do_uu_tien IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')),
        trang_thai TEXT NOT NULL DEFAULT 'TODO'
            CHECK(trang_thai IN ('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
        progress_percent INTEGER NOT NULL DEFAULT 0
            CHECK(progress_percent BETWEEN 0 AND 100),
        progress_note TEXT CHECK(progress_note IS NULL OR length(progress_note) <= 2000),
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
        FOREIGN KEY (ma_nguoi_dung_mentor) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nhiem_vu_mentor ON NHIEM_VU_THUC_TAP(ma_nguoi_dung_mentor, created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nhiem_vu_ho_so ON NHIEM_VU_THUC_TAP(ma_ho_so, created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nhiem_vu_filters ON NHIEM_VU_THUC_TAP(trang_thai, do_uu_tien, han_hoan_thanh)")

    task_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(NHIEM_VU_THUC_TAP)")}
    if "progress_percent" not in task_columns:
        cursor.execute("ALTER TABLE NHIEM_VU_THUC_TAP ADD COLUMN progress_percent INTEGER NOT NULL DEFAULT 0 CHECK(progress_percent BETWEEN 0 AND 100)")
    if "progress_note" not in task_columns:
        cursor.execute("ALTER TABLE NHIEM_VU_THUC_TAP ADD COLUMN progress_note TEXT CHECK(progress_note IS NULL OR length(progress_note) <= 2000)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS LICH_SU_TIEN_DO_CONG_VIEC (
        ma_lich_su INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_nhiem_vu INTEGER NOT NULL,
        updated_by INTEGER NOT NULL,
        old_progress INTEGER NOT NULL CHECK(old_progress BETWEEN 0 AND 100),
        new_progress INTEGER NOT NULL CHECK(new_progress BETWEEN 0 AND 100),
        old_status TEXT NOT NULL CHECK(old_status IN ('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
        new_status TEXT NOT NULL CHECK(new_status IN ('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
        note TEXT CHECK(note IS NULL OR length(note) <= 2000),
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_nhiem_vu) REFERENCES NHIEM_VU_THUC_TAP(ma_nhiem_vu) ON DELETE RESTRICT,
        FOREIGN KEY (updated_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_progress_history ON LICH_SU_TIEN_DO_CONG_VIEC(ma_nhiem_vu, created_at, ma_lich_su)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_progress_actor ON LICH_SU_TIEN_DO_CONG_VIEC(updated_by)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS BAO_CAO_TUAN (
        ma_bao_cao INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_ho_so INTEGER NOT NULL,
        ma_chuong_trinh INTEGER NOT NULL,
        week_start TEXT NOT NULL,
        week_end TEXT NOT NULL,
        work_content TEXT NOT NULL DEFAULT '' CHECK(length(work_content) <= 10000),
        results TEXT NOT NULL DEFAULT '' CHECK(length(results) <= 10000),
        difficulties TEXT NOT NULL DEFAULT '' CHECK(length(difficulties) <= 10000),
        trang_thai TEXT NOT NULL DEFAULT 'DRAFT' CHECK(trang_thai IN ('DRAFT', 'SUBMITTED')),
        submitted_at DATETIME,
        attachment_storage_key TEXT UNIQUE,
        attachment_original_name TEXT,
        attachment_mime_type TEXT,
        attachment_file_size INTEGER CHECK(attachment_file_size IS NULL OR attachment_file_size > 0),
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ma_ho_so, ma_chuong_trinh, week_start),
        FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
        FOREIGN KEY (ma_chuong_trinh) REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE RESTRICT
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bao_cao_tuan_profile_status ON BAO_CAO_TUAN(ma_ho_so, trang_thai, week_start)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bao_cao_tuan_program ON BAO_CAO_TUAN(ma_chuong_trinh, week_start)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS NHAN_XET_BAO_CAO_TUAN (
        ma_nhan_xet INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_bao_cao INTEGER NOT NULL UNIQUE,
        reviewed_by INTEGER NOT NULL,
        comment TEXT NOT NULL CHECK(length(comment) BETWEEN 1 AND 10000),
        reviewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_bao_cao) REFERENCES BAO_CAO_TUAN(ma_bao_cao) ON DELETE RESTRICT,
        FOREIGN KEY (reviewed_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nhan_xet_mentor ON NHAN_XET_BAO_CAO_TUAN(reviewed_by, reviewed_at)")

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
    CREATE TABLE IF NOT EXISTS HOP_DONG_THUC_TAP (
        ma_hop_dong INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_ho_so INTEGER NOT NULL,
        original_file_name TEXT NOT NULL,
        storage_key TEXT NOT NULL UNIQUE,
        mime_type TEXT NOT NULL,
        file_size INTEGER NOT NULL CHECK(file_size > 0),
        trang_thai TEXT NOT NULL DEFAULT 'PENDING_CONFIRMATION'
            CHECK(trang_thai IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'REJECTED')),
        uploaded_by INTEGER,
        confirmed_by INTEGER,
        confirmed_at DATETIME,
        rejected_by INTEGER,
        rejected_at DATETIME,
        rejection_reason TEXT,
        uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
        FOREIGN KEY (uploaded_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL,
        FOREIGN KEY (confirmed_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL,
        FOREIGN KEY (rejected_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
    )
    """)
    contract_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(HOP_DONG_THUC_TAP)")}
    for name, definition in (
        ("confirmed_by", "INTEGER"),
        ("confirmed_at", "DATETIME"),
        ("rejected_by", "INTEGER"),
        ("rejected_at", "DATETIME"),
        ("rejection_reason", "TEXT"),
    ):
        if name not in contract_columns:
            cursor.execute(f"ALTER TABLE HOP_DONG_THUC_TAP ADD COLUMN {name} {definition}")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS HOP_DONG_THUC_TAP_LICH_SU (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ma_hop_dong INTEGER NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('UPLOADED', 'CONFIRMED', 'REJECTED')),
            old_status TEXT,
            new_status TEXT NOT NULL,
            actor_id INTEGER,
            actor_name TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            reason TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ma_hop_dong, action),
            FOREIGN KEY (ma_hop_dong) REFERENCES HOP_DONG_THUC_TAP(ma_hop_dong) ON DELETE RESTRICT,
            FOREIGN KEY (actor_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_contract_history_timeline
        ON HOP_DONG_THUC_TAP_LICH_SU(ma_hop_dong, created_at, history_id)
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO HOP_DONG_THUC_TAP_LICH_SU
            (ma_hop_dong, action, old_status, new_status, actor_id, actor_name, actor_role, created_at)
        SELECT c.ma_hop_dong, 'UPLOADED', NULL, 'PENDING_CONFIRMATION', c.uploaded_by,
               COALESCE(u.ho_ten, 'Nhân sự'), COALESCE(u.vai_tro, 'HR'), c.uploaded_at
        FROM HOP_DONG_THUC_TAP c
        LEFT JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = c.uploaded_by
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_hop_dong_uploaded_at
        ON HOP_DONG_THUC_TAP(uploaded_at)
    """)

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
        max_retry INTEGER NOT NULL DEFAULT 4,
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

    outbox_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(EMAIL_OUTBOX)")}
    if "body_html" not in outbox_columns:
        cursor.execute("ALTER TABLE EMAIL_OUTBOX ADD COLUMN body_html TEXT")
    if "has_attachments" not in outbox_columns:
        cursor.execute("ALTER TABLE EMAIL_OUTBOX ADD COLUMN has_attachments INTEGER NOT NULL DEFAULT 0")
    if "dedup_hash" not in outbox_columns:
        cursor.execute("ALTER TABLE EMAIL_OUTBOX ADD COLUMN dedup_hash TEXT")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_email_dedup
        ON EMAIL_OUTBOX(recipient_email, dedup_hash, created_at)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS EMAIL_DEDUP_LOCKS (
        recipient_email TEXT NOT NULL,
        dedup_hash TEXT NOT NULL,
        expires_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_outbox_id INTEGER,
        PRIMARY KEY (recipient_email, dedup_hash)
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_dedup_expires ON EMAIL_DEDUP_LOCKS(expires_at);")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS EMAIL_ATTACHMENTS (
        id TEXT PRIMARY KEY,
        email_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        file_path TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        file_size INTEGER NOT NULL CHECK(file_size > 0 AND file_size <= 10485760),
        disposition TEXT NOT NULL DEFAULT 'attachment' CHECK(disposition IN ('attachment', 'inline')),
        content_id TEXT,
        checksum_sha256 TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (email_id) REFERENCES EMAIL_OUTBOX(id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_attachments_email_id ON EMAIL_ATTACHMENTS(email_id, disposition);")

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

    cursor.execute("SELECT COUNT(*) FROM CHUONG_TRINH_THUC_TAP")
    if not os.getenv("IMS_SQLITE_PATH") and cursor.fetchone()[0] == 0:
        cursor.executemany("""
            INSERT INTO CHUONG_TRINH_THUC_TAP
                (ma_ct, ten_ct, ma_phong_ban, ngay_bat_dau, ngay_ket_thuc, chi_tieu, mo_ta_cong_viec, yeu_cau, quyen_loi, trang_thai)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DangMo')
        """, [
            (
                "TTS-BE-2026",
                "Thực tập sinh Backend Developer (Python/FastAPI)",
                1,
                "2026-10-15",
                "2026-12-30",
                5,
                "Tham gia phát triển các dịch vụ backend, thiết kế RESTful API và tối ưu hóa truy vấn cơ sở dữ liệu MySQL. Trực tiếp tham gia dự án thực tế cùng các kỹ sư cao cấp.",
                "Sinh viên năm 3, 4 hoặc mới tốt nghiệp chuyên ngành CNTT/KTPM. Nắm vững lập trình Python, cơ bản về FastAPI/Django/Flask và cơ sở dữ liệu SQL.",
                "Trợ cấp thực tập hấp dẫn, được cấp máy tính làm việc, hướng dẫn 1-1 bởi Senior Mentor, cơ hội trở thành nhân viên chính thức sau kỳ thực tập."
            ),
            (
                "TTS-FE-2026",
                "Thực tập sinh Frontend Developer (React/Vite)",
                1,
                "2026-10-15",
                "2026-12-30",
                4,
                "Xây dựng giao diện ứng dụng web hiện đại, tối ưu trải nghiệm người dùng (UX/UI) và tương tác với các RESTful API.",
                "Có kiến thức vững về HTML5, CSS3, JavaScript/TypeScript. Đã từng thực hành với ReactJS, hiểu về state management và responsive web design.",
                "Được đào tạo bài bản quy trình Agile/Scrum, phụ cấp hàng tháng, môi trường làm việc trẻ trung năng động."
            ),
            (
                "TTS-AI-2026",
                "Thực tập sinh Trí tuệ Nhân tạo & Khoa học Dữ liệu (AI/Data)",
                3,
                "2026-11-01",
                "2026-12-31",
                3,
                "Nghiên cứu ứng dụng các mô hình Machine Learning, LLM và xử lý dữ liệu lớn phục vụ bài toán nội bộ doanh nghiệp.",
                "Nắm vững toán học/xác suất thống kê, thành thạo Python, pandas, scikit-learn hoặc PyTorch/TensorFlow.",
                "Làm việc với hạ tầng GPU hiện đại, tài trợ chi phí thi chứng chỉ quốc tế, cơ hội xuất bản báo cáo khoa học."
            ),
            (
                "TTS-SEC-2026",
                "Thực tập sinh An toàn Thông tin & An ninh mạng",
                2,
                "2026-10-20",
                "2026-12-15",
                3,
                "Tham gia đánh giá an toàn ứng dụng, dò quét lỗ hổng bảo mật web/hệ thống và hỗ trợ rà soát tuân thủ tiêu chuẩn an ninh thông tin.",
                "Có kiến thức về mạng máy tính, hệ điều hành Linux, hiểu biết về OWASP Top 10 và các công cụ pentest cơ bản.",
                "Hướng dẫn bởi chuyên gia bảo mật hàng đầu, trải nghiệm các kịch bản diễn tập phòng thủ thực chiến."
            )
        ])

    conn.commit()
    conn.close()
