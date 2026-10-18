import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import load_workbook
from pypdf import PdfReader

from app import database
from app.evaluation_service import InternEvaluationService
from app.final_report_service import FinalReportService
from app.routes import final_report_routes
from app.schemas import InternEvaluationCreate


def request_for(user):
    return SimpleNamespace(state=SimpleNamespace(current_user=user))


class FinalReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us20-")
        cls.db_path = Path(cls.temp_dir.name) / "us20.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
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
        if len(mentors) < 2 or len(interns) < 2:
            db.close()
            raise RuntimeError("US20 fixtures require two mentors and two approved interns.")
        cls.mentor_a, cls.mentor_b = map(dict, mentors)
        cls.intern_a, cls.intern_b = map(dict, interns)
        programs = db.execute("SELECT ma_chuong_trinh FROM CHUONG_TRINH_THUC_TAP ORDER BY ma_chuong_trinh LIMIT 2").fetchall()
        if not programs:
            dept = db.execute("SELECT ma_phong_ban FROM PHONG_BAN ORDER BY ma_phong_ban LIMIT 1").fetchone()
            dept_id = dept["ma_phong_ban"] if dept else 1
            db.execute("""
                INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, ma_phong_ban, ngay_bat_dau, ngay_ket_thuc, chi_tieu, trang_thai)
                VALUES ('CT-US20-1', 'Chương trình 2026-1', ?, '2026-01-01', '2026-06-30', 20, 'DangMo'),
                       ('CT-US20-2', 'Chương trình 2026-2', ?, '2026-07-01', '2026-12-31', 20, 'DangMo')
            """, (dept_id, dept_id))
            db.commit()
            programs = db.execute("SELECT ma_chuong_trinh FROM CHUONG_TRINH_THUC_TAP ORDER BY ma_chuong_trinh LIMIT 2").fetchall()
        cls.program_id = programs[0]["ma_chuong_trinh"]
        cls.other_program_id = programs[-1]["ma_chuong_trinh"]

        for intern in (cls.intern_a, cls.intern_b):
            db.execute("""
                INSERT OR IGNORE INTO UNG_TUYEN_CHUONG_TRINH
                    (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet)
                VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP)
            """, (cls.program_id, intern["ma_ho_so"]))
            db.execute("""
                UPDATE UNG_TUYEN_CHUONG_TRINH
                SET trang_thai='DaDuyet'
                WHERE ma_chuong_trinh=? AND ma_ho_so=?
            """, (cls.program_id, intern["ma_ho_so"]))
            db.execute("DELETE FROM PHAN_CONG_MENTOR_TTS WHERE ma_ho_so=?", (intern["ma_ho_so"],))

        db.execute("""
            INSERT INTO PHAN_CONG_MENTOR_TTS (ma_nguoi_dung_mentor, ma_ho_so, ma_chuong_trinh)
            VALUES (?, ?, ?), (?, ?, ?)
        """, (
            cls.mentor_a["ma_nguoi_dung"], cls.intern_a["ma_ho_so"], cls.program_id,
            cls.mentor_b["ma_nguoi_dung"], cls.intern_b["ma_ho_so"], cls.program_id,
        ))
        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()
        self.db.execute("DELETE FROM DANH_GIA_THUC_TAP")
        self.db.commit()
        self.evaluation_service = InternEvaluationService(self.db)
        self.report_service = FinalReportService(self.db)

    def tearDown(self):
        self.db.close()

    def make_eval(self, mentor_id, profile_id, program_id, period="FINAL", **scores):
        defaults = dict(
            professional_skill_score=4,
            work_quality_score=4,
            initiative_score=4,
            communication_teamwork_score=5,
            attitude_discipline_score=5,
            overall_comment=f"Đánh giá {period} tốt.",
        )
        defaults.update(scores)
        return self.evaluation_service.create(
            mentor_id,
            InternEvaluationCreate(
                internship_profile_id=profile_id,
                program_id=program_id,
                evaluation_period=period,
                **defaults,
            ),
        )

    def test_hr_admin_can_list_and_get_reports(self):
        self.make_eval(self.mentor_a["ma_nguoi_dung"], self.intern_a["ma_ho_so"], self.program_id, period="FINAL")

        admin_req = request_for({"ma_nguoi_dung": 1, "vai_tro": "Admin"})
        hr_req = request_for({"ma_nguoi_dung": 2, "vai_tro": "HR"})

        res_admin = final_report_routes.list_final_reports(
            request=admin_req,
            program_id=None,
            internship_profile_id=None,
            status="ALL",
            search=None,
            page=1,
            page_size=10,
            db=self.db,
        )
        self.assertGreaterEqual(res_admin["total_items"], 2)
        self.assertEqual(res_admin["summary"]["complete_count"], 1)
        self.assertGreaterEqual(res_admin["summary"]["incomplete_count"], 1)

        detail_hr = final_report_routes.get_final_report(
            profile_id=self.intern_a["ma_ho_so"],
            program_id=self.program_id,
            request=hr_req,
            db=self.db,
        )
        self.assertEqual(detail_hr["internship_profile_id"], self.intern_a["ma_ho_so"])
        self.assertEqual(detail_hr["data_status"], "DU_DU_LIEU")
        self.assertIsNotNone(detail_hr["final_evaluation"])
        self.assertEqual(detail_hr["final_evaluation"]["average_score"], 4.4)

    def test_intern_and_mentor_forbidden_from_report_api(self):
        intern_req = request_for({**self.intern_a, "vai_tro": "ThucTapSinh"})
        mentor_req = request_for({**self.mentor_a, "vai_tro": "Mentor"})

        with self.assertRaises(HTTPException) as cm_intern_list:
            final_report_routes.list_final_reports(request=intern_req, db=self.db)
        self.assertEqual(cm_intern_list.exception.status_code, 403)

        with self.assertRaises(HTTPException) as cm_mentor_list:
            final_report_routes.list_final_reports(request=mentor_req, db=self.db)
        self.assertEqual(cm_mentor_list.exception.status_code, 403)

        with self.assertRaises(HTTPException) as cm_intern_get:
            final_report_routes.get_final_report(
                profile_id=self.intern_a["ma_ho_so"],
                program_id=self.program_id,
                request=intern_req,
                db=self.db,
            )
        self.assertEqual(cm_intern_get.exception.status_code, 403)

        with self.assertRaises(HTTPException) as cm_mentor_get:
            final_report_routes.get_final_report(
                profile_id=self.intern_a["ma_ho_so"],
                program_id=self.program_id,
                request=mentor_req,
                db=self.db,
            )
        self.assertEqual(cm_mentor_get.exception.status_code, 403)

    def test_complete_report_with_us19_evaluations(self):
        self.make_eval(
            self.mentor_a["ma_nguoi_dung"],
            self.intern_a["ma_ho_so"],
            self.program_id,
            period="MIDTERM",
            professional_skill_score=3,
            work_quality_score=3,
            initiative_score=3,
            communication_teamwork_score=3,
            attitude_discipline_score=3,
        )
        self.make_eval(
            self.mentor_a["ma_nguoi_dung"],
            self.intern_a["ma_ho_so"],
            self.program_id,
            period="FINAL",
            professional_skill_score=5,
            work_quality_score=5,
            initiative_score=5,
            communication_teamwork_score=5,
            attitude_discipline_score=5,
        )

        report = self.report_service.get_final_report(self.intern_a["ma_ho_so"], self.program_id)
        self.assertEqual(report["data_status"], "DU_DU_LIEU")
        self.assertEqual(report["missing_requirements"], [])
        self.assertEqual(report["has_final_evaluation"], True)
        self.assertEqual(report["has_midterm_evaluation"], True)
        self.assertEqual(report["final_average_score"], 5.0)
        self.assertEqual(report["midterm_average_score"], 3.0)
        self.assertEqual(report["final_evaluation"]["evaluator_id"], self.mentor_a["ma_nguoi_dung"])
        self.assertEqual(report["midterm_evaluation"]["evaluator_id"], self.mentor_a["ma_nguoi_dung"])

        count = self.db.execute("SELECT COUNT(*) FROM DANH_GIA_THUC_TAP").fetchone()[0]
        self.assertEqual(count, 2)

    def test_incomplete_report_without_evaluation(self):
        report = self.report_service.get_final_report(self.intern_b["ma_ho_so"], self.program_id)
        self.assertEqual(report["data_status"], "CHUA_DU_LIEU")
        self.assertIn("FINAL_EVALUATION", report["missing_requirements"])
        self.assertEqual(report["has_final_evaluation"], False)
        self.assertIsNone(report["final_average_score"])
        self.assertIsNone(report["final_evaluation"])

    def test_incomplete_report_without_mentor(self):
        self.db.execute(
            "DELETE FROM PHAN_CONG_MENTOR_TTS WHERE ma_ho_so=? AND ma_chuong_trinh=?",
            (self.intern_b["ma_ho_so"], self.program_id),
        )
        self.db.commit()

        try:
            report = self.report_service.get_final_report(self.intern_b["ma_ho_so"], self.program_id)
            self.assertEqual(report["has_mentor"], False)
            self.assertIn("MENTOR", report["missing_requirements"])
            self.assertEqual(report["data_status"], "CHUA_DU_LIEU")
        finally:
            self.db.execute("""
                INSERT INTO PHAN_CONG_MENTOR_TTS (ma_nguoi_dung_mentor, ma_ho_so, ma_chuong_trinh)
                VALUES (?, ?, ?)
            """, (self.mentor_b["ma_nguoi_dung"], self.intern_b["ma_ho_so"], self.program_id))
            self.db.commit()

    def test_report_filtering_by_program_and_status(self):
        self.make_eval(self.mentor_a["ma_nguoi_dung"], self.intern_a["ma_ho_so"], self.program_id, period="FINAL")

        all_reports = self.report_service.list_final_reports(program_id=self.program_id, status="ALL")
        self.assertEqual(len(all_reports["items"]), 2)

        complete_reports = self.report_service.list_final_reports(program_id=self.program_id, status="DU_DU_LIEU")
        self.assertEqual(len(complete_reports["items"]), 1)
        self.assertEqual(complete_reports["items"][0]["internship_profile_id"], self.intern_a["ma_ho_so"])

        incomplete_reports = self.report_service.list_final_reports(program_id=self.program_id, status="CHUA_DU_LIEU")
        self.assertEqual(len(incomplete_reports["items"]), 1)
        self.assertEqual(incomplete_reports["items"][0]["internship_profile_id"], self.intern_b["ma_ho_so"])

    def test_report_search(self):
        intern_name = self.intern_a["ho_ten"]
        found = self.report_service.list_final_reports(search=intern_name[:4])
        self.assertTrue(any(it["intern_name"] == intern_name for it in found["items"]))

    def test_nonexistent_report_returns_404(self):
        with self.assertRaises(HTTPException) as cm:
            self.report_service.get_final_report(profile_id=99999, program_id=99999)
        self.assertEqual(cm.exception.status_code, 404)

    def test_us34_export_uses_us20_filter_and_role_guard(self):
        request = request_for({"vai_tro": "HR"})
        filtered = self.report_service.list_final_reports(program_id=self.program_id)
        response = final_report_routes.export_final_reports(
            request, "xlsx", program_id=self.program_id,
            internship_profile_id=None, status="ALL", search=None, db=self.db,
        )
        workbook = load_workbook(BytesIO(response.body), read_only=True)
        rows = [row for row in workbook.active.values if row and isinstance(row[0], int)]
        self.assertEqual(len(rows), filtered["total_items"])
        workbook.close()

        pdf_response = final_report_routes.export_final_reports(
            request, "pdf", program_id=self.program_id,
            internship_profile_id=None, status="ALL", search=None, db=self.db,
        )
        reader = PdfReader(BytesIO(pdf_response.body))
        self.assertIn("Báo cáo đánh giá cuối kỳ", reader.pages[0].extract_text())

        with self.assertRaises(HTTPException) as denied:
            final_report_routes.export_final_reports(
                request_for({"vai_tro": "Mentor"}), "xlsx", db=self.db,
            )
        self.assertEqual(denied.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
