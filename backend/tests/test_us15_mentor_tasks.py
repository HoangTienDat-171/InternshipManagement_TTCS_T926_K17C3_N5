"""US15 task authorization and CRUD regressions on a disposable SQLite database."""
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import database
from app.routes.task_routes import create_mentor_task, delete_mentor_task
from app.schemas import MentorTaskCreate, MentorTaskUpdate
from app.task_service import InternshipTaskService


def request_for(user=None):
    return SimpleNamespace(state=SimpleNamespace(current_user=user))


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class MentorTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us15-", ignore_cleanup_errors=True)
        cls.db_path = Path(cls.temp_dir.name) / "us15.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()

        db = database.get_db_connection()
        mentor_a = db.execute(
            "SELECT ma_nguoi_dung, ho_ten, vai_tro FROM NGUOI_DUNG WHERE email = ?",
            ("mentor@internship.vn",),
        ).fetchone()
        mentor_b = db.execute(
            "SELECT ma_nguoi_dung, ho_ten, vai_tro FROM NGUOI_DUNG WHERE email = ?",
            ("hai.dang.nguyen@internship.vn",),
        ).fetchone()
        intern_rows = db.execute("""
            SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten
            FROM HO_SO_THUC_TAP h
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            WHERE u.email IN ('tuan.lm@internship.vn', 'minh.khoi.nguyen@internship.vn')
            ORDER BY u.email
        """).fetchall()
        if len(intern_rows) != 2:
            raise RuntimeError("US15 fixtures require two seeded intern profiles.")
        cls.mentor_a = dict(mentor_a)
        cls.mentor_b = dict(mentor_b)
        cls.intern_a = dict(intern_rows[0])
        cls.intern_b = dict(intern_rows[1])
        cls.intern_a_actor = {
            "ma_nguoi_dung": cls.intern_a["ma_nguoi_dung"],
            "ho_ten": cls.intern_a["ho_ten"],
            "vai_tro": "ThucTapSinh",
        }
        cls.intern_b_actor = {
            "ma_nguoi_dung": cls.intern_b["ma_nguoi_dung"],
            "ho_ten": cls.intern_b["ho_ten"],
            "vai_tro": "ThucTapSinh",
        }
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
        self.db.execute("DELETE FROM NHIEM_VU_THUC_TAP")
        self.db.execute("DELETE FROM THONG_BAO WHERE loai = 'TASK_ASSIGNED'")
        self.db.commit()
        self.service = InternshipTaskService(self.db)

    def tearDown(self):
        self.db.close()

    def task_data(self, profile_id=None, **overrides):
        values = {
            "internship_profile_id": profile_id or self.intern_a["ma_ho_so"],
            "title": "  Hoàn thiện API đăng nhập  ",
            "description": "  Kiểm tra và viết tài liệu  ",
            "due_date": "2026-10-20",
            "priority": "HIGH",
        }
        values.update(overrides)
        return MentorTaskCreate(**values)

    def create_task(self, mentor=None, profile_id=None, **overrides):
        return self.service.create_task(
            mentor or self.mentor_a,
            self.task_data(profile_id, **overrides),
        )

    def assert_http_error(self, code, callback):
        with self.assertRaises(HTTPException) as context:
            callback()
        self.assertEqual(context.exception.status_code, code)

    def test_create_uses_authenticated_mentor_assignment_and_initial_status(self):
        task = self.create_task()
        self.assertEqual(task["mentor_id"], self.mentor_a["ma_nguoi_dung"])
        self.assertEqual(task["internship_profile_id"], self.intern_a["ma_ho_so"])
        self.assertEqual(task["title"], "Hoàn thiện API đăng nhập")
        self.assertEqual(task["description"], "Kiểm tra và viết tài liệu")
        self.assertEqual(task["status"], "TODO")
        notification = self.db.execute("""
            SELECT ma_nguoi_dung, reference_id FROM THONG_BAO
            WHERE loai = 'TASK_ASSIGNED'
        """).fetchone()
        self.assertEqual(notification["ma_nguoi_dung"], self.intern_a["ma_nguoi_dung"])
        self.assertEqual(notification["reference_id"], str(task["id"]))

    def test_create_blocks_other_mentor_intern_and_missing_profile(self):
        self.assert_http_error(
            403,
            lambda: self.create_task(profile_id=self.intern_b["ma_ho_so"]),
        )
        self.assert_http_error(404, lambda: self.create_task(profile_id=999999))

    def test_create_endpoint_requires_mentor_and_authenticated_user(self):
        payload = self.task_data()
        self.assert_http_error(
            403,
            lambda: create_mentor_task(payload, request_for(self.intern_a_actor), self.db),
        )
        self.assert_http_error(
            401,
            lambda: create_mentor_task(payload, request_for(), self.db),
        )

    def test_create_schema_rejects_invalid_and_protected_fields(self):
        invalid_payloads = (
            {"title": "   "},
            {"priority": "CRITICAL"},
            {"due_date": "not-a-date"},
            {"mentorId": 999},
            {"status": "COMPLETED"},
            {"progressPercent": 100},
            {"createdAt": "2020-01-01"},
        )
        base = self.task_data().model_dump(mode="json")
        for values in invalid_payloads:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                MentorTaskCreate(**{**base, **values})

    def test_lists_are_scoped_to_authenticated_actor(self):
        task_a = self.create_task()
        task_b = self.create_task(self.mentor_b, self.intern_b["ma_ho_so"], title="Task B")
        mentor_rows = self.service.list_mentor_tasks(self.mentor_a["ma_nguoi_dung"])
        intern_rows = self.service.list_intern_tasks(self.intern_a["ma_nguoi_dung"])
        self.assertEqual([row["id"] for row in mentor_rows], [task_a["id"]])
        self.assertEqual([row["id"] for row in intern_rows], [task_a["id"]])
        self.assertNotEqual(task_a["id"], task_b["id"])

    def test_detail_blocks_mentor_and_intern_idor(self):
        task_a = self.create_task()
        task_b = self.create_task(self.mentor_b, self.intern_b["ma_ho_so"], title="Task B")
        self.assertEqual(self.service.get_task(task_a["id"], self.mentor_a)["id"], task_a["id"])
        self.assertEqual(self.service.get_task(task_a["id"], self.intern_a_actor)["id"], task_a["id"])
        self.assert_http_error(403, lambda: self.service.get_task(task_b["id"], self.mentor_a))
        self.assert_http_error(403, lambda: self.service.get_task(task_b["id"], self.intern_a_actor))

    def test_mentor_update_changes_only_owned_mentor_fields(self):
        task = self.create_task()
        updated = self.service.update_task(
            task["id"],
            self.mentor_a,
            MentorTaskUpdate(title="Tiêu đề mới", due_date="2026-10-25", priority="URGENT"),
        )
        self.assertEqual((updated["title"], updated["due_date"], updated["priority"]), (
            "Tiêu đề mới", "2026-10-25", "URGENT",
        ))
        self.assertEqual(updated["status"], "TODO")
        for protected in ({"mentorId": 5}, {"progressPercent": 50}, {"status": "COMPLETED"}):
            with self.assertRaises(ValidationError):
                MentorTaskUpdate(**protected)
        self.assert_http_error(
            403,
            lambda: self.service.update_task(task["id"], self.mentor_b, MentorTaskUpdate(title="Chiếm quyền")),
        )

    def test_delete_is_owner_only_and_preserves_scope(self):
        task = self.create_task()
        self.assert_http_error(403, lambda: self.service.delete_task(task["id"], self.mentor_b))
        response = delete_mentor_task(task["id"], request_for(self.mentor_a), self.db)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.db.execute(
            "SELECT 1 FROM NHIEM_VU_THUC_TAP WHERE ma_nhiem_vu = ?", (task["id"],),
        ).fetchone())

    def test_xss_like_text_is_stored_as_plain_data(self):
        task = self.create_task(
            title="<script>alert(1)</script>",
            description='<img src=x onerror="alert(1)">',
        )
        self.assertEqual(task["title"], "<script>alert(1)</script>")
        self.assertEqual(task["description"], '<img src=x onerror="alert(1)">')

    def test_schema_has_stable_primary_key_and_future_safe_foreign_keys(self):
        columns = {row["name"]: row for row in self.db.execute("PRAGMA table_info(NHIEM_VU_THUC_TAP)")}
        self.assertEqual(columns["ma_nhiem_vu"]["pk"], 1)
        foreign_keys = self.db.execute("PRAGMA foreign_key_list(NHIEM_VU_THUC_TAP)").fetchall()
        self.assertEqual({row["table"] for row in foreign_keys}, {"HO_SO_THUC_TAP", "NGUOI_DUNG"})
        self.assertTrue(all(row["on_delete"] == "RESTRICT" for row in foreign_keys))

    def test_http_full_flow_enforces_auth_scope_and_protected_payload(self):
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
        log_path = Path(self.temp_dir.name) / "us15-uvicorn.log"
        log_file = log_path.open("w", encoding="utf-8")
        server = subprocess.Popen(
            [str(Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "python.exe"),
             "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
             "--log-level", "warning"],
            cwd=Path(__file__).resolve().parents[1],
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
                    self.fail(f"US15 test API exited during startup:\n{log_path.read_text(encoding='utf-8')}")
                try:
                    urllib.request.urlopen(base_url + "/", timeout=1).read()
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.2)
            else:
                self.fail("US15 test API did not start before timeout.")

            mentor_a_token = login("mentor@internship.vn")
            mentor_b_token = login("hai.dang.nguyen@internship.vn")
            intern_a_email = self.db.execute(
                "SELECT email FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?",
                (self.intern_a["ma_nguoi_dung"],),
            ).fetchone()[0]
            intern_b_email = self.db.execute(
                "SELECT email FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?",
                (self.intern_b["ma_nguoi_dung"],),
            ).fetchone()[0]
            intern_a_token = login(intern_a_email)
            intern_b_token = login(intern_b_email)
            payload = self.task_data().model_dump(mode="json")

            code, _ = api("/api/mentor/tasks", "POST", data=payload)
            self.assertEqual(code, 401)
            code, _ = api("/api/mentor/tasks", "POST", intern_a_token, payload)
            self.assertEqual(code, 403)
            code, _ = api(
                "/api/mentor/tasks", "POST", mentor_a_token,
                {**payload, "mentorId": self.mentor_b["ma_nguoi_dung"]},
            )
            self.assertEqual(code, 422)

            code, task = api("/api/mentor/tasks", "POST", mentor_a_token, payload)
            self.assertEqual(code, 201, task)
            self.assertEqual(task["mentor_id"], self.mentor_a["ma_nguoi_dung"])
            code, tasks = api("/api/interns/me/tasks", token=intern_a_token)
            self.assertEqual(code, 200, tasks)
            self.assertEqual([item["id"] for item in tasks], [task["id"]])
            code, _ = api(f"/api/tasks/{task['id']}", token=intern_b_token)
            self.assertEqual(code, 403)
            code, updated = api(
                f"/api/mentor/tasks/{task['id']}", "PUT", mentor_a_token,
                {"priority": "URGENT", "due_date": "2026-10-28"},
            )
            self.assertEqual(code, 200, updated)
            self.assertEqual(updated["priority"], "URGENT")
            code, _ = api(f"/api/mentor/tasks/{task['id']}", "DELETE", mentor_b_token)
            self.assertEqual(code, 403)
            code, _ = api(f"/api/mentor/tasks/{task['id']}", "DELETE", mentor_a_token)
            self.assertEqual(code, 204)
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
            log_file.close()


if __name__ == "__main__":
    unittest.main()
