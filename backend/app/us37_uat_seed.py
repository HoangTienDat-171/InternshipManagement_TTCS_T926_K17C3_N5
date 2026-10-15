"""Idempotent, synthetic US37 demo data for the isolated UAT launcher only."""
from __future__ import annotations

from pathlib import Path

from . import database
from .hrm_storage import ensure_hrm_sqlite_schema

DEMO_EMAIL = "us37.demo.candidate@example.test"
DEMO_PROGRAM_CODE = "US37-UAT-CANDIDATE"


def seed_demo_candidate() -> int:
    if database.DATABASE_BACKEND != "sqlite":
        raise RuntimeError("US37 demo seeding is limited to SQLite UAT.")
    db_path = Path(database.DB_FILE).resolve()
    if db_path.parent.name.casefold() != "ims-us37-uat":
        raise RuntimeError("US37 demo seeding requires the dedicated IMS-US37-UAT database directory.")

    database.init_db()
    db = database.get_db_connection()
    try:
        ensure_hrm_sqlite_schema(db)
        hr = db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro='HR' ORDER BY ma_nguoi_dung LIMIT 1").fetchone()
        if not hr:
            raise RuntimeError("The isolated UAT database has no seeded HR account.")

        intern = db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email=?", (DEMO_EMAIL,)).fetchone()
        if intern:
            user_id = int(intern["ma_nguoi_dung"])
        else:
            user_id = int(db.execute(
                "INSERT INTO NGUOI_DUNG (ho_ten,email,mat_khau,vai_tro,trang_thai) VALUES (?,?,?,'ThucTapSinh','HoatDong')",
                ("US37 Demo Candidate", DEMO_EMAIL, "uat-demo-account-no-login"),
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
