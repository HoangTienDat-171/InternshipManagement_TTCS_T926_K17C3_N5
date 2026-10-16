"""Create only the two local IMS UAT login accounts in the clean test schema."""
from __future__ import annotations

import os

from . import database

EXPECTED_SCHEMA = "ims_us37_clean_uat"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
ACCOUNTS = (
    ("US37 UAT Admin", "admin@internship.vn", "Admin", "US37_CLEAN_ADMIN_PASSWORD"),
    ("US37 UAT HR", "hr@internship.vn", "HR", "US37_CLEAN_HR_PASSWORD"),
)
CLEAN_DEPARTMENTS = (
    ("Trung tâm Công nghệ Thông tin", "Phát triển phần mềm, giải pháp Web/App, AI và Cloud"),
    ("Khối Kỹ thuật Hạ tầng & An ninh mạng", "Vận hành hệ thống, DevOps và an toàn thông tin"),
    ("Phòng Dữ liệu & Trí tuệ nhân tạo (AI/Data)", "Phân tích dữ liệu và giải pháp trí tuệ nhân tạo"),
    ("Phòng Kiểm thử & Đảm bảo chất lượng (QA/QC)", "Kiểm thử phần mềm và quản lý chất lượng"),
)


def seed_clean_uat_accounts() -> None:
    if (
        database.DATABASE_BACKEND != "mysql"
        or os.getenv("MYSQL_DATABASE", "").strip() != EXPECTED_SCHEMA
        or os.getenv("MYSQL_HOST", "").strip().lower() not in LOCAL_HOSTS
    ):
        raise RuntimeError("Clean UAT account creation is restricted to the local ims_us37_clean_uat schema.")

    passwords = {}
    for _, email, _, env_name in ACCOUNTS:
        password = os.getenv(env_name, "")
        if len(password) < 24:
            raise RuntimeError(f"{env_name} must contain a locally generated UAT password of at least 24 characters.")
        passwords[email] = password

    database.init_db()
    connection = database.get_db_connection()
    try:
        for name, description in CLEAN_DEPARTMENTS:
            existing_department = connection.execute(
                "SELECT ma_phong_ban FROM PHONG_BAN WHERE LOWER(TRIM(ten_phong_ban)) = LOWER(TRIM(?))",
                (name,),
            ).fetchone()
            if not existing_department:
                connection.execute(
                    "INSERT INTO PHONG_BAN (ten_phong_ban, mo_ta) VALUES (?, ?)",
                    (name, description),
                )

        department = connection.execute(
            "SELECT ma_phong_ban FROM PHONG_BAN ORDER BY ma_phong_ban LIMIT 1"
        ).fetchone()
        department_id = int(department["ma_phong_ban"]) if department else None
        for name, email, role, _ in ACCOUNTS:
            current = connection.execute(
                "SELECT ma_nguoi_dung, vai_tro FROM NGUOI_DUNG WHERE email = ?", (email,)
            ).fetchone()
            if current:
                if current["vai_tro"] != role:
                    raise RuntimeError(f"Existing UAT account {email} has a different role; no account was modified.")
                continue
            connection.execute(
                "INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai) "
                "VALUES (?, ?, ?, ?, ?, 'HoatDong')",
                (department_id, name, email, database.hash_password(passwords[email]), role),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    seed_clean_uat_accounts()
    print("Clean UAT Admin and HR accounts are ready; no TTS or outbound demo record was created.")
