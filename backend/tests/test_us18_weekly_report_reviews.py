"""US18 Mentor review authorization, concurrency and feedback regressions."""
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
from app.schemas import WeeklyReportCreate, WeeklyReportReview
from app.weekly_report_service import WeeklyReportService


def request_for(user):
    return SimpleNamespace(state=SimpleNamespace(current_user=user))


class WeeklyReportReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us18-", ignore_cleanup_errors=True)
        cls.temp_path = Path(cls.temp_dir.name)
        cls.db_path = cls.temp_path / "us18.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.storage_patch = patch.object(weekly_report_routes, "REPORT_STORAGE_ROOT", cls.temp_path / "uploads")
        cls.backend_patch.start()
        cls.path_patch.start()
        cls.storage_patch.start()
        database.init_db()

        db = database.get_db_connection()
        mentors = db.execute("""
            SELECT ma_nguoi_dung, ho_ten, vai_tro FROM NGUOI_DUNG
            WHERE vai_tro='Mentor' ORDER BY ma_nguoi_dung LIMIT 2
        """).fetchall()
        interns = db.execute("""
            SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten, u.vai_tro
            FROM HO_SO_THUC_TAP h JOIN NGUOI_DUNG u ON u.ma_nguoi_dung=h.ma_nguoi_dung
            WHERE u.vai_tro='ThucTapSinh' AND h.trang_thai_xet_duyet='DaDuyet'
            ORDER BY h.ma_ho_so LIMIT 2
        """).fetchall()
        if len(mentors) != 2 or len(interns) != 2:
            raise RuntimeError("US18 fixtures require two mentors and two approved interns.")
        cls.mentor_a, cls.mentor_b = map(dict, mentors)
        cls.intern_a, cls.intern_b = map(dict, interns)
        program = db.execute("SELECT ma_chuong_trinh FROM CHUONG_TRINH_THUC_TAP ORDER BY ma_chuong_trinh LIMIT 1").fetchone()
        cls.program_id = program["ma_chuong_trinh"]
        for intern in (cls.intern_a, cls.intern_b):
            db.execute("""
                INSERT OR IGNORE INTO UNG_TUYEN_CHUONG_TRINH
                    (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet)
                VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP)
            """, (cls.program_id, intern["ma_ho_so"]))
            db.execute("UPDATE UNG_TUYEN_CHUONG_TRINH SET trang_thai='DaDuyet' WHERE ma_chuong_trinh=? AND ma_ho_so=?", (cls.program_id, intern["ma_ho_so"]))
            db.execute("DELETE FROM PHAN_CONG_MENTOR_TTS WHERE ma_ho_so=?", (intern["ma_ho_so"],))
        db.execute("INSERT INTO PHAN_CONG_MENTOR_TTS (ma_nguoi_dung_mentor, ma_ho_so) VALUES (?, ?), (?, ?)", (
            cls.mentor_a["ma_nguoi_dung"], cls.intern_a["ma_ho_so"],
            cls.mentor_b["ma_nguoi_dung"], cls.intern_b["ma_ho_so"],
        ))
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
        self.db.execute("DELETE FROM NHAN_XET_BAO_CAO_TUAN")
        self.db.execute("DELETE FROM BAO_CAO_TUAN")
        self.db.execute("DELETE FROM THONG_BAO WHERE loai IN ('WEEKLY_REPORT_SUBMITTED','WEEKLY_REPORT_REVIEWED')")
        self.db.commit()
        self.service = WeeklyReportService(self.db)

    def tearDown(self):
        self.db.close()

    def create_report(self, intern, week, submit=True):
        report = self.service.create(intern, WeeklyReportCreate(
            program_id=self.program_id,
            week_start=week,
            work_content="Công việc trong tuần",
            results="Kết quả trong tuần",
            difficulties="Không có",
        ))
        return self.service.submit(report["id"], intern) if submit else report

    def assert_http_error(self, code, callback):
        with self.assertRaises(HTTPException) as context:
            callback()
        self.assertEqual(context.exception.status_code, code)

    def test_assigned_mentor_list_detail_and_outsider_are_scoped(self):
        report_a = self.create_report(self.intern_a, "2026-10-05")
        self.create_report(self.intern_b, "2026-10-12")
        own = self.service.list_for_mentor(self.mentor_a["ma_nguoi_dung"])
        self.assertEqual([item["id"] for item in own], [report_a["id"]])
        self.assertEqual(self.service.get_for_mentor(report_a["id"], self.mentor_a["ma_nguoi_dung"])["intern_user_id"], self.intern_a["ma_nguoi_dung"])
        self.assert_http_error(403, lambda: self.service.get_for_mentor(report_a["id"], self.mentor_b["ma_nguoi_dung"]))
        self.assert_http_error(403, lambda: self.service.review(
            report_a["id"], self.mentor_b, WeeklyReportReview(comment="Không được phép")))

    def test_review_uses_server_actor_time_notifies_and_is_visible_to_intern(self):
        report = self.create_report(self.intern_a, "2026-10-05")
        reviewed = self.service.review(report["id"], self.mentor_a, WeeklyReportReview(comment="  Tiến độ tốt.  "))
        self.assertEqual(reviewed["review_comment"], "Tiến độ tốt.")
        self.assertEqual(reviewed["reviewed_by"], self.mentor_a["ma_nguoi_dung"])
        self.assertIsNotNone(reviewed["reviewed_at"])
        intern_view = self.service.get(report["id"], self.intern_a["ma_nguoi_dung"])
        self.assertEqual(intern_view["review_comment"], "Tiến độ tốt.")
        notification = self.db.execute("""
            SELECT * FROM THONG_BAO WHERE loai='WEEKLY_REPORT_REVIEWED' AND ma_nguoi_dung=?
        """, (self.intern_a["ma_nguoi_dung"],)).fetchone()
        self.assertIsNotNone(notification)
        self.assertEqual(str(notification["reference_id"]), str(report["id"]))

    def test_draft_tts_and_mass_assignment_cannot_review(self):
        draft = self.create_report(self.intern_a, "2026-10-05", submit=False)
        self.assert_http_error(409, lambda: self.service.review(
            draft["id"], self.mentor_a, WeeklyReportReview(comment="Draft")))
        self.assert_http_error(403, lambda: weekly_report_routes.review_weekly_report(
            draft["id"], WeeklyReportReview(comment="TTS"), request_for(self.intern_a), self.db))
        with self.assertRaises(ValidationError):
            WeeklyReportReview(comment="Injected", mentor_id=999, reviewed_by=999, report_id=999)

    def test_concurrent_review_creates_one_row_and_one_notification(self):
        report = self.create_report(self.intern_a, "2026-10-05")

        def review_once(comment):
            connection = database.get_db_connection()
            try:
                return WeeklyReportService(connection).review(
                    report["id"], self.mentor_a, WeeklyReportReview(comment=comment))["review_id"]
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            review_ids = list(pool.map(review_once, ("Nhận xét A", "Nhận xét B")))
        self.assertEqual(review_ids[0], review_ids[1])
        count = self.db.execute("SELECT COUNT(*) FROM NHAN_XET_BAO_CAO_TUAN WHERE ma_bao_cao=?", (report["id"],)).fetchone()[0]
        notifications = self.db.execute("SELECT COUNT(*) FROM THONG_BAO WHERE loai='WEEKLY_REPORT_REVIEWED'").fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(notifications, 1)

    def test_attachment_download_requires_current_assignment(self):
        report = self.create_report(self.intern_a, "2026-10-05", submit=False)
        upload = UploadFile(filename="weekly.pdf", file=io.BytesIO(b"%PDF-1.4\nreview test\n%%EOF\n"))
        asyncio.run(weekly_report_routes.upload_weekly_report_attachment(
            report["id"], request_for(self.intern_a), upload, self.db))
        self.service.submit(report["id"], self.intern_a)
        response = weekly_report_routes.download_mentor_weekly_report_attachment(
            report["id"], request_for(self.mentor_a), self.db)
        self.assertTrue(Path(response.path).is_file())
        self.assert_http_error(403, lambda: weekly_report_routes.download_mentor_weekly_report_attachment(
            report["id"], request_for(self.mentor_b), self.db))
