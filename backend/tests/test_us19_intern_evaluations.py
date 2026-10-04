import tempfile
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import database
from app.evaluation_service import InternEvaluationService
from app.routes import evaluation_routes
from app.schemas import InternEvaluationCreate, InternEvaluationUpdate


def request_for(user):
    return SimpleNamespace(state=SimpleNamespace(current_user=user))


class InternEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us19-")
        cls.db_path = Path(cls.temp_dir.name) / "us19.sqlite3"
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
            raise RuntimeError("US19 fixtures require two mentors and two approved interns.")
        cls.mentor_a, cls.mentor_b = map(dict, mentors)
        cls.intern_a, cls.intern_b = map(dict, interns)
        programs = db.execute("SELECT ma_chuong_trinh FROM CHUONG_TRINH_THUC_TAP ORDER BY ma_chuong_trinh LIMIT 2").fetchall()
        if not programs:
            db.close()
            raise RuntimeError("US19 fixtures require an internship program.")
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
            INSERT INTO PHAN_CONG_MENTOR_TTS (ma_nguoi_dung_mentor, ma_ho_so)
            VALUES (?, ?), (?, ?)
        """, (
            cls.mentor_a["ma_nguoi_dung"], cls.intern_a["ma_ho_so"],
            cls.mentor_b["ma_nguoi_dung"], cls.intern_b["ma_ho_so"],
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
        self.service = InternEvaluationService(self.db)

    def tearDown(self):
        self.db.close()

    def data(self, profile_id=None, program_id=None, period="MIDTERM", **changes):
        values = {
            "internship_profile_id": profile_id or self.intern_a["ma_ho_so"],
            "program_id": program_id or self.program_id,
            "evaluation_period": period,
            "professional_skill_score": 4,
            "work_quality_score": 4,
            "initiative_score": 5,
            "communication_teamwork_score": 4,
            "attitude_discipline_score": 5,
            "overall_comment": "  Hoàn thành tốt mục tiêu đã thống nhất.  ",
        }
        values.update(changes)
        return InternEvaluationCreate(**values)

    def assert_http_error(self, status_code, callback):
        with self.assertRaises(HTTPException) as context:
            callback()
        self.assertEqual(context.exception.status_code, status_code)

    def create_as_mentor_a(self, data=None):
        return evaluation_routes.create_mentor_evaluation(
            data or self.data(), request_for(self.mentor_a), self.db,
        )

    def test_assigned_mentor_creates_server_scoped_evaluation(self):
        result = self.create_as_mentor_a()
        self.assertEqual(result["mentor_id"], self.mentor_a["ma_nguoi_dung"])
        self.assertEqual(result["internship_profile_id"], self.intern_a["ma_ho_so"])
        self.assertEqual(result["evaluation_period"], "MIDTERM")
        self.assertEqual(result["average_score"], 4.4)
        self.assertEqual(result["overall_comment"], "Hoàn thành tốt mục tiêu đã thống nhất.")
        self.assertNotEqual(result["created_at"], "2000-01-01 00:00:00")
        self.assertNotEqual(result["evaluated_at"], "2000-01-01 00:00:00")
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(DANH_GIA_THUC_TAP)")}
        self.assertNotIn("average_score", columns)

    def test_minimum_and_maximum_scores_are_accepted_and_average_is_server_computed(self):
        lowest = self.create_as_mentor_a(self.data(
            professional_skill_score=1,
            work_quality_score=1,
            initiative_score=1,
            communication_teamwork_score=1,
            attitude_discipline_score=1,
        ))
        self.assertEqual(lowest["average_score"], 1.0)
        final = self.service.create(self.mentor_a["ma_nguoi_dung"], self.data(
            period="FINAL",
            professional_skill_score=5,
            work_quality_score=5,
            initiative_score=5,
            communication_teamwork_score=5,
            attitude_discipline_score=5,
        ))
        self.assertEqual(final["average_score"], 5.0)

    def test_wrong_mentor_and_unapproved_program_are_blocked(self):
        self.assert_http_error(403, lambda: self.service.create(self.mentor_b["ma_nguoi_dung"], self.data()))
        self.assert_http_error(403, lambda: self.service.create(
            self.mentor_a["ma_nguoi_dung"], self.data(program_id=999999)))

    def test_score_types_boundaries_and_required_comment_are_validated(self):
        self.data(professional_skill_score=1, attitude_discipline_score=5)
        for field, invalid_value in (
            ("professional_skill_score", 0),
            ("work_quality_score", 6),
            ("initiative_score", 1.5),
            ("communication_teamwork_score", "4"),
        ):
            with self.subTest(field=field, value=invalid_value):
                with self.assertRaises(ValidationError):
                    self.data(**{field: invalid_value})
        for blank in ("", "   ", "\n\t"):
            with self.subTest(comment=repr(blank)):
                with self.assertRaises(ValidationError):
                    self.data(overall_comment=blank)
        with self.assertRaises(ValidationError):
            self.data(mentor_id=999)
        with self.assertRaises(ValidationError):
            self.data(average_score=5)
        with self.assertRaises(ValidationError):
            self.data(evaluated_at="2000-01-01", created_at="2000-01-01")

    def test_database_constraints_protect_scores_and_business_key(self):
        self.create_as_mentor_a()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("""
                INSERT INTO DANH_GIA_THUC_TAP (
                    ma_ho_so, ma_chuong_trinh, ma_nguoi_dung_mentor, ky_danh_gia,
                    professional_skill_score, work_quality_score, initiative_score,
                    communication_teamwork_score, attitude_discipline_score, overall_comment
                ) VALUES (?, ?, ?, 'MIDTERM', 4, 4, 4, 4, 6, 'Sai điểm')
            """, (self.intern_a["ma_ho_so"], self.program_id, self.mentor_a["ma_nguoi_dung"]))
        self.db.rollback()
        self.assert_http_error(409, lambda: self.service.create(self.mentor_a["ma_nguoi_dung"], self.data()))
        final = self.service.create(self.mentor_a["ma_nguoi_dung"], self.data(period="FINAL"))
        self.assertEqual(final["evaluation_period"], "FINAL")

    def test_concurrent_create_has_one_winner(self):
        payload = self.data()

        def create_once():
            db = database.get_db_connection()
            try:
                return InternEvaluationService(db).create(self.mentor_a["ma_nguoi_dung"], payload)["id"]
            except HTTPException as exc:
                return exc.status_code
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create_once(), range(2)))
        self.assertEqual(sum(isinstance(result, int) and result != 409 for result in results), 1)
        self.assertEqual(results.count(409), 1)
        count = self.db.execute("SELECT COUNT(*) FROM DANH_GIA_THUC_TAP").fetchone()[0]
        self.assertEqual(count, 1)

    def test_assigned_mentor_can_edit_but_another_mentor_cannot(self):
        created = self.create_as_mentor_a()
        self.db.execute("UPDATE DANH_GIA_THUC_TAP SET updated_at='2000-01-01 00:00:00' WHERE ma_danh_gia=?", (created["id"],))
        self.db.commit()
        updated = self.service.update(created["id"], self.mentor_a["ma_nguoi_dung"], InternEvaluationUpdate(
            initiative_score=3, overall_comment="Đã cập nhật nhận xét."))
        self.assertEqual(updated["initiative_score"], 3)
        self.assertEqual(updated["overall_comment"], "Đã cập nhật nhận xét.")
        self.assertNotEqual(updated["updated_at"], "2000-01-01 00:00:00")
        self.assert_http_error(403, lambda: self.service.get_for_mentor(
            created["id"], self.mentor_b["ma_nguoi_dung"]))
        self.assert_http_error(403, lambda: self.service.update(
            created["id"], self.mentor_b["ma_nguoi_dung"], InternEvaluationUpdate(initiative_score=2)))
        with self.assertRaises(ValidationError):
            InternEvaluationUpdate(created_at="2000-01-01", mentor_id=999)
        with self.assertRaises(ValidationError):
            InternEvaluationUpdate(internship_profile_id=self.intern_b["ma_ho_so"])

    def test_tts_reads_only_own_history_and_cannot_write(self):
        own = self.create_as_mentor_a()
        final = self.service.create(self.mentor_a["ma_nguoi_dung"], self.data(period="FINAL"))
        other = self.service.create(self.mentor_b["ma_nguoi_dung"], self.data(
            profile_id=self.intern_b["ma_ho_so"]))
        request = request_for({**self.intern_a, "vai_tro": "ThucTapSinh"})
        history = evaluation_routes.list_my_evaluations(request, self.db)
        self.assertEqual({item["id"] for item in history}, {own["id"], final["id"]})
        self.assertEqual(evaluation_routes.get_my_evaluation(own["id"], request, self.db)["id"], own["id"])
        self.assert_http_error(404, lambda: evaluation_routes.get_my_evaluation(other["id"], request, self.db))
        self.assert_http_error(403, lambda: evaluation_routes.create_mentor_evaluation(self.data(), request, self.db))
        self.assert_http_error(403, lambda: evaluation_routes.update_mentor_evaluation(
            own["id"], InternEvaluationUpdate(initiative_score=2), request, self.db))

    def test_hr_admin_can_read_but_cannot_write(self):
        created = self.create_as_mentor_a()
        admin = request_for({"ma_nguoi_dung": 1, "vai_tro": "Admin"})
        hr = request_for({"ma_nguoi_dung": 2, "vai_tro": "HR"})
        self.assertEqual(evaluation_routes.list_evaluations_for_hr_admin(admin, None, None, None, self.db)[0]["id"], created["id"])
        self.assertEqual(evaluation_routes.get_evaluation_for_hr_admin(created["id"], hr, self.db)["id"], created["id"])
        self.assert_http_error(403, lambda: evaluation_routes.update_mentor_evaluation(
            created["id"], InternEvaluationUpdate(initiative_score=2), admin, self.db))


if __name__ == "__main__":
    unittest.main()
