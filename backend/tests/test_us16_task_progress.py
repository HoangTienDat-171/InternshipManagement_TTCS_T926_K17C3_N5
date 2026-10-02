"""US16 progress, history, transaction, ownership, and concurrency regressions."""
import json
import math
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import database
from app.routes.task_routes import update_my_task_progress
from app.schemas import InternTaskProgressUpdate, MentorTaskCreate, MentorTaskUpdate
from app.task_service import InternshipTaskService


def request_for(user=None):
    return SimpleNamespace(state=SimpleNamespace(current_user=user))


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class TaskProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us16-", ignore_cleanup_errors=True)
        cls.db_path = Path(cls.temp_dir.name) / "us16.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()

        db = database.get_db_connection()
        mentor_rows = db.execute("""
            SELECT ma_nguoi_dung, ho_ten, vai_tro, email FROM NGUOI_DUNG
            WHERE email IN ('mentor@internship.vn', 'hai.dang.nguyen@internship.vn')
            ORDER BY email DESC
        """).fetchall()
        intern_rows = db.execute("""
            SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten, u.email, u.vai_tro
            FROM HO_SO_THUC_TAP h
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            WHERE u.email IN ('tuan.lm@internship.vn', 'minh.khoi.nguyen@internship.vn')
            ORDER BY u.email
        """).fetchall()
        if len(mentor_rows) != 2 or len(intern_rows) != 2:
            raise RuntimeError("US16 fixtures require two Mentors and two intern profiles.")
        cls.mentor_a, cls.mentor_b = map(dict, mentor_rows)
        cls.intern_a, cls.intern_b = map(dict, intern_rows)
        db.execute("DELETE FROM PHAN_CONG_MENTOR_TTS WHERE ma_ho_so IN (?, ?)", (
            cls.intern_a["ma_ho_so"], cls.intern_b["ma_ho_so"],
        ))
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
        self.db.execute("DELETE FROM LICH_SU_TIEN_DO_CONG_VIEC")
        self.db.execute("DELETE FROM NHIEM_VU_THUC_TAP")
        self.db.execute("DELETE FROM THONG_BAO WHERE loai = 'TASK_ASSIGNED'")
        self.db.commit()
        self.service = InternshipTaskService(self.db)

    def tearDown(self):
        self.db.close()

    def task_data(self, profile_id=None, title="US16 task"):
        return MentorTaskCreate(
            internship_profile_id=profile_id or self.intern_a["ma_ho_so"],
            title=title,
            description="Task progress test",
            due_date="2026-10-30",
            priority="MEDIUM",
        )

    def create_task(self, mentor=None, profile_id=None, title="US16 task"):
        return self.service.create_task(
            mentor or self.mentor_a,
            self.task_data(profile_id, title),
        )

    @staticmethod
    def progress(progress_percent, task_status="IN_PROGRESS", note=None):
        return InternTaskProgressUpdate(
            progress_percent=progress_percent,
            status=task_status,
            note=note,
        )

    def assert_http_error(self, code, callback):
        with self.assertRaises(HTTPException) as context:
            callback()
        self.assertEqual(context.exception.status_code, code)

    def test_progress_schema_boundaries_status_consistency_and_mass_assignment(self):
        self.assertEqual(self.progress(0, "TODO").progress_percent, 0)
        self.assertEqual(self.progress(100, "COMPLETED").progress_percent, 100)
        invalid = (
            {"progress_percent": -1, "status": "TODO"},
            {"progress_percent": 101, "status": "IN_PROGRESS"},
            {"progress_percent": "not-a-number", "status": "TODO"},
            {"progress_percent": math.nan, "status": "TODO"},
            {"progress_percent": 20, "status": "INVALID"},
            {"progress_percent": 100, "status": "IN_PROGRESS"},
            {"progress_percent": 80, "status": "COMPLETED"},
            {"progress_percent": 20, "status": "IN_PROGRESS", "title": "HACK"},
            {"progress_percent": 20, "status": "IN_PROGRESS", "mentor_id": 999},
            {"progress_percent": 20, "status": "IN_PROGRESS", "internship_profile_id": 999},
            {"progress_percent": 20, "status": "IN_PROGRESS", "updated_by": 999},
            {"progress_percent": 20, "status": "CANCELLED"},
        )
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                InternTaskProgressUpdate(**payload)

    def test_progress_history_tracks_old_new_actor_note_and_server_time(self):
        task = self.create_task()
        first = self.service.update_progress(
            task["id"], self.intern_a, self.progress(30, note="Hoàn thành API"),
        )
        second = self.service.update_progress(
            task["id"], self.intern_a, self.progress(60, note="Hoàn thành kiểm thử"),
        )
        history = self.service.get_progress_history(task["id"], self.intern_a)
        self.assertEqual((first["progress_percent"], second["progress_percent"]), (30, 60))
        self.assertEqual(len(history), 2)
        self.assertEqual((history[0]["old_progress"], history[0]["new_progress"]), (0, 30))
        self.assertEqual((history[1]["old_progress"], history[1]["new_progress"]), (30, 60))
        self.assertEqual(history[1]["updated_by"], self.intern_a["ma_nguoi_dung"])
        self.assertEqual(history[1]["note"], "Hoàn thành kiểm thử")
        self.assertTrue(history[1]["created_at"])

    def test_noop_does_not_create_history_but_note_only_change_does(self):
        task = self.create_task()
        self.service.update_progress(task["id"], self.intern_a, self.progress(20, note="Bắt đầu"))
        self.service.update_progress(task["id"], self.intern_a, self.progress(20, note="Bắt đầu"))
        self.assertEqual(len(self.service.get_progress_history(task["id"], self.intern_a)), 1)
        self.service.update_progress(task["id"], self.intern_a, self.progress(20, note="Đã bổ sung ghi chú"))
        history = self.service.get_progress_history(task["id"], self.intern_a)
        self.assertEqual(len(history), 2)
        self.assertEqual((history[1]["old_progress"], history[1]["new_progress"]), (20, 20))

    def test_state_machine_blocks_reopen_and_terminal_updates(self):
        task = self.create_task()
        self.service.update_progress(task["id"], self.intern_a, self.progress(40))
        self.assert_http_error(
            409,
            lambda: self.service.update_progress(task["id"], self.intern_a, self.progress(20, "TODO")),
        )
        completed = self.service.update_progress(task["id"], self.intern_a, self.progress(100, "COMPLETED"))
        self.assertEqual(completed["status"], "COMPLETED")
        self.assert_http_error(
            409,
            lambda: self.service.update_progress(task["id"], self.intern_a, self.progress(80)),
        )

        cancelled_task = self.create_task(title="Cancelled task")
        self.db.execute(
            "UPDATE NHIEM_VU_THUC_TAP SET trang_thai = 'CANCELLED' WHERE ma_nhiem_vu = ?",
            (cancelled_task["id"],),
        )
        self.db.commit()
        self.assert_http_error(
            409,
            lambda: self.service.update_progress(cancelled_task["id"], self.intern_a, self.progress(10)),
        )

    def test_ownership_and_mentor_history_scope_block_idor(self):
        task_a = self.create_task()
        task_b = self.create_task(self.mentor_b, self.intern_b["ma_ho_so"], "Task B")
        self.service.update_progress(task_a["id"], self.intern_a, self.progress(25))
        self.service.update_progress(task_b["id"], self.intern_b, self.progress(35))
        self.assert_http_error(
            403,
            lambda: self.service.update_progress(task_b["id"], self.intern_a, self.progress(50)),
        )
        self.assert_http_error(403, lambda: self.service.get_progress_history(task_b["id"], self.intern_a))
        self.assert_http_error(403, lambda: self.service.get_progress_history(task_b["id"], self.mentor_a))
        self.assertEqual(len(self.service.get_progress_history(task_a["id"], self.mentor_a)), 1)

    def test_reassigned_mentor_can_view_progress_but_cannot_manage_creators_task(self):
        task = self.create_task()
        self.service.update_progress(task["id"], self.intern_a, self.progress(25))
        try:
            self.db.execute("""
                UPDATE PHAN_CONG_MENTOR_TTS
                SET ma_nguoi_dung_mentor = ?
                WHERE ma_ho_so = ?
            """, (self.mentor_b["ma_nguoi_dung"], self.intern_a["ma_ho_so"]))
            self.db.commit()

            self.assertEqual(self.service.get_task(task["id"], self.mentor_b)["id"], task["id"])
            self.assertEqual(len(self.service.get_progress_history(task["id"], self.mentor_b)), 1)
            visible_ids = {row["id"] for row in self.service.list_mentor_tasks(self.mentor_b["ma_nguoi_dung"])}
            self.assertIn(task["id"], visible_ids)
            self.assert_http_error(
                403,
                lambda: self.service.update_task(
                    task["id"], self.mentor_b, MentorTaskUpdate(title="Không được sửa"),
                ),
            )
            self.assert_http_error(403, lambda: self.service.delete_task(task["id"], self.mentor_b))
            self.assert_http_error(403, lambda: self.service.get_task(task["id"], self.mentor_a))
        finally:
            self.db.execute("""
                UPDATE PHAN_CONG_MENTOR_TTS
                SET ma_nguoi_dung_mentor = ?
                WHERE ma_ho_so = ?
            """, (self.mentor_a["ma_nguoi_dung"], self.intern_a["ma_ho_so"]))
            self.db.commit()

    def test_progress_endpoint_requires_authenticated_intern(self):
        task = self.create_task()
        data = self.progress(10)
        self.assert_http_error(
            403,
            lambda: update_my_task_progress(task["id"], data, request_for(self.mentor_a), self.db),
        )
        self.assert_http_error(
            401,
            lambda: update_my_task_progress(task["id"], data, request_for(), self.db),
        )

    def test_history_insert_failure_rolls_back_task_update(self):
        task = self.create_task()
        with patch.object(self.service, "_insert_progress_history", side_effect=RuntimeError("history failed")):
            with self.assertRaisesRegex(RuntimeError, "history failed"):
                self.service.update_progress(task["id"], self.intern_a, self.progress(70))
        current = self.service.get_task(task["id"], self.intern_a)
        self.assertEqual((current["progress_percent"], current["status"]), (0, "TODO"))
        self.assertEqual(self.service.get_progress_history(task["id"], self.intern_a), [])

    def test_delete_after_progress_cancels_and_preserves_history(self):
        task = self.create_task()
        self.service.update_progress(task["id"], self.intern_a, self.progress(45, note="Đang làm"))
        self.service.delete_task(task["id"], self.mentor_a)
        current = self.service.get_task(task["id"], self.intern_a)
        history = self.service.get_progress_history(task["id"], self.intern_a)
        self.assertEqual(current["status"], "CANCELLED")
        self.assertEqual(history[-1]["new_status"], "CANCELLED")
        self.assertEqual(history[-1]["updated_by"], self.mentor_a["ma_nguoi_dung"])
        self.assert_http_error(
            409,
            lambda: self.service.update_progress(task["id"], self.intern_a, self.progress(50)),
        )

    def test_concurrent_service_updates_serialize_history_chain(self):
        for iteration in range(10):
            task = self.create_task(title=f"Concurrent service {iteration}")
            barrier = threading.Barrier(2)

            def update(value):
                connection = database.get_db_connection()
                try:
                    barrier.wait(timeout=5)
                    return InternshipTaskService(connection).update_progress(
                        task["id"], self.intern_a, self.progress(value),
                    )
                finally:
                    connection.close()

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(update, (30, 60)))
            history = self.service.get_progress_history(task["id"], self.intern_a)
            current = self.service.get_task(task["id"], self.intern_a)
            self.assertEqual(len(results), 2)
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["old_progress"], 0)
            self.assertEqual(history[1]["old_progress"], history[0]["new_progress"])
            self.assertEqual(current["progress_percent"], history[1]["new_progress"])

    def test_concurrent_http_updates_serialize_history_chain(self):
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment.update({
            "IMS_DATABASE_BACKEND": "sqlite",
            "IMS_SQLITE_PATH": str(self.db_path),
            "PYTHONIOENCODING": "utf-8",
            "SMTP_HOST": "",
            "SMTP_USERNAME": "",
            "SMTP_PASSWORD": "",
            "SMTP_FROM": "",
        })
        log_path = Path(self.temp_dir.name) / "us16-uvicorn.log"
        log_file = log_path.open("w", encoding="utf-8")
        backend_dir = Path(__file__).resolve().parents[1]
        server = subprocess.Popen(
            [str(backend_dir / ".venv" / "Scripts" / "python.exe"), "-m", "uvicorn",
             "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            cwd=backend_dir,
            env=environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

        def api(path, method="GET", token=None, data=None):
            body = json.dumps(data).encode("utf-8") if data is not None else None
            headers = {"Content-Type": "application/json"} if body is not None else {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            request = urllib.request.Request(base_url + path, data=body, method=method, headers=headers)
            try:
                response = urllib.request.urlopen(request, timeout=12)
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
            except urllib.error.HTTPError as error:
                raw = error.read()
                return error.code, json.loads(raw) if raw else None

        def login(email):
            code, response = api(
                "/api/auth/login", "POST", data={"email": email, "mat_khau": "123456"},
            )
            self.assertEqual(code, 200, response)
            return response["token"]

        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    log_file.flush()
                    self.fail(f"US16 test API exited during startup:\n{log_path.read_text(encoding='utf-8')}")
                try:
                    urllib.request.urlopen(base_url + "/", timeout=1).read()
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.2)
            else:
                self.fail("US16 test API did not start before timeout.")

            mentor_token = login(self.mentor_a["email"])
            intern_token = login(self.intern_a["email"])
            for iteration in range(5):
                create_payload = self.task_data(title=f"Concurrent HTTP {iteration}").model_dump(mode="json")
                code, task = api("/api/mentor/tasks", "POST", mentor_token, create_payload)
                self.assertEqual(code, 201, task)
                barrier = threading.Barrier(2)

                def update(value):
                    barrier.wait(timeout=5)
                    return api(
                        f"/api/interns/me/tasks/{task['id']}/progress",
                        "PATCH",
                        intern_token,
                        {"progress_percent": value, "status": "IN_PROGRESS", "note": f"HTTP {value}"},
                    )

                with ThreadPoolExecutor(max_workers=2) as executor:
                    responses = list(executor.map(update, (30, 60)))
                self.assertEqual([code for code, _ in responses], [200, 200])
                code, history = api(
                    f"/api/tasks/{task['id']}/progress-history", token=intern_token,
                )
                self.assertEqual(code, 200, history)
                self.assertEqual(len(history), 2)
                self.assertEqual(history[0]["old_progress"], 0)
                self.assertEqual(history[1]["old_progress"], history[0]["new_progress"])
                code, current = api(f"/api/tasks/{task['id']}", token=intern_token)
                self.assertEqual(code, 200, current)
                self.assertEqual(current["progress_percent"], history[1]["new_progress"])
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
            log_file.close()

    def test_history_schema_is_append_only_api_ready(self):
        task_columns = {row["name"]: row for row in self.db.execute("PRAGMA table_info(NHIEM_VU_THUC_TAP)")}
        self.assertEqual(task_columns["progress_percent"]["dflt_value"], "0")
        history_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(LICH_SU_TIEN_DO_CONG_VIEC)")}
        self.assertTrue({
            "ma_lich_su", "ma_nhiem_vu", "updated_by", "old_progress", "new_progress",
            "old_status", "new_status", "note", "created_at",
        }.issubset(history_columns))
        index_names = {row["name"] for row in self.db.execute("PRAGMA index_list(LICH_SU_TIEN_DO_CONG_VIEC)")}
        self.assertIn("idx_task_progress_history", index_names)
        self.assertIn("idx_task_progress_actor", index_names)


if __name__ == "__main__":
    unittest.main()
