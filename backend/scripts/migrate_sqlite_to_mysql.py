"""Merge the existing SQLite app records into MySQL without replacing rows.

Accounts are matched by email and relationships are rebuilt from those stable
identities rather than reusing SQLite auto-increment IDs.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from shutil import copy2
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import BACKEND_DIR, _connect_mysql


PROJECT_DB = BACKEND_DIR / "app" / "internship.db"
PREVIEW_DB = Path(r"C:\Users\dat17\AppData\Local\Temp\ims-ui-preview-20260927-01\backend\app\internship.db")


def table_exists(source: sqlite3.Connection, table: str) -> bool:
    return source.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def columns(source: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in source.execute(f"PRAGMA table_info({table})")}


def source_rows(source: sqlite3.Connection, table: str):
    return source.execute(f"SELECT * FROM {table}").fetchall()


def get_mysql_id(mysql, table: str, key: str, value):
    row = mysql.execute(f"SELECT {key} FROM {table} WHERE {key}=%s LIMIT 1", (value,)).fetchone()
    return row[key] if row else None


def is_known_mojibake(value: str) -> bool:
    return any(character in value for character in "─║╗╔╚╝░▒▓╞╟╠╣╦╩╬")


def merge_source(mysql, db_path: Path, counts: dict[str, int], warnings: list[str]):
    if not db_path.exists():
        warnings.append(f"Nguồn SQLite không tồn tại, bỏ qua: {db_path}")
        return
    source = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    source.execute("PRAGMA query_only=ON")
    try:
        department_ids = {}
        for row in source_rows(source, "PHONG_BAN") if table_exists(source, "PHONG_BAN") else []:
            target = mysql.execute(
                "SELECT ma_phong_ban FROM PHONG_BAN WHERE ten_phong_ban=%s LIMIT 1",
                (row["ten_phong_ban"],),
            ).fetchone()
            if target:
                target_id = target["ma_phong_ban"]
            else:
                cursor = mysql.execute(
                    "INSERT INTO PHONG_BAN (ten_phong_ban, mo_ta) VALUES (%s, %s)",
                    (row["ten_phong_ban"], row["mo_ta"]),
                )
                target_id = cursor.lastrowid
                counts["departments_added"] += 1
            department_ids[row["ma_phong_ban"]] = target_id

        university_ids = {}
        for row in source_rows(source, "TRUONG_DAI_HOC") if table_exists(source, "TRUONG_DAI_HOC") else []:
            target = mysql.execute(
                "SELECT ma_truong FROM TRUONG_DAI_HOC WHERE ten_truong=%s LIMIT 1",
                (row["ten_truong"],),
            ).fetchone()
            legacy = mysql.execute(
                "SELECT ma_truong,ten_truong FROM TRUONG_DAI_HOC WHERE ma_truong=%s LIMIT 1",
                (row["ma_truong"],),
            ).fetchone()
            if legacy and is_known_mojibake(legacy["ten_truong"]):
                target_id = legacy["ma_truong"]
                if target and target["ma_truong"] != target_id:
                    mysql.execute(
                        "UPDATE HO_SO_THUC_TAP SET ma_truong=%s WHERE ma_truong=%s",
                        (target_id, target["ma_truong"]),
                    )
                    mysql.execute("DELETE FROM TRUONG_DAI_HOC WHERE ma_truong=%s", (target["ma_truong"],))
                mysql.execute("""
                    UPDATE TRUONG_DAI_HOC SET ten_truong=%s, dia_chi=%s,
                        nguoi_lien_he=%s, email_lien_he=%s WHERE ma_truong=%s
                """, (row["ten_truong"], row["dia_chi"], row["nguoi_lien_he"], row["email_lien_he"], target_id))
                target = {"ma_truong": target_id}
            if target:
                target_id = target["ma_truong"]
            else:
                cursor = mysql.execute("""
                    INSERT INTO TRUONG_DAI_HOC (ten_truong, dia_chi, nguoi_lien_he, email_lien_he)
                    VALUES (%s, %s, %s, %s)
                """, (row["ten_truong"], row["dia_chi"], row["nguoi_lien_he"], row["email_lien_he"]))
                target_id = cursor.lastrowid
                counts["universities_added"] += 1
            university_ids[row["ma_truong"]] = target_id

        user_ids = {}
        for row in source_rows(source, "NGUOI_DUNG"):
            email = row["email"].strip().lower()
            dept_id = department_ids.get(row["ma_phong_ban"])
            existing = mysql.execute(
                "SELECT ma_nguoi_dung, mat_khau FROM NGUOI_DUNG WHERE LOWER(email)=%s LIMIT 1",
                (email,),
            ).fetchone()
            if existing:
                target_id = existing["ma_nguoi_dung"]
                phone = row["so_dien_thoai"]
                if phone:
                    collision = mysql.execute(
                        "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE so_dien_thoai=%s AND ma_nguoi_dung<>%s LIMIT 1",
                        (phone, target_id),
                    ).fetchone()
                    if collision:
                        warnings.append(f"Không ghi đè số điện thoại bị trùng của tài khoản {email}.")
                        phone = None
                mysql.execute("""
                    UPDATE NGUOI_DUNG
                    SET ma_phong_ban=%s, ho_ten=%s, so_dien_thoai=COALESCE(%s, so_dien_thoai),
                        vai_tro=%s, trang_thai=%s
                    WHERE ma_nguoi_dung=%s
                """, (dept_id, row["ho_ten"], phone, row["vai_tro"], row["trang_thai"], target_id))
                counts["users_matched"] += 1
            else:
                phone = row["so_dien_thoai"]
                if phone and mysql.execute("SELECT 1 FROM NGUOI_DUNG WHERE so_dien_thoai=%s LIMIT 1", (phone,)).fetchone():
                    warnings.append(f"Tài khoản {email} được nhập không kèm số điện thoại do số đã thuộc tài khoản khác.")
                    phone = None
                cursor = mysql.execute("""
                    INSERT INTO NGUOI_DUNG
                        (ma_phong_ban, ho_ten, email, mat_khau, so_dien_thoai, vai_tro, trang_thai)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (dept_id, row["ho_ten"], email, row["mat_khau"], phone, row["vai_tro"], row["trang_thai"]))
                target_id = cursor.lastrowid
                counts["users_added"] += 1
            user_ids[row["ma_nguoi_dung"]] = target_id

        profile_ids = {}
        for row in source_rows(source, "HO_SO_THUC_TAP") if table_exists(source, "HO_SO_THUC_TAP") else []:
            owner = source.execute(
                "SELECT email, vai_tro FROM NGUOI_DUNG WHERE ma_nguoi_dung=?", (row["ma_nguoi_dung"],)
            ).fetchone()
            if not owner:
                warnings.append(f"Bỏ hồ sơ TTS #{row['ma_ho_so']}: tài khoản nguồn #{row['ma_nguoi_dung']} không tồn tại.")
                continue
            if owner["vai_tro"] != "ThucTapSinh":
                warnings.append(f"Bỏ hồ sơ #{row['ma_ho_so']} gắn với tài khoản không phải TTS ({owner['email']}).")
                continue
            target_user_id = user_ids[row["ma_nguoi_dung"]]
            target_school_id = university_ids.get(row["ma_truong"])
            existing = mysql.execute(
                "SELECT ma_ho_so FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung=%s LIMIT 1", (target_user_id,)
            ).fetchone()
            if existing:
                target_profile_id = existing["ma_ho_so"]
                mysql.execute("""
                    UPDATE HO_SO_THUC_TAP SET ma_truong=%s, chuyen_nganh=%s,
                        trang_thai_xet_duyet=%s, trang_thai_thuc_tap=%s WHERE ma_ho_so=%s
                """, (target_school_id, row["chuyen_nganh"], row["trang_thai_xet_duyet"], row["trang_thai_thuc_tap"], target_profile_id))
                counts["profiles_matched"] += 1
            else:
                cursor = mysql.execute("""
                    INSERT INTO HO_SO_THUC_TAP
                        (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
                    VALUES (%s, %s, %s, %s, %s)
                """, (target_user_id, target_school_id, row["chuyen_nganh"], row["trang_thai_xet_duyet"], row["trang_thai_thuc_tap"]))
                target_profile_id = cursor.lastrowid
                counts["profiles_added"] += 1
            profile_ids[row["ma_ho_so"]] = target_profile_id

        if table_exists(source, "MENTOR_PROFILE"):
            for row in source_rows(source, "MENTOR_PROFILE"):
                source_user = source.execute(
                    "SELECT email, vai_tro FROM NGUOI_DUNG WHERE ma_nguoi_dung=?", (row["ma_nguoi_dung"],)
                ).fetchone()
                if not source_user or source_user["vai_tro"] != "Mentor":
                    warnings.append(f"Bỏ thông tin Mentor #{row['ma_nguoi_dung']}: tài khoản không hợp lệ.")
                    continue
                target_user_id = user_ids.get(row["ma_nguoi_dung"])
                if target_user_id is None:
                    target_user_id = get_mysql_id(mysql, "NGUOI_DUNG", "email", source_user["email"])
                if target_user_id is None:
                    continue
                mysql.execute("""
                    INSERT INTO MENTOR_PROFILE (ma_nguoi_dung, chuyen_mon, kinh_nghiem, so_tts_toi_da)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        chuyen_mon=COALESCE(VALUES(chuyen_mon), chuyen_mon),
                        kinh_nghiem=COALESCE(VALUES(kinh_nghiem), kinh_nghiem),
                        so_tts_toi_da=COALESCE(VALUES(so_tts_toi_da), so_tts_toi_da)
                """, (target_user_id, row["chuyen_mon"], row["kinh_nghiem"], row["so_tts_toi_da"]))
                counts["mentor_profiles_synced"] += 1

        mysql.execute("""
            INSERT IGNORE INTO MENTOR_PROFILE (ma_nguoi_dung, so_tts_toi_da)
            SELECT ma_nguoi_dung, 3 FROM NGUOI_DUNG WHERE vai_tro='Mentor'
        """)

        program_ids = {}
        if table_exists(source, "CHUONG_TRINH_THUC_TAP"):
            for row in source_rows(source, "CHUONG_TRINH_THUC_TAP"):
                source_dept = source.execute(
                    "SELECT ten_phong_ban FROM PHONG_BAN WHERE ma_phong_ban=?", (row["ma_phong_ban"],)
                ).fetchone() if row["ma_phong_ban"] else None
                target_dept = mysql.execute(
                    "SELECT ma_phong_ban FROM PHONG_BAN WHERE ten_phong_ban=%s LIMIT 1",
                    (source_dept["ten_phong_ban"],),
                ).fetchone() if source_dept else None
                dept_id = target_dept["ma_phong_ban"] if target_dept else None
                cursor = mysql.execute("""
                    INSERT INTO CHUONG_TRINH_THUC_TAP
                        (ma_ct, ten_ct, ma_phong_ban, ngay_bat_dau, ngay_ket_thuc, chi_tieu,
                         mo_ta_cong_viec, yeu_cau, quyen_loi, trang_thai, ngay_tao)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        ten_ct=VALUES(ten_ct), ma_phong_ban=VALUES(ma_phong_ban),
                        ngay_bat_dau=VALUES(ngay_bat_dau), ngay_ket_thuc=VALUES(ngay_ket_thuc),
                        chi_tieu=VALUES(chi_tieu), mo_ta_cong_viec=VALUES(mo_ta_cong_viec),
                        yeu_cau=VALUES(yeu_cau), quyen_loi=VALUES(quyen_loi), trang_thai=VALUES(trang_thai)
                """, (row["ma_ct"], row["ten_ct"], dept_id, row["ngay_bat_dau"], row["ngay_ket_thuc"],
                      row["chi_tieu"], row["mo_ta_cong_viec"], row["yeu_cau"], row["quyen_loi"], row["trang_thai"], row["ngay_tao"]))
                program = mysql.execute(
                    "SELECT ma_chuong_trinh FROM CHUONG_TRINH_THUC_TAP WHERE ma_ct=%s", (row["ma_ct"],)
                ).fetchone()
                program_ids[row["ma_chuong_trinh"]] = program["ma_chuong_trinh"]
                counts["programs_synced"] += 1

        if table_exists(source, "UNG_TUYEN_CHUONG_TRINH"):
            for row in source_rows(source, "UNG_TUYEN_CHUONG_TRINH"):
                program_id = program_ids.get(row["ma_chuong_trinh"])
                profile_id = profile_ids.get(row["ma_ho_so"])
                if profile_id is None and table_exists(source, "HO_SO_THUC_TAP"):
                    source_profile = source.execute(
                        "SELECT ma_nguoi_dung FROM HO_SO_THUC_TAP WHERE ma_ho_so=?", (row["ma_ho_so"],)
                    ).fetchone()
                    source_account = source.execute(
                        "SELECT email FROM NGUOI_DUNG WHERE ma_nguoi_dung=?",
                        (source_profile["ma_nguoi_dung"],),
                    ).fetchone() if source_profile else None
                    target_user = mysql.execute(
                        "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email=%s",
                        (source_account["email"],),
                    ).fetchone() if source_account else None
                    target_profile = mysql.execute(
                        "SELECT ma_ho_so FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung=%s",
                        (target_user["ma_nguoi_dung"],),
                    ).fetchone() if target_user else None
                    profile_id = target_profile["ma_ho_so"] if target_profile else None
                reviewer_email = None
                if row["nguoi_xet_duyet"]:
                    reviewer = source.execute(
                        "SELECT email FROM NGUOI_DUNG WHERE ma_nguoi_dung=?", (row["nguoi_xet_duyet"],)
                    ).fetchone()
                    reviewer_email = reviewer["email"] if reviewer else None
                reviewer_id = mysql.execute(
                    "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email=%s", (reviewer_email,)
                ).fetchone() if reviewer_email else None
                if program_id is None or profile_id is None:
                    warnings.append(f"Bỏ đơn ứng tuyển #{row['ma_ung_tuyen']}: thiếu chương trình hoặc hồ sơ đích.")
                    continue
                mysql.execute("""
                    INSERT INTO UNG_TUYEN_CHUONG_TRINH
                        (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_ung_tuyen, ngay_xet_duyet, nguoi_xet_duyet)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE trang_thai=VALUES(trang_thai),
                        ngay_ung_tuyen=VALUES(ngay_ung_tuyen), ngay_xet_duyet=VALUES(ngay_xet_duyet),
                        nguoi_xet_duyet=VALUES(nguoi_xet_duyet)
                """, (program_id, profile_id, row["trang_thai"], row["ngay_ung_tuyen"], row["ngay_xet_duyet"],
                      reviewer_id["ma_nguoi_dung"] if reviewer_id else None))
                counts["applications_synced"] += 1

        if table_exists(source, "TAI_LIEU_HO_SO"):
            document_columns = columns(source, "TAI_LIEU_HO_SO")
            upload_root = db_path.parent / "uploads"
            target_upload_root = BACKEND_DIR / "app" / "uploads" / "documents"
            target_upload_root.mkdir(parents=True, exist_ok=True)
            for row in source_rows(source, "TAI_LIEU_HO_SO"):
                target_profile_id = profile_ids.get(row["ma_ho_so"])
                if target_profile_id is None:
                    warnings.append(f"Bỏ tài liệu #{row['ma_tai_lieu']}: không tìm thấy hồ sơ TTS đích.")
                    continue
                relative_path = row["duong_dan_file"].replace("\\", "/")
                source_file = (upload_root / relative_path).resolve()
                try:
                    source_file.relative_to(upload_root.resolve())
                except ValueError:
                    warnings.append(f"Bỏ tài liệu #{row['ma_tai_lieu']}: đường dẫn tệp nằm ngoài thư mục upload.")
                    continue
                if not source_file.is_file():
                    warnings.append(f"Bỏ tài liệu #{row['ma_tai_lieu']}: không còn tệp gốc để sao chép.")
                    continue
                stored_name = source_file.name
                target_file = target_upload_root / stored_name
                if target_file.exists():
                    if target_file.stat().st_size != source_file.stat().st_size:
                        warnings.append(f"Bỏ tài liệu #{row['ma_tai_lieu']}: trùng tên tệp nhưng nội dung khác.")
                        continue
                else:
                    copy2(source_file, target_file)
                target_path = f"documents/{stored_name}"
                filename = row["ten_file"] if "ten_file" in document_columns else stored_name
                size = row["kich_thuoc"] if "kich_thuoc" in document_columns else source_file.stat().st_size
                duplicate = mysql.execute("""
                    SELECT ma_tai_lieu FROM TAI_LIEU_HO_SO
                    WHERE ma_ho_so=%s AND loai_tai_lieu=%s AND ten_file=%s AND ngay_tai_len=%s LIMIT 1
                """, (target_profile_id, row["loai_tai_lieu"], filename, row["ngay_tai_len"])).fetchone()
                if not duplicate:
                    mysql.execute("""
                        INSERT INTO TAI_LIEU_HO_SO
                            (ma_ho_so, loai_tai_lieu, duong_dan_file, ten_file, kich_thuoc,
                             trang_thai_duyet, ngay_tai_len)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """, (target_profile_id, row["loai_tai_lieu"], target_path, filename, size,
                          row["trang_thai_duyet"], row["ngay_tai_len"]))
                    counts["documents_synced"] += 1

        if table_exists(source, "PHAN_CONG_MENTOR_TTS"):
            for row in source_rows(source, "PHAN_CONG_MENTOR_TTS"):
                source_mentor = source.execute(
                    "SELECT email FROM NGUOI_DUNG WHERE ma_nguoi_dung=?", (row["ma_nguoi_dung_mentor"],)
                ).fetchone()
                source_intern = source.execute(
                    "SELECT ma_nguoi_dung FROM HO_SO_THUC_TAP WHERE ma_ho_so=?", (row["ma_ho_so"],)
                ).fetchone()
                mentor = mysql.execute(
                    "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email=%s",
                    (source_mentor["email"],),
                ).fetchone() if source_mentor else None
                intern = mysql.execute(
                    "SELECT ma_ho_so FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung=%s",
                    (user_ids.get(source_intern["ma_nguoi_dung"]),),
                ).fetchone() if source_intern and user_ids.get(source_intern["ma_nguoi_dung"]) else None
                source_actor = source.execute(
                    "SELECT email FROM NGUOI_DUNG WHERE ma_nguoi_dung=?", (row["ma_nguoi_phan_cong"],)
                ).fetchone() if row["ma_nguoi_phan_cong"] else None
                actor = mysql.execute(
                    "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email=%s",
                    (source_actor["email"],),
                ).fetchone() if source_actor else None
                if mentor and intern:
                    mysql.execute("""
                        INSERT INTO PHAN_CONG_MENTOR_TTS
                            (ma_nguoi_dung_mentor,ma_ho_so,ma_nguoi_phan_cong,ngay_phan_cong)
                        VALUES (%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE ma_nguoi_dung_mentor=VALUES(ma_nguoi_dung_mentor),
                            ma_nguoi_phan_cong=VALUES(ma_nguoi_phan_cong), ngay_phan_cong=VALUES(ngay_phan_cong)
                    """, (mentor["ma_nguoi_dung"], intern["ma_ho_so"], actor["ma_nguoi_dung"] if actor else None,
                          row["ngay_phan_cong"]))
                    counts["assignments_synced"] += 1
                else:
                    warnings.append(f"Bỏ phân công #{row['ma_phan_cong']}: thiếu Mentor hoặc hồ sơ TTS đích.")

        if table_exists(source, "ACTIVE_SESSIONS"):
            for row in source_rows(source, "ACTIVE_SESSIONS"):
                account = source.execute(
                    "SELECT email FROM NGUOI_DUNG WHERE ma_nguoi_dung=?", (row["ma_nguoi_dung"],)
                ).fetchone()
                target_user = mysql.execute(
                    "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email=%s", (account["email"],)
                ).fetchone() if account else None
                if target_user:
                    mysql.execute("""
                        INSERT INTO ACTIVE_SESSIONS (ma_nguoi_dung, token_hash, session_id)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE token_hash=VALUES(token_hash), session_id=VALUES(session_id)
                    """, (target_user["ma_nguoi_dung"], row["token_hash"], row["session_id"]))
                    counts["sessions_synced"] += 1

        if table_exists(source, "THONG_BAO"):
            for row in source_rows(source, "THONG_BAO"):
                account = source.execute(
                    "SELECT email FROM NGUOI_DUNG WHERE ma_nguoi_dung=?", (row["ma_nguoi_dung"],)
                ).fetchone()
                target_user = mysql.execute(
                    "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email=%s", (account["email"],)
                ).fetchone() if account else None
                if not target_user:
                    continue
                duplicate = mysql.execute("""
                    SELECT ma_thong_bao FROM THONG_BAO
                    WHERE ma_nguoi_dung=%s AND tieu_de=%s AND noi_dung <=> %s AND thoi_gian_gui=%s LIMIT 1
                """, (target_user["ma_nguoi_dung"], row["tieu_de"], row["noi_dung"], row["thoi_gian_gui"])).fetchone()
                if not duplicate:
                    mysql.execute("""
                        INSERT INTO THONG_BAO (ma_nguoi_dung,tieu_de,noi_dung,kenh,da_doc,thoi_gian_gui)
                        VALUES (%s,%s,%s,%s,%s,%s)
                    """, (target_user["ma_nguoi_dung"], row["tieu_de"], row["noi_dung"], row["kenh"], row["da_doc"], row["thoi_gian_gui"]))
                    counts["notifications_added"] += 1
    finally:
        source.close()


def main():
    counts = {key: 0 for key in (
        "departments_added", "universities_added", "users_added", "users_matched",
        "profiles_added", "profiles_matched", "mentor_profiles_synced", "programs_synced",
        "applications_synced", "assignments_synced", "documents_synced", "sessions_synced", "notifications_added",
    )}
    warnings: list[str] = []
    mysql = _connect_mysql()
    try:
        mysql._connection.begin()
        merge_source(mysql, PROJECT_DB, counts, warnings)
        merge_source(mysql, PREVIEW_DB, counts, warnings)
        mysql._connection.commit()
    except Exception:
        mysql._connection.rollback()
        raise
    finally:
        mysql.close()
    print("SQLite -> MySQL merge completed")
    for key, value in counts.items():
        print(f"{key}: {value}")
    for warning in warnings:
        print(f"REVIEW: {warning}")


if __name__ == "__main__":
    main()
