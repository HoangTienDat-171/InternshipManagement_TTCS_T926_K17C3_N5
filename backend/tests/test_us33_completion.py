import sqlite3
import tempfile
import unittest
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import load_workbook
from pypdf import PdfReader

from app.reporting_service import CompletionStatisticsService
from app.routes import reporting_routes
from app import database


AS_OF = date(2026, 10, 14)


def request_for(role, user_id=90):
    return SimpleNamespace(state=SimpleNamespace(current_user={"vai_tro": role, "ma_nguoi_dung": user_id}))


class CompletionStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE PHONG_BAN (ma_phong_ban INTEGER PRIMARY KEY, ten_phong_ban TEXT);
            CREATE TABLE CHUONG_TRINH_THUC_TAP (
                ma_chuong_trinh INTEGER PRIMARY KEY, ten_ct TEXT, ma_phong_ban INTEGER,
                ngay_ket_thuc DATE
            );
            CREATE TABLE TRUONG_DAI_HOC (ma_truong INTEGER PRIMARY KEY, ten_truong TEXT);
            CREATE TABLE NGUOI_DUNG (
                ma_nguoi_dung INTEGER PRIMARY KEY, ma_phong_ban INTEGER,
                ho_ten TEXT, email TEXT, vai_tro TEXT
            );
            CREATE TABLE HO_SO_THUC_TAP (
                ma_ho_so INTEGER PRIMARY KEY, ma_nguoi_dung INTEGER,
                ma_truong INTEGER, chuyen_nganh TEXT
            );
            CREATE TABLE UNG_TUYEN_CHUONG_TRINH (
                ma_ung_tuyen INTEGER PRIMARY KEY, ma_chuong_trinh INTEGER,
                ma_ho_so INTEGER, trang_thai TEXT,
                completion_status TEXT NOT NULL DEFAULT 'ChuaHoanThanh',
                completion_updated_by INTEGER, completion_updated_at DATETIME
            );
            INSERT INTO PHONG_BAN VALUES (1, 'Công nghệ'), (2, 'Thiết kế');
            INSERT INTO CHUONG_TRINH_THUC_TAP VALUES
                (10, 'Chương trình A', 1, '2026-10-13'),
                (20, 'Chương trình B', 2, '2026-10-14'),
                (30, 'Chương trình đang diễn ra', 1, '2999-10-15'),
                (40, 'Chưa có ngày kết thúc', 1, NULL);
            INSERT INTO NGUOI_DUNG VALUES
                (1, 1, 'An', 'an@example.test', 'ThucTapSinh'),
                (2, 2, 'Bình', 'binh@example.test', 'ThucTapSinh'),
                (3, 1, 'Chi', 'chi@example.test', 'ThucTapSinh'),
                (4, 1, 'Mentor', 'mentor@example.test', 'Mentor'),
                (90, 1, 'HR', 'hr@example.test', 'HR');
            INSERT INTO HO_SO_THUC_TAP VALUES
                (101, 1, NULL, 'Kỹ thuật'), (102, 2, NULL, 'Thiết kế'),
                (103, 3, NULL, 'Kỹ thuật');
            INSERT INTO UNG_TUYEN_CHUONG_TRINH VALUES
                (1001, 10, 101, 'DaDuyet', 'HoanThanh', 90, '2026-10-13 10:00:00'),
                (1002, 10, 102, 'DaDuyet', 'ChuaHoanThanh', NULL, NULL),
                (1003, 20, 101, 'DaDuyet', 'ChuaHoanThanh', NULL, NULL),
                (1004, 30, 103, 'DaDuyet', 'ChuaHoanThanh', NULL, NULL),
                (1005, 40, 103, 'DaDuyet', 'ChuaHoanThanh', NULL, NULL),
                (1006, 10, 103, 'TuChoi', 'ChuaHoanThanh', NULL, NULL);
        """)
        self.service = CompletionStatisticsService(self.db)

    def tearDown(self):
        self.db.close()

    def test_sqlite_bootstrap_adds_completion_fields_to_existing_schema_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = f"{directory}/legacy.sqlite"
            legacy = sqlite3.connect(db_path)
            legacy.execute("""
                CREATE TABLE UNG_TUYEN_CHUONG_TRINH (
                    ma_ung_tuyen INTEGER PRIMARY KEY AUTOINCREMENT,
                    ma_chuong_trinh INTEGER NOT NULL,
                    ma_ho_so INTEGER NOT NULL,
                    trang_thai TEXT NOT NULL DEFAULT 'ChoDuyet',
                    ngay_ung_tuyen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    ngay_xet_duyet DATETIME,
                    nguoi_xet_duyet INTEGER,
                    UNIQUE(ma_chuong_trinh, ma_ho_so)
                )
            """)
            legacy.execute("INSERT INTO UNG_TUYEN_CHUONG_TRINH(ma_chuong_trinh, ma_ho_so, trang_thai) VALUES(1, 1, 'DaDuyet')")
            legacy.commit()
            legacy.close()
            with patch.object(database, "DATABASE_BACKEND", "sqlite"), patch.object(database, "DB_FILE", db_path):
                database.init_db()
                database.init_db()
            migrated = sqlite3.connect(db_path)
            columns = {row[1] for row in migrated.execute("PRAGMA table_info(UNG_TUYEN_CHUONG_TRINH)")}
            self.assertTrue({"completion_status", "completion_updated_by", "completion_updated_at"}.issubset(columns))
            status = migrated.execute("SELECT completion_status FROM UNG_TUYEN_CHUONG_TRINH WHERE ma_ung_tuyen=1").fetchone()[0]
            self.assertEqual(status, "ChuaHoanThanh")
            migrated.close()

    def test_eligible_completed_rate_and_program_breakdown_share_same_cohort(self):
        report = self.service.overview(as_of=AS_OF)
        self.assertEqual(report["summary"], {
            "eligible": 3, "completed": 1, "incomplete": 2, "completion_rate": 33.3,
        })
        self.assertEqual(report["total_items"], 3)
        self.assertEqual(sum(row["eligible"] for row in report["programs"]), report["total_items"])
        self.assertEqual(sum(row["completed"] for row in report["programs"]), report["summary"]["completed"])
        program_a = next(row for row in report["programs"] if row["id"] == 10)
        self.assertEqual((program_a["eligible"], program_a["completed"], program_a["completion_rate"]), (2, 1, 50.0))
        self.assertNotIn(1004, [row["application_id"] for row in report["items"]])
        self.assertNotIn(1005, [row["application_id"] for row in report["items"]])
        self.assertNotIn(1006, [row["application_id"] for row in report["items"]])

    def test_filters_pagination_and_zero_denominator(self):
        filtered = self.service.overview(program_id=20, department_id=2, as_of=AS_OF, page=1, page_size=1)
        self.assertEqual(filtered["summary"]["eligible"], 1)
        self.assertEqual(filtered["items"][0]["application_id"], 1003)
        filtered_date = self.service.overview(date_from=date(2026, 10, 14), date_to=AS_OF, as_of=AS_OF)
        self.assertEqual(filtered_date["items"][0]["application_id"], 1003)
        empty = self.service.overview(program_id=30, as_of=AS_OF)
        self.assertEqual(empty["summary"]["eligible"], 0)
        self.assertIsNone(empty["summary"]["completion_rate"])
        self.assertEqual(empty["total_pages"], 0)

    def test_export_uses_same_filter_values_and_contains_summary_and_detail(self):
        response = reporting_routes.export_completion_statistics(
            request_for("HR"), "xlsx", program_id=10, department_id=None,
            date_from=None, date_to=None, search=None, db=self.db,
        )
        workbook = load_workbook(BytesIO(response.body), read_only=True)
        rows = list(workbook.active.values)
        self.assertTrue(any(row and row[0] == "Đủ điều kiện (Eligible)" and row[1] == 2 for row in rows))
        self.assertTrue(any(row and row[0] == 1001 for row in rows))
        self.assertTrue(any(row and row[0] == 1002 for row in rows))
        workbook.close()
        pdf = reporting_routes.export_completion_statistics(
            request_for("Admin"), "pdf", program_id=10, department_id=None,
            date_from=None, date_to=None, search=None, db=self.db,
        )
        pdf_text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf.body)).pages)
        self.assertIn("Hoàn thành", pdf_text)
        self.assertIn("Chưa hoàn thành", pdf_text)

    def test_completion_export_with_no_eligible_rows_returns_not_found_and_denies_mentor(self):
        with self.assertRaises(HTTPException) as denied:
            reporting_routes.export_completion_statistics(
                request_for("Mentor"), "xlsx", program_id=10, department_id=None,
                date_from=None, date_to=None, search=None, db=self.db,
            )
        self.assertEqual(denied.exception.status_code, 403)
        with self.assertRaises(HTTPException) as empty:
            reporting_routes.export_completion_statistics(
                request_for("HR"), "xlsx", program_id=30, department_id=None,
                date_from=None, date_to=None, search=None, db=self.db,
            )
        self.assertEqual(empty.exception.status_code, 404)

    def test_only_hr_admin_can_update_and_only_eligible_application_is_mutable(self):
        with patch.object(reporting_routes.database_module, "DATABASE_BACKEND", "sqlite"):
            with self.assertRaises(HTTPException) as denied:
                reporting_routes.update_application_completion(
                    1002, request_for("Mentor"), "HoanThanh", self.db,
                )
            self.assertEqual(denied.exception.status_code, 403)

            response = reporting_routes.update_application_completion(
                1002, request_for("HR", 90), "HoanThanh", self.db,
            )
            self.assertEqual(response["completion_status"], "HoanThanh")
            row = self.db.execute("SELECT completion_status, completion_updated_by, completion_updated_at FROM UNG_TUYEN_CHUONG_TRINH WHERE ma_ung_tuyen=1002").fetchone()
            self.assertEqual(row["completion_status"], "HoanThanh")
            self.assertEqual(row["completion_updated_by"], 90)
            self.assertIsNotNone(row["completion_updated_at"])
            completed_report = CompletionStatisticsService(self.db).overview(program_id=10, as_of=AS_OF)
            self.assertEqual((completed_report["summary"]["eligible"], completed_report["summary"]["completed"]), (2, 2))

            reporting_routes.update_application_completion(
                1002, request_for("Admin", 90), "ChuaHoanThanh", self.db,
            )
            reset_report = CompletionStatisticsService(self.db).overview(program_id=10, as_of=AS_OF)
            self.assertEqual((reset_report["summary"]["eligible"], reset_report["summary"]["completed"]), (2, 1))

            with self.assertRaises(HTTPException) as ineligible:
                reporting_routes.update_application_completion(
                    1004, request_for("Admin", 90), "HoanThanh", self.db,
                )
            self.assertEqual(ineligible.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
