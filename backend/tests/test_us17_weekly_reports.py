"""US17 weekly-report authorization, concurrency, submission and attachment regressions."""
import asyncio
import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from app import database
from app.routes import weekly_report_routes
from app.schemas import WeeklyReportCreate, WeeklyReportUpdate
from app.weekly_report_service import WeeklyReportService


def request_for(user):
    return SimpleNamespace(state=SimpleNamespace(current_user=user))


class WeeklyReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us17-", ignore_cleanup_errors=True)
        cls.temp_path = Path(cls.temp_dir.name)
        cls.db_path = cls.temp_path / "us17.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.storage_patch = patch.object(weekly_report_routes, "REPORT_STORAGE_ROOT", cls.temp_path / "uploads")
        cls.backend_patch.start()
        cls.path_patch.start()
        cls.storage_patch.start()
        database.init_db()

        db = database.get_db_connection()
        rows = db.execute("""
            SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten
            FROM HO_SO_THUC_TAP h
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            WHERE u.email IN ('tuan.lm@internship.vn', 'minh.khoi.nguyen@internship.vn')
            ORDER BY u.email
        """).fetchall()
        if len(rows) != 2:
            raise RuntimeError("US17 fixtures require two seeded intern profiles.")
        cls.intern_a = {**dict(rows[0]), "vai_tro": "ThucTapSinh"}
        cls.intern_b = {**dict(rows[1]), "vai_tro": "ThucTapSinh"}
        program = db.execute("SELECT ma_chuong_trinh FROM CHUONG_TRINH_THUC_TAP ORDER BY ma_chuong_trinh LIMIT 1").fetchone()
        cls.program_id = program["ma_chuong_trinh"]
        for intern in (cls.intern_a, cls.intern_b):
            db.execute("""
                INSERT OR IGNORE INTO UNG_TUYEN_CHUONG_TRINH
                    (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet)
                VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP)
            """, (cls.program_id, intern["ma_ho_so"]))
            db.execute("""
                UPDATE UNG_TUYEN_CHUONG_TRINH SET trang_thai='DaDuyet', ngay_xet_duyet=CURRENT_TIMESTAMP
                WHERE ma_chuong_trinh=? AND ma_ho_so=?
            """, (cls.program_id, intern["ma_ho_so"]))
        mentor = db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro='Mentor' ORDER BY ma_nguoi_dung LIMIT 1").fetchone()
        db.execute("DELETE FROM PHAN_CONG_MENTOR_TTS WHERE ma_ho_so = ?", (cls.intern_a["ma_ho_so"],))
        db.execute("INSERT INTO PHAN_CONG_MENTOR_TTS (ma_nguoi_dung_mentor, ma_ho_so) VALUES (?, ?)", (mentor["ma_nguoi_dung"], cls.intern_a["ma_ho_so"]))
        cls.mentor_id = mentor["ma_nguoi_dung"]
        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        cls.storage_patch.stop()
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()
        self.db.execute("DELETE FROM BAO_CAO_TUAN")
        self.db.execute("DELETE FROM THONG_BAO WHERE loai = 'WEEKLY_REPORT_SUBMITTED'")
        self.db.commit()
        self.service = WeeklyReportService(self.db)

    def tearDown(self):
        self.db.close()

    def data(self, week="2026-10-05", **changes):
        values = {
            "program_id": self.program_id,
            "week_start": week,
            "work_content": "Hoàn thiện API báo cáo tuần",
            "results": "Đã hoàn thành và kiểm thử",
            "difficulties": "Không có",
        }
        values.update(changes)
        return WeeklyReportCreate(**values)

    def assert_http_error(self, code, callback):
        with self.assertRaises(HTTPException) as context:
            callback()
        self.assertEqual(context.exception.status_code, code)

    def test_create_update_submit_lock_and_notification(self):
        report = self.service.create(self.intern_a, self.data())
        self.assertEqual(report["status"], "DRAFT")
        self.assertEqual(str(report["week_end"]), "2026-10-11")
        updated = self.service.update(report["id"], self.intern_a, WeeklyReportUpdate(results="Kết quả mới"))
        self.assertEqual(updated["results"], "Kết quả mới")

        submitted = self.service.submit(report["id"], self.intern_a)
        self.assertEqual(submitted["status"], "SUBMITTED")
        self.assertIsNotNone(submitted["submitted_at"])
        notification = self.db.execute("""
            SELECT * FROM THONG_BAO WHERE loai='WEEKLY_REPORT_SUBMITTED' AND ma_nguoi_dung=?
        """, (self.mentor_id,)).fetchone()
        self.assertIsNotNone(notification)
        self.assertEqual(str(notification["reference_id"]), str(report["id"]))

        self.assert_http_error(409, lambda: self.service.update(
            report["id"], self.intern_a, WeeklyReportUpdate(results="Ghi đè")))
        self.assert_http_error(409, lambda: self.service.submit(report["id"], self.intern_a))
        count = self.db.execute("SELECT COUNT(*) FROM THONG_BAO WHERE loai='WEEKLY_REPORT_SUBMITTED'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_owner_idor_and_mass_assignment_are_blocked(self):
        own = self.service.create(self.intern_a, self.data())
        self.assert_http_error(403, lambda: self.service.get(own["id"], self.intern_b["ma_nguoi_dung"]))
        self.assert_http_error(403, lambda: self.service.update(
            own["id"], self.intern_b, WeeklyReportUpdate(results="IDOR")))
        self.assert_http_error(403, lambda: self.service.submit(own["id"], self.intern_b))
        with self.assertRaises(ValidationError):
            WeeklyReportUpdate(status="SUBMITTED", submitted_at="2026-10-05", internship_profile_id=999)

    def test_duplicate_and_concurrent_create_leave_one_report(self):
        self.service.create(self.intern_a, self.data())
        self.assert_http_error(409, lambda: self.service.create(self.intern_a, self.data()))
        self.db.execute("DELETE FROM BAO_CAO_TUAN")
        self.db.commit()

        def create_once():
            connection = database.get_db_connection()
            try:
                return WeeklyReportService(connection).create(self.intern_a, self.data())["id"]
            except HTTPException as error:
                return error.status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create_once(), range(2)))
        self.assertEqual(sum(value == 409 for value in results), 1)
        count = self.db.execute("SELECT COUNT(*) FROM BAO_CAO_TUAN").fetchone()[0]
        self.assertEqual(count, 1)

    def test_attachment_valid_owner_download_and_traversal(self):
        report = self.service.create(self.intern_a, self.data())
        upload = UploadFile(filename="bao-cao.pdf", file=io.BytesIO(b"%PDF-1.4\nweekly report\n%%EOF\n"))
        saved = asyncio.run(weekly_report_routes.upload_weekly_report_attachment(
            report["id"], request_for(self.intern_a), upload, self.db))
        self.assertTrue(saved["has_attachment"])
        response = weekly_report_routes.download_weekly_report_attachment(
            report["id"], request_for(self.intern_a), self.db)
        self.assertTrue(Path(response.path).is_file())
        self.assert_http_error(403, lambda: weekly_report_routes.download_weekly_report_attachment(
            report["id"], request_for(self.intern_b), self.db))
        self.assert_http_error(404, lambda: weekly_report_routes._attachment_path("../../test.pdf"))

        bad = UploadFile(filename="..\\..\\test.pdf", file=io.BytesIO(b"%PDF-1.4\n%%EOF\n"))
        self.assert_http_error(400, lambda: asyncio.run(weekly_report_routes.upload_weekly_report_attachment(
            report["id"], request_for(self.intern_a), bad, self.db)))

    def test_week_requires_monday_and_submit_requires_content(self):
        with self.assertRaises(ValidationError):
            self.data(week="2026-10-06")
        report = self.service.create(self.intern_a, self.data(work_content="", results=""))
        self.assert_http_error(422, lambda: self.service.submit(report["id"], self.intern_a))
