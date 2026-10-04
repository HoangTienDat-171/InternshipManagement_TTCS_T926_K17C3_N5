import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import database
from app.attendance_service import InternAttendanceService
from app.routes import attendance_routes
from app.schemas import InternAttendanceCheckIn, InternAttendanceCheckOut


def request_for(user=None):
    return SimpleNamespace(state=SimpleNamespace(current_user=user))


class InternAttendanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us21-")
        cls.db_path = Path(cls.temp_dir.name) / "us21.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()

        db = database.get_db_connection()
        admin = db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro='Admin' ORDER BY ma_nguoi_dung LIMIT 1").fetchone()
        mentor = db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro='Mentor' ORDER BY ma_nguoi_dung LIMIT 1").fetchone()
        if not admin or not mentor:
            raise RuntimeError("US21 test fixture requires seeded Admin and Mentor users.")
        cls.admin_id = admin["ma_nguoi_dung"]
        cls.mentor = dict(db.execute("SELECT ma_nguoi_dung, vai_tro FROM NGUOI_DUNG WHERE ma_nguoi_dung=?", (mentor["ma_nguoi_dung"],)).fetchone())

        program_cursor = db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, chi_tieu)
            VALUES ('US21-PROGRAM', 'US21 Attendance Program', 1)
        """)
        cls.program_id = program_cursor.lastrowid
        user_cursor = db.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES ('US21 Intern', 'us21-intern@example.test', 'test-only', 'ThucTapSinh', 'HoatDong')
        """)
        cls.user_id = user_cursor.lastrowid
        profile_cursor = db.execute("""
            INSERT INTO HO_SO_THUC_TAP
                (ma_nguoi_dung, trang_thai_xet_duyet, trang_thai_thuc_tap)
            VALUES (?, 'DaDuyet', 'DangThucTap')
        """, (cls.user_id,))
        cls.profile_id = profile_cursor.lastrowid
        db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH
                (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet)
            VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP)
        """, (cls.program_id, cls.profile_id))
        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()
        self.db.execute("DELETE FROM CHAM_CONG")
        self.db.execute("DELETE FROM CA_LAM_VIEC")
        self.db.commit()
        self.day = self.db.execute("SELECT CURRENT_DATE AS today").fetchone()["today"]
        self.day = str(self.day)[:10]
        self.intern = {"ma_nguoi_dung": self.user_id, "vai_tro": "ThucTapSinh"}
        self.service = InternAttendanceService(self.db)

    def tearDown(self):
        self.db.close()

    def add_shift(self, *, scope="PROGRAM", program_id=None, status="ACTIVE", starts_in=0, ends_in=None, name="Test shift"):
        if scope == "PROGRAM" and program_id is None:
            program_id = self.program_id
        from datetime import date

        today = date.fromisoformat(self.day)
        effective_from = (today + timedelta(days=starts_in)).isoformat()
        effective_to = (today + timedelta(days=ends_in)).isoformat() if ends_in is not None else None
        cursor = self.db.execute("""
            INSERT INTO CA_LAM_VIEC
                (name, start_time, end_time, scope_type, ma_chuong_trinh,
                 effective_from, effective_to, status, created_by)
            VALUES (?, '09:30:00', '12:30:00', ?, ?, ?, ?, ?, ?)
        """, (name, scope, program_id, effective_from, effective_to, status, self.admin_id))
        self.db.commit()
        return cursor.lastrowid

    def test_program_shift_overrides_global_and_inactive_program_shift_falls_back(self):
        global_id = self.add_shift(scope="GLOBAL", name="Global shift")
        program_id = self.add_shift(name="Program shift")
        record = self.service.check_in(self.user_id)
        self.assertEqual(record["shift"]["id"], program_id)

        self.db.execute("DELETE FROM CHAM_CONG")
        self.db.execute("UPDATE CA_LAM_VIEC SET status='INACTIVE' WHERE id=?", (program_id,))
        self.db.commit()
        fallback_record = self.service.check_in(self.user_id)
        self.assertEqual(fallback_record["shift"]["id"], global_id)

    def test_no_shift_inactive_and_out_of_range_shifts_block_check_in(self):
        for shift_options in (
            {"status": "INACTIVE"},
            {"starts_in": 1, "ends_in": 2},
        ):
            with self.subTest(shift_options=shift_options):
                self.db.execute("DELETE FROM CHAM_CONG")
                self.db.execute("DELETE FROM CA_LAM_VIEC")
                self.db.commit()
                self.add_shift(**shift_options)
                with self.assertRaises(HTTPException) as context:
                    self.service.check_in(self.user_id)
                self.assertEqual(context.exception.status_code, 409)
                self.assertEqual(context.exception.detail, "Không có ca làm việc áp dụng cho hôm nay.")
        self.db.execute("DELETE FROM CA_LAM_VIEC")
        self.db.commit()
        with self.assertRaises(HTTPException) as context:
            self.service.check_in(self.user_id)
        self.assertEqual(context.exception.detail, "Không có ca làm việc áp dụng cho hôm nay.")

    def test_multiple_applicable_shifts_fail_safe(self):
        self.add_shift(name="Candidate one")
        self.add_shift(name="Candidate two")
        with self.assertRaises(HTTPException) as context:
            self.service.check_in(self.user_id)
        self.assertEqual(context.exception.status_code, 409)
        self.assertIn("nhiều ca", context.exception.detail)
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS total FROM CHAM_CONG").fetchone()["total"], 0)

    def test_check_in_is_idempotent_and_database_enforces_business_unique_key(self):
        self.add_shift()
        first = self.service.check_in(self.user_id, "Ghi chú ban đầu")
        repeated = self.service.check_in(self.user_id, "Không được ghi đè")
        self.assertEqual(first["id"], repeated["id"])
        self.assertEqual(first["check_in_at"], repeated["check_in_at"])
        self.assertEqual(repeated["note"], "Ghi chú ban đầu")
        self.assertEqual(repeated["status"], "CHECKED_IN")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("""
                INSERT INTO CHAM_CONG
                    (ma_ho_so, ca_lam_viec_id, attendance_date, status)
                VALUES (?, ?, ?, 'CHECKED_IN')
            """, (self.profile_id, first["shift"]["id"], self.day))

    def test_concurrent_check_in_creates_only_one_row(self):
        self.add_shift()
        barrier = Barrier(2)

        def attempt():
            conn = database.get_db_connection()
            try:
                barrier.wait(timeout=3)
                return InternAttendanceService(conn).check_in(self.user_id)
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: attempt(), range(2)))
        self.assertEqual(results[0]["id"], results[1]["id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS total FROM CHAM_CONG").fetchone()["total"], 1)

    def test_check_out_requires_check_in_and_preserves_first_checkout(self):
        self.add_shift()
        with self.assertRaises(HTTPException) as context:
            self.service.check_out(self.user_id)
        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(context.exception.detail, "Bạn chưa Check-in cho ca làm hôm nay.")

        checked_in = self.service.check_in(self.user_id)
        completed = self.service.check_out(self.user_id)
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertIsNotNone(completed["check_out_at"])
        self.db.execute("UPDATE CHAM_CONG SET check_out_at='2001-01-01 01:02:03' WHERE id=?", (checked_in["id"],))
        self.db.commit()
        repeated = self.service.check_out(self.user_id)
        self.assertEqual(repeated["check_out_at"], "2001-01-01 01:02:03")

    def test_concurrent_check_out_keeps_one_transition_and_timestamp(self):
        self.add_shift()
        self.service.check_in(self.user_id)
        barrier = Barrier(2)

        def attempt():
            conn = database.get_db_connection()
            try:
                barrier.wait(timeout=3)
                return InternAttendanceService(conn).check_out(self.user_id)
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: attempt(), range(2)))
        self.assertEqual(results[0]["check_out_at"], results[1]["check_out_at"])
        self.assertEqual(results[0]["status"], "COMPLETED")

    def test_server_clock_and_request_schema_reject_client_identity_shift_and_time(self):
        self.add_shift()
        record = attendance_routes.check_in_attendance(
            InternAttendanceCheckIn(), request_for(self.intern), db=self.db,
        )
        self.assertEqual(record["attendance_date"], self.day)
        self.assertEqual(
            record["check_in_at"],
            self.db.execute("SELECT check_in_at FROM CHAM_CONG WHERE id=?", (record["id"],)).fetchone()["check_in_at"],
        )
        for payload in (
            {"profile_id": self.profile_id + 1},
            {"student_id": self.user_id + 1},
            {"shift_id": record["shift"]["id"] + 1},
            {"attendance_date": "2001-01-01"},
            {"check_in_at": "2001-01-01 01:02:03"},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                InternAttendanceCheckIn.model_validate(payload)
        with self.assertRaises(ValidationError):
            InternAttendanceCheckOut.model_validate({"check_out_at": "2001-01-01 01:02:03"})

    def test_role_and_self_history_scope_are_enforced(self):
        self.add_shift(scope="GLOBAL")
        with self.assertRaises(HTTPException) as anonymous:
            attendance_routes.get_today_attendance(request_for(), db=self.db)
        self.assertEqual(anonymous.exception.status_code, 401)
        with self.assertRaises(HTTPException) as mentor:
            attendance_routes.check_in_attendance(
                InternAttendanceCheckIn(), request_for(self.mentor), db=self.db,
            )
        self.assertEqual(mentor.exception.status_code, 403)

        other_user_cursor = self.db.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES ('Other US21 Intern', 'us21-other@example.test', 'test-only', 'ThucTapSinh', 'HoatDong')
        """)
        other_user_id = other_user_cursor.lastrowid
        other_profile_cursor = self.db.execute("""
            INSERT INTO HO_SO_THUC_TAP
                (ma_nguoi_dung, trang_thai_xet_duyet, trang_thai_thuc_tap)
            VALUES (?, 'DaDuyet', 'DangThucTap')
        """, (other_user_id,))
        other_profile_id = other_profile_cursor.lastrowid
        self.db.commit()
        self.db.execute("""
            INSERT INTO CHAM_CONG
                (ma_ho_so, ca_lam_viec_id, attendance_date, status)
            VALUES (?, (SELECT id FROM CA_LAM_VIEC LIMIT 1), ?, 'CHECKED_IN')
        """, (other_profile_id, self.day))
        self.db.commit()
        history = attendance_routes.get_attendance_history(
            request_for(self.intern), month=None, page=1, page_size=20, db=self.db,
        )
        self.assertEqual(history["total_items"], 0)

    def test_today_and_history_routes_expose_server_date_and_paginated_self_records(self):
        self.add_shift()
        attendance_routes.check_in_attendance(InternAttendanceCheckIn(), request_for(self.intern), db=self.db)
        today = attendance_routes.get_today_attendance(request_for(self.intern), db=self.db)
        history = attendance_routes.get_attendance_history(
            request_for(self.intern), month=self.day[:7], page=1, page_size=10, db=self.db,
        )
        self.assertEqual(today["date"], self.day)
        self.assertFalse(today["can_check_in"])
        self.assertTrue(today["can_check_out"])
        self.assertEqual(history["total_items"], 1)
        self.assertEqual(history["items"][0]["attendance_date"], self.day)


if __name__ == "__main__":
    unittest.main()
