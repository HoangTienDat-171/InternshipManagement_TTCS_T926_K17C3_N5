import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import database
from app.routes import work_shift_routes
from app.schemas import WorkShiftCreate, WorkShiftUpdate
from app.work_shift_service import WorkShiftService, _time_text, resolve_applicable_shifts


def request_for(user=None):
    return SimpleNamespace(state=SimpleNamespace(current_user=user))


class WorkShiftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us23-")
        cls.db_path = Path(cls.temp_dir.name) / "us23.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()
        db = database.get_db_connection()
        cls.admin = dict(db.execute("SELECT ma_nguoi_dung, vai_tro FROM NGUOI_DUNG WHERE vai_tro='Admin' ORDER BY ma_nguoi_dung LIMIT 1").fetchone())
        cls.hr = dict(db.execute("SELECT ma_nguoi_dung, vai_tro FROM NGUOI_DUNG WHERE vai_tro='HR' ORDER BY ma_nguoi_dung LIMIT 1").fetchone())
        cls.mentor = dict(db.execute("SELECT ma_nguoi_dung, vai_tro FROM NGUOI_DUNG WHERE vai_tro='Mentor' ORDER BY ma_nguoi_dung LIMIT 1").fetchone())
        cls.program_ids = [row["ma_chuong_trinh"] for row in db.execute(
            "SELECT ma_chuong_trinh FROM CHUONG_TRINH_THUC_TAP ORDER BY ma_chuong_trinh LIMIT 2"
        ).fetchall()]
        if len(cls.program_ids) < 2:
            department_id = db.execute("SELECT ma_phong_ban FROM PHONG_BAN ORDER BY ma_phong_ban LIMIT 1").fetchone()[0]
            for index in range(2 - len(cls.program_ids)):
                cursor = db.execute("""
                    INSERT INTO CHUONG_TRINH_THUC_TAP
                        (ma_ct, ten_ct, ma_phong_ban, chi_tieu)
                    VALUES (?, ?, ?, 1)
                """, (f"US23-{index}-{cls.db_path.stem}", f"US23 Program {index}", department_id))
                cls.program_ids.append(cursor.lastrowid)
            db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()
        self.db.execute("DELETE FROM CA_LAM_VIEC")
        self.db.commit()
        self.service = WorkShiftService(self.db)

    def tearDown(self):
        self.db.close()

    def values(self, **changes):
        data = {
            "name": "  Ca sáng  ",
            "start_time": "08:00",
            "end_time": "12:00",
            "scope_type": "GLOBAL",
            "program_id": None,
            "effective_from": "2026-10-05",
            "effective_to": "2026-10-30",
            "status": "ACTIVE",
        }
        data.update(changes)
        return WorkShiftCreate(**data)

    def create(self, **changes):
        return self.service.create_shift(self.values(**changes).model_dump(), self.admin["ma_nguoi_dung"])

    def assert_http_error(self, status_code, callback):
        with self.assertRaises(HTTPException) as context:
            callback()
        self.assertEqual(context.exception.status_code, status_code)

    def test_schema_rejects_overnight_invalid_dates_wrong_scope_and_client_actor(self):
        with self.assertRaises(ValidationError):
            self.values(start_time="22:00", end_time="06:00")
        with self.assertRaises(ValidationError):
            self.values(start_time="08:00+07:00")
        with self.assertRaises(ValidationError):
            self.values(effective_from="2026-10-30", effective_to="2026-10-05")
        with self.assertRaises(ValidationError):
            self.values(scope_type="PROGRAM", program_id=None)
        with self.assertRaises(ValidationError):
            self.values(created_by=self.admin["ma_nguoi_dung"])
        with self.assertRaises(ValidationError):
            WorkShiftUpdate(status=None)

    def test_mysql_time_values_are_serialized_without_losing_leading_zero(self):
        self.assertEqual(_time_text(timedelta(hours=8, minutes=5)), "08:05:00")

    def test_time_windows_are_half_open_and_adjacent_shifts_are_allowed(self):
        first = self.create()
        second = self.create(name="Ca chiều", start_time="12:00", end_time="17:00")
        self.assertEqual(first["start_time"], "08:00:00")
        self.assertEqual(second["start_time"], "12:00:00")
        self.assertEqual(self.service.list_shifts(), [first, second])

    def test_overlaps_conflict_only_in_same_scope_and_on_intersecting_dates(self):
        self.create()
        self.assert_http_error(409, lambda: self.create(name="Ca trùng", start_time="11:59", end_time="13:00"))
        self.assert_http_error(409, lambda: self.create(name="Ngày chạm", effective_from="2026-10-30", effective_to="2026-11-02"))
        self.create(name="Sau ngày hiệu lực", effective_from="2026-10-31", effective_to=None)
        program_id, other_program_id = self.program_ids
        program_shift = self.create(name="Ca chương trình A", scope_type="PROGRAM", program_id=program_id)
        self.create(name="Ca chương trình B", scope_type="PROGRAM", program_id=other_program_id)
        self.assertEqual(program_shift["program_id"], program_id)

    def test_inactive_shift_does_not_block_active_configuration(self):
        self.create(status="INACTIVE")
        active = self.create(name="Ca đang dùng")
        self.assertEqual(active["status"], "ACTIVE")

    def test_update_rechecks_overlap_excludes_self_and_deactivation_is_allowed(self):
        first = self.create()
        second = self.create(name="Ca chiều", start_time="12:00", end_time="17:00")
        self.assertEqual(self.service.update_shift(first["id"], {"name": "Ca sáng mới"})["name"], "Ca sáng mới")
        self.assert_http_error(409, lambda: self.service.update_shift(second["id"], {"start_time": "11:00"}))
        inactive = self.service.update_shift(first["id"], {"status": "INACTIVE"})
        self.assertEqual(inactive["status"], "INACTIVE")

    def test_program_resolution_overrides_global_then_falls_back(self):
        self.create(name="Global morning")
        program_id, other_program_id = self.program_ids
        self.create(name="Program A morning", scope_type="PROGRAM", program_id=program_id)
        self.create(name="Program B morning", scope_type="PROGRAM", program_id=other_program_id)
        program_result = resolve_applicable_shifts(self.db, program_id, date(2026, 10, 10))
        other_result = resolve_applicable_shifts(self.db, other_program_id, date(2026, 10, 10))
        self.assertEqual([item["name"] for item in program_result], ["Program A morning"])
        self.assertEqual([item["name"] for item in other_result], ["Program B morning"])
        self.db.execute("UPDATE CA_LAM_VIEC SET status='INACTIVE' WHERE scope_type='PROGRAM' AND ma_chuong_trinh=?", (program_id,))
        self.db.commit()
        self.assertEqual([item["name"] for item in resolve_applicable_shifts(self.db, program_id, date(2026, 10, 10))], ["Global morning"])
        self.assertEqual(resolve_applicable_shifts(self.db, program_id, date(2026, 12, 1)), [])

    def test_list_filters_status_scope_program_and_effective_date(self):
        global_shift = self.create()
        program_shift = self.create(name="Program shift", scope_type="PROGRAM", program_id=self.program_ids[0])
        program_code = self.db.execute(
            "SELECT ma_ct FROM CHUONG_TRINH_THUC_TAP WHERE ma_chuong_trinh = ?",
            (self.program_ids[0],),
        ).fetchone()[0]
        self.service.update_shift(global_shift["id"], {"status": "INACTIVE"})
        program_rows = self.service.list_shifts(status="ACTIVE", scope_type="PROGRAM", program_id=self.program_ids[0])
        self.assertEqual([row["id"] for row in program_rows], [program_shift["id"]])
        self.assertEqual(program_rows[0]["program_code"], program_code)
        self.assertEqual(self.service.list_shifts(effective_date=date(2026, 12, 1)), [])

    def test_route_enforces_hr_admin_and_records_authenticated_creator(self):
        payload = self.values()
        created = work_shift_routes.create_work_shift(payload, request_for(self.hr), self.db)
        self.assertEqual(created["created_by"], self.hr["ma_nguoi_dung"])
        self.assert_http_error(403, lambda: work_shift_routes.list_work_shifts(request_for(self.mentor), db=self.db))
        self.assert_http_error(401, lambda: work_shift_routes.list_work_shifts(request_for(), db=self.db))
        self.assert_http_error(403, lambda: work_shift_routes.create_work_shift(payload, request_for(self.mentor), self.db))

    def test_concurrent_overlapping_creates_cannot_both_succeed(self):
        barrier = Barrier(2)

        def attempt(name):
            conn = database.get_db_connection()
            try:
                barrier.wait(timeout=3)
                return WorkShiftService(conn).create_shift(
                    self.values(name=name).model_dump(), self.admin["ma_nguoi_dung"],
                )
            except HTTPException as exc:
                return exc.status_code
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ("Concurrent A", "Concurrent B")))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual([result for result in results if isinstance(result, int)], [409])
        count = self.db.execute("SELECT COUNT(*) FROM CA_LAM_VIEC WHERE status='ACTIVE'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_database_constraints_reject_invalid_scope_and_time(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("""
                INSERT INTO CA_LAM_VIEC
                    (name, start_time, end_time, scope_type, ma_chuong_trinh,
                     effective_from, status, created_by)
                VALUES ('Invalid', '18:00', '09:00', 'GLOBAL', ?, '2026-10-05', 'ACTIVE', ?)
            """, (self.program_ids[0], self.admin["ma_nguoi_dung"]))


if __name__ == "__main__":
    unittest.main()
