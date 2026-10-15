"""Idempotent, synthetic US37 demo data for the isolated UAT launcher only."""
from __future__ import annotations

import os
from pathlib import Path
import secrets

from . import database
from .hrm_storage import ensure_hrm_sqlite_schema, hrm_schema_ready

DEMO_EMAIL = "us37.demo.candidate@example.test"
DEMO_PROGRAM_CODE = "US37-UAT-CANDIDATE"


def _require_isolated_uat_database() -> None:
    if database.DATABASE_BACKEND == "sqlite":
        db_path = Path(database.DB_FILE).resolve()
        if db_path.parent.name.casefold() != "ims-us37-uat":
            raise RuntimeError("US37 demo seeding requires the dedicated IMS-US37-UAT database directory.")
        return
    host = os.getenv("MYSQL_HOST", "").strip().lower()
    if (
        database.DATABASE_BACKEND != "mysql"
        or os.getenv("MYSQL_DATABASE", "").strip() != "internship_management_us37_uat"
        or host not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise RuntimeError("US37 demo seeding is limited to the local internship_management_us37_uat database.")


def seed_demo_candidate() -> int:
    _require_isolated_uat_database()
    database.init_db()
    db = database.get_db_connection()
    try:
        if database.DATABASE_BACKEND == "sqlite":
            ensure_hrm_sqlite_schema(db)
        elif not hrm_schema_ready(db):
            raise RuntimeError("US37 MySQL UAT migrations must be applied before demo seeding.")

        # The MySQL initializer creates schema and reference departments, but it
        # deliberately does not seed production demo accounts. Create local-only
        # UAT logins here so the isolated database can be exercised end to end.
        department = db.execute(
            "SELECT ma_phong_ban FROM PHONG_BAN ORDER BY ma_phong_ban LIMIT 1"
        ).fetchone()
        department_id = int(department["ma_phong_ban"]) if department else None
        for name, email, role, phone in (
            ("US37 UAT Admin", "admin@internship.vn", "Admin", "0900000001"),
            ("US37 UAT HR", "hr@internship.vn", "HR", "0900000002"),
        ):
            existing_login = db.execute(
                "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email=?", (email,)
            ).fetchone()
            if not existing_login:
                db.execute(
                    "INSERT INTO NGUOI_DUNG (ma_phong_ban,ho_ten,email,mat_khau,so_dien_thoai,vai_tro,trang_thai) VALUES (?,?,?,?,?,?, 'HoatDong')",
                    (department_id, name, email, database.hash_password("123456"), phone, role),
                )

        hr = db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro='HR' ORDER BY ma_nguoi_dung LIMIT 1").fetchone()
        if not hr:
            raise RuntimeError("The isolated UAT database has no seeded HR account.")

        intern = db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email=?", (DEMO_EMAIL,)).fetchone()
        if intern:
            user_id = int(intern["ma_nguoi_dung"])
        else:
            # The synthetic candidate is not intended to be a login account.
            # Store only a one-time random password hash, never a reusable secret.
            user_id = int(db.execute(
                "INSERT INTO NGUOI_DUNG (ho_ten,email,mat_khau,vai_tro,trang_thai) VALUES (?,?,?,'ThucTapSinh','HoatDong')",
                ("US37 Demo Candidate", DEMO_EMAIL, database.hash_password(secrets.token_urlsafe(48))),
            ).lastrowid)

        profile = db.execute("SELECT ma_ho_so FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung=?", (user_id,)).fetchone()
        if profile:
            profile_id = int(profile["ma_ho_so"])
            db.execute(
                "UPDATE HO_SO_THUC_TAP SET trang_thai_xet_duyet='DaDuyet', trang_thai_thuc_tap='HoanThanh' WHERE ma_ho_so=?",
                (profile_id,),
            )
        else:
            profile_id = int(db.execute(
                "INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung,trang_thai_xet_duyet,trang_thai_thuc_tap) VALUES (?,'DaDuyet','HoanThanh')",
                (user_id,),
            ).lastrowid)

        program = db.execute("SELECT ma_chuong_trinh FROM CHUONG_TRINH_THUC_TAP WHERE ma_ct=?", (DEMO_PROGRAM_CODE,)).fetchone()
        if program:
            program_id = int(program["ma_chuong_trinh"])
        else:
            program_id = int(db.execute(
                "INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct,ten_ct,chi_tieu,trang_thai,ngay_bat_dau,ngay_ket_thuc) VALUES (?,?,1,'DaDong','2026-01-05','2026-02-27')",
                (DEMO_PROGRAM_CODE, "US37 Synthetic completed internship"),
            ).lastrowid)

        application = db.execute(
            "SELECT ma_ung_tuyen FROM UNG_TUYEN_CHUONG_TRINH WHERE ma_chuong_trinh=? AND ma_ho_so=?",
            (program_id, profile_id),
        ).fetchone()
        if application:
            db.execute(
                "UPDATE UNG_TUYEN_CHUONG_TRINH SET trang_thai='DaDuyet', completion_status='HoanThanh', completion_updated_by=?, completion_updated_at='2026-02-28 10:00:00' WHERE ma_ung_tuyen=?",
                (int(hr["ma_nguoi_dung"]), int(application["ma_ung_tuyen"])),
            )
        else:
            db.execute(
                "INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh,ma_ho_so,trang_thai,completion_status,completion_updated_by,completion_updated_at) VALUES (?,?,'DaDuyet','HoanThanh',?,'2026-02-28 10:00:00')",
                (program_id, profile_id, int(hr["ma_nguoi_dung"])),
            )
        db.commit()
        return profile_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print(f"Prepared isolated synthetic US37 candidate profile #{seed_demo_candidate()}.")
