"""Focused Sprint 1 API regressions using a disposable SQLite database."""
import base64
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
PDF = b"%PDF-1.4\nSprint 1 API test\n%%EOF\n"


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class WebSocketClient:
    """Small test-only RFC 6455 client for the server's text event frame."""

    def __init__(self, url):
        parsed = urllib.parse.urlsplit(url)
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=4)
        self.socket.settimeout(4)
        self.buffer = b""
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path + "?" + parsed.query
        self.socket.sendall((
            f"GET {path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii"))
        while b"\r\n\r\n" not in self.buffer:
            self.buffer += self.socket.recv(4096)
        headers, self.buffer = self.buffer.split(b"\r\n\r\n", 1)
        if b" 101 " not in headers:
            raise AssertionError(f"WebSocket handshake failed: {headers!r}; body={self.buffer!r}")

    def receive_json(self):
        while len(self.buffer) < 2:
            self.buffer += self.socket.recv(4096)
        first, second = self.buffer[0], self.buffer[1]
        self.buffer = self.buffer[2:]
        length = second & 0x7F
        if length == 126:
            while len(self.buffer) < 2:
                self.buffer += self.socket.recv(4096)
            length = int.from_bytes(self.buffer[:2], "big")
            self.buffer = self.buffer[2:]
        elif length == 127:
            while len(self.buffer) < 8:
                self.buffer += self.socket.recv(4096)
            length = int.from_bytes(self.buffer[:8], "big")
            self.buffer = self.buffer[8:]
        mask = None
        if second & 0x80:
            while len(self.buffer) < 4:
                self.buffer += self.socket.recv(4096)
            mask, self.buffer = self.buffer[:4], self.buffer[4:]
        while len(self.buffer) < length:
            self.buffer += self.socket.recv(4096)
        payload, self.buffer = self.buffer[:length], self.buffer[length:]
        if mask:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        if first & 0x0F != 1:
            raise AssertionError(f"Expected a WebSocket text event, received opcode {first & 0x0F}")
        return json.loads(payload)

    def close(self):
        self.socket.close()


class Sprint1RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PYTHON.is_file():
            raise RuntimeError(f"Backend virtualenv Python not found: {PYTHON}")
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-sprint1-", ignore_cleanup_errors=True)
        cls.temp_path = Path(cls.temp_dir.name)
        cls.db_path = cls.temp_path / "sprint1-test.sqlite3"
        cls.port = free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        environment = os.environ.copy()
        environment["IMS_DATABASE_BACKEND"] = "sqlite"
        environment["IMS_SQLITE_PATH"] = str(cls.db_path)
        environment["PYTHONIOENCODING"] = "utf-8"
        cls.log_path = cls.temp_path / "uvicorn.log"
        cls.log_file = cls.log_path.open("w", encoding="utf-8")
        cls.server = subprocess.Popen(
            [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=BACKEND, env=environment, stdout=cls.log_file, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                cls.log_file.flush()
                raise RuntimeError(f"Test API exited during startup:\n{cls.log_path.read_text(encoding='utf-8')}")
            try:
                urllib.request.urlopen(cls.base_url + "/", timeout=1).read()
                break
            except (OSError, urllib.error.URLError):
                time.sleep(0.25)
        else:
            cls.server.terminate()
            raise RuntimeError(f"Test API did not start:\n{cls.log_path.read_text(encoding='utf-8')}")

        # More than one page of deterministic records, inserted only into the disposable DB.
        db = sqlite3.connect(cls.db_path)
        try:
            for index in range(15):
                email = f"pagination.case{index:02d}@test.invalid"
                cursor = db.execute("""
                    INSERT INTO NGUOI_DUNG
                        (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
                    VALUES (1, ?, ?, 'unused-test-hash', 'ThucTapSinh', 'HoatDong')
                """, (f"Pagination Test {index:02d}", email))
                db.execute("""
                    INSERT INTO HO_SO_THUC_TAP
                        (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
                    VALUES (?, 1, 'Regression QA', 'DaDuyet', 'DangThucTap')
                """, (cursor.lastrowid,))
            db.commit()
        finally:
            db.close()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server", None) and cls.server.poll() is None:
            cls.server.terminate()
            try:
                cls.server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                cls.server.kill()
                cls.server.wait(timeout=5)
        if getattr(cls, "log_file", None):
            cls.log_file.close()
        if getattr(cls, "temp_dir", None):
            for attempt in range(20):
                try:
                    cls.temp_dir.cleanup()
                    break
                except PermissionError:
                    if attempt == 19:
                        break
                    time.sleep(0.2)

    def request(self, path, method="GET", token=None, body=None, content_type=None, headers=None):
        request_headers = dict(headers or {})
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        if content_type:
            request_headers["Content-Type"] = content_type
        request = urllib.request.Request(self.base_url + path, data=body, method=method, headers=request_headers)
        try:
            response = urllib.request.urlopen(request, timeout=12)
            return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def json_request(self, path, method="GET", token=None, data=None, headers=None):
        body = json.dumps(data).encode("utf-8") if data is not None else None
        status_code, raw, headers = self.request(
            path, method, token, body,
            "application/json" if body is not None else None,
            headers=headers,
        )
        return status_code, json.loads(raw) if raw else None, headers

    def login(self, email):
        status_code, response, _ = self.json_request(
            "/api/auth/login", "POST", data={"email": email, "mat_khau": "123456"},
        )
        self.assertEqual(status_code, 200, response)
        return response["token"], response["user"]

    def upload(self, token, filename, document_type, content, profile_id=None):
        boundary = "----Sprint1Boundary7MA4YWxkTrZu0gW"
        parts = []
        if profile_id is not None:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"ma_ho_so\"\r\n\r\n{profile_id}\r\n".encode())
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"loai_tai_lieu\"\r\n\r\n{document_type}\r\n".encode())
        parts.append((
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            "Content-Type: application/pdf\r\n\r\n"
        ).encode() + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return self.request(
            "/api/documents", "POST", token, b"".join(parts),
            f"multipart/form-data; boundary={boundary}",
        )

    def test_search_filters_and_server_pagination(self):
        token, _ = self.login("admin@internship.vn")
        status_code, response, _ = self.json_request("/api/interns?page=1&pageSize=5&search=pagination.case", token=token)
        self.assertEqual(status_code, 200)
        self.assertEqual((response["page"], response["pageSize"], response["totalItems"], response["totalPages"]), (1, 5, 15, 3))
        self.assertEqual(len(response["items"]), 5)

        status_code, response, _ = self.json_request(
            "/api/interns?page=2&pageSize=5&search=pagination.case&trang_thai_xet_duyet=DaDuyet&ma_truong=1",
            token=token,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual((response["page"], response["totalItems"], response["totalPages"], len(response["items"])), (2, 15, 3, 5))
        self.assertTrue(all(row["trang_thai_xet_duyet"] == "DaDuyet" for row in response["items"]))

        status_code, response, _ = self.json_request("/api/interns?page=99&pageSize=5&search=pagination.case", token=token)
        self.assertEqual(status_code, 200)
        self.assertEqual((response["page"], len(response["items"])), (3, 5))
        status_code, response, _ = self.json_request("/api/interns?pageSize=0", token=token)
        self.assertEqual(status_code, 422, response)
        status_code, response, _ = self.json_request("/api/interns?search=does-not-exist", token=token)
        self.assertEqual(status_code, 200)
        self.assertEqual((response["totalItems"], response["totalPages"], response["page"], response["items"]), (0, 0, 1, []))

    def test_all_management_tables_paginate_and_preserve_legacy_list_responses(self):
        token, _ = self.login("admin@internship.vn")
        db = sqlite3.connect(self.db_path)
        try:
            profiles = [row[0] for row in db.execute("""
                SELECT h.ma_ho_so
                FROM HO_SO_THUC_TAP h
                JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
                WHERE u.email LIKE 'pagination.case%'
                ORDER BY h.ma_ho_so
                LIMIT 12
            """).fetchall()]
            self.assertEqual(len(profiles), 12)

            for index in range(12):
                cursor = db.execute("""
                    INSERT INTO NGUOI_DUNG
                        (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
                    VALUES (1, ?, ?, 'unused-test-hash', 'Mentor', 'HoatDong')
                """, (f"Page Mentor {index:02d}", f"page.mentor{index:02d}@test.invalid"))
                db.execute("""
                    INSERT INTO MENTOR_PROFILE
                        (ma_nguoi_dung, chuyen_mon, kinh_nghiem, so_tts_toi_da)
                    VALUES (?, 'Pagination QA', 5, 3)
                """, (cursor.lastrowid,))

            program_ids = []
            for index in range(12):
                cursor = db.execute("""
                    INSERT INTO CHUONG_TRINH_THUC_TAP
                        (ma_ct, ten_ct, ma_phong_ban, chi_tieu, trang_thai)
                    VALUES (?, ?, 1, 5, 'DangMo')
                """, (f"PAGINATION-{index:02d}", f"Page Program {index:02d}"))
                program_ids.append(cursor.lastrowid)
                db.execute("""
                    INSERT INTO TAI_LIEU_HO_SO
                        (ma_ho_so, loai_tai_lieu, duong_dan_file, trang_thai_duyet, ten_file, kich_thuoc)
                    VALUES (?, 'CV', ?, 'ChoDuyet', ?, 128)
                """, (profiles[index], f"/test/page-{index:02d}.pdf", f"page-{index:02d}.pdf"))
                db.execute("""
                    INSERT INTO UNG_TUYEN_CHUONG_TRINH
                        (ma_chuong_trinh, ma_ho_so, trang_thai)
                    VALUES (?, ?, ?)
                """, (program_ids[0], profiles[index], 'ChoDuyet' if index % 2 == 0 else 'DaDuyet'))
            db.execute("""
                INSERT INTO CHUONG_TRINH_THUC_TAP
                    (ma_ct, ten_ct, ma_phong_ban, chi_tieu, trang_thai)
                VALUES ('PAGINATION-PAUSED', 'Paused Program', 1, 5, 'TamDung')
            """)
            db.commit()
        finally:
            db.close()

        queries = (
            ("/api/auth/users?vai_tro=Mentor&page=2&pageSize=5", "Admin", "ho_ten"),
            ("/api/mentors?page=2&pageSize=5", "Admin", "ho_ten"),
            ("/api/programs?page=2&pageSize=5", "Admin", "ma_ct"),
            ("/api/documents?page=2&pageSize=5", "Admin", "ten_file"),
            (f"/api/programs/{program_ids[0]}/applications?page=2&pageSize=5", "Admin", "ma_ung_tuyen"),
        )
        for path, _, row_key in queries:
            with self.subTest(path=path):
                status_code, response, _ = self.json_request(path, token=token)
                self.assertEqual(status_code, 200, response)
                self.assertIsInstance(response["items"], list)
                self.assertEqual((response["page"], response["pageSize"], len(response["items"])), (2, 5, 5))
                self.assertGreaterEqual(response["totalItems"], 12 if "applications" in path else 12)
                self.assertGreaterEqual(response["totalPages"], 3)
                self.assertIn(row_key, response["items"][0])

        status_code, clamped, _ = self.json_request(
            f"/api/programs/{program_ids[0]}/applications?page=99&pageSize=5", token=token,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual((clamped["page"], len(clamped["items"])), (clamped["totalPages"], 2))

        intern_token, _ = self.login("tuan.lm@internship.vn")
        status_code, open_programs, _ = self.json_request(
            "/api/programs?page=1&pageSize=5", token=intern_token,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual((open_programs["totalItems"], open_programs["totalPages"]), (12, 3))
        self.assertTrue(all(program["trang_thai"] == "DangMo" for program in open_programs["items"]))

        # Existing integrations that omit pagination arguments continue receiving arrays.
        for path in (
            "/api/auth/users", "/api/mentors", "/api/programs", "/api/documents",
            f"/api/programs/{program_ids[0]}/applications",
        ):
            status_code, response, _ = self.json_request(path, token=token)
            self.assertEqual(status_code, 200, response)
            self.assertIsInstance(response, list, path)

    def test_intern_mentor_and_program_create_update(self):
        token, _ = self.login("admin@internship.vn")
        suffix = str(time.time_ns())
        status_code, created, _ = self.json_request("/api/interns", "POST", token, {
            "ho_ten": "Sprint 1 CRUD Intern", "email": f"sprint1.{suffix}@test.invalid",
            "ma_phong_ban": 1, "ma_truong": 1, "chuyen_nganh": "Backend",
            "trang_thai_xet_duyet": "ChoDuyet", "trang_thai_thuc_tap": "DangThucTap",
        })
        self.assertEqual(status_code, 201, created)
        profile_id = created["ma_ho_so"]
        status_code, detail, _ = self.json_request(f"/api/interns/{profile_id}", token=token)
        self.assertEqual((status_code, detail["email"]), (200, f"sprint1.{suffix}@test.invalid"))
        status_code, updated, _ = self.json_request(f"/api/interns/{profile_id}", "PUT", token, {
            "ho_ten": "Sprint 1 CRUD Intern Updated", "email": f"sprint1.{suffix}@test.invalid",
            "ma_phong_ban": 2, "ma_truong": 2, "chuyen_nganh": "Data Engineering",
            "trang_thai_xet_duyet": "ChoDuyet", "trang_thai_thuc_tap": "DangThucTap",
        })
        self.assertEqual(status_code, 200, updated)
        status_code, detail, _ = self.json_request(f"/api/interns/{profile_id}", token=token)
        self.assertEqual((status_code, detail["chuyen_nganh"], detail["ma_truong"]), (200, "Data Engineering", 2))

        mentor_email = f"sprint1.mentor.{suffix}@test.invalid"
        status_code, mentor, _ = self.json_request("/api/mentors", "POST", token, {
            "ho_ten": "Sprint 1 CRUD Mentor", "email": mentor_email, "mat_khau": "123456",
            "ma_phong_ban": 1, "chuyen_mon": "Python", "kinh_nghiem": 4, "so_tts_toi_da": 2,
        })
        self.assertEqual(status_code, 201, mentor)
        mentor_id = mentor["ma_nguoi_dung"]
        status_code, _, _ = self.json_request(f"/api/mentors/{mentor_id}/profile", "PUT", token, {
            "chuyen_mon": "Python, FastAPI", "kinh_nghiem": 5, "so_tts_toi_da": 3,
        })
        self.assertEqual(status_code, 200)
        status_code, mentor_rows, _ = self.json_request("/api/mentors", token=token)
        self.assertEqual(status_code, 200)
        saved_mentor = next(row for row in mentor_rows if row["ma_nguoi_dung"] == mentor_id)
        self.assertEqual((saved_mentor["chuyen_mon"], saved_mentor["kinh_nghiem"], saved_mentor["so_tts_toi_da"]), ("Python, FastAPI", 5, 3))

        code = f"S1-{suffix[-10:]}"
        program = {
            "ma_ct": code, "ten_ct": "Sprint 1 CRUD Program", "ma_phong_ban": 1,
            "ngay_bat_dau": "2026-10-01", "ngay_ket_thuc": "2026-12-31", "chi_tieu": 4,
            "mo_ta_cong_viec": "Backend API testing", "yeu_cau": "Python basics", "quyen_loi": "Mentoring",
        }
        status_code, created, _ = self.json_request("/api/programs", "POST", token, program)
        self.assertEqual(status_code, 201, created)
        program_id = created["ma_chuong_trinh"]
        program["ten_ct"] = "Sprint 1 CRUD Program Updated"
        status_code, _, _ = self.json_request(f"/api/programs/{program_id}", "PUT", token, program)
        self.assertEqual(status_code, 200)
        status_code, detail, _ = self.json_request(f"/api/programs/{program_id}", token=token)
        self.assertEqual((status_code, detail["ten_ct"]), (200, "Sprint 1 CRUD Program Updated"))

    def test_documents_allow_cv_and_application_letter_with_owner_checks(self):
        token, _ = self.login("tuan.lm@internship.vn")
        status_code, workspace, _ = self.json_request("/api/interns/me/workspace", token=token)
        self.assertEqual(status_code, 200)
        own_profile = workspace["profile"]["ma_ho_so"]
        db = sqlite3.connect(self.db_path)
        try:
            other_profile = db.execute("SELECT ma_ho_so FROM HO_SO_THUC_TAP WHERE ma_ho_so != ? LIMIT 1", (own_profile,)).fetchone()[0]
        finally:
            db.close()

        for kind, filename in (("CV", "resume.pdf"), ("DonXinThucTap", "application.pdf")):
            status_code, raw, _ = self.upload(token, filename, kind, PDF, other_profile)
            self.assertEqual(status_code, 201, raw)
            saved = json.loads(raw)
            self.assertEqual((saved["ma_ho_so"], saved["loai_tai_lieu"]), (own_profile, kind))
        doc_id = saved["ma_tai_lieu"]

        status_code, rows, _ = self.json_request("/api/interns/me/workspace", token=token)
        self.assertEqual(status_code, 200)
        self.assertEqual({row["loai_tai_lieu"] for row in rows["documents"]}, {"CV", "DonXinThucTap"})
        status_code, file_body, headers = self.request(f"/api/documents/{doc_id}/file", token=token)
        self.assertEqual((status_code, file_body, headers.get_content_type()), (200, PDF, "application/pdf"))
        another_tts, _ = self.login("lananh.hoang@internship.vn")
        status_code, _, _ = self.request(f"/api/documents/{doc_id}/file", token=another_tts)
        self.assertEqual(status_code, 404)

        tuan_token, _ = self.login("tuan.lm@internship.vn")
        status_code, _, _ = self.upload(tuan_token, "intro.pdf", "GiayGioiThieu", PDF)
        self.assertEqual(status_code, 403)
        status_code, _, _ = self.upload(tuan_token, "bad.pdf", "Unknown", PDF)
        self.assertEqual(status_code, 400)
        status_code, _, _ = self.upload(tuan_token, "empty.pdf", "CV", b"")
        self.assertEqual(status_code, 400)
        status_code, _, _ = self.upload(tuan_token, "fake.pdf", "CV", b"not a PDF")
        self.assertEqual(status_code, 400)
        status_code, _, _ = self.upload(tuan_token, "large.pdf", "CV", b"%PDF-" + b"x" * (15 * 1024 * 1024))
        self.assertEqual(status_code, 400)

    def test_single_session_revokes_rest_and_pushes_logout_for_every_role(self):
        accounts = (
            ("Admin", "admin@internship.vn"),
            ("HR", "hr@internship.vn"),
            ("Mentor", "mentor@internship.vn"),
            ("ThucTapSinh", "tuan.lm@internship.vn"),
        )
        for expected_role, email in accounts:
            with self.subTest(role=expected_role):
                old_token, user = self.login(email)
                self.assertEqual(user["vai_tro"], expected_role)
                old_status, old_user, _ = self.json_request("/api/auth/me", token=old_token)
                self.assertEqual((old_status, old_user["vai_tro"]), (200, expected_role))
                websocket = WebSocketClient(
                    f"ws://127.0.0.1:{self.port}/api/auth/events?{urllib.parse.urlencode({'token': old_token})}"
                )
                try:
                    new_token, _ = self.login(email)
                    old_status, old_body, _ = self.json_request("/api/auth/me", token=old_token)
                    self.assertEqual(old_status, 401, old_body)
                    new_status, current_user, _ = self.json_request("/api/auth/me", token=new_token)
                    self.assertEqual((new_status, current_user["vai_tro"]), (200, expected_role))
                    event = websocket.receive_json()
                    self.assertEqual(event.get("type"), "FORCE_LOGOUT")
                finally:
                    websocket.close()

        status_code, body, _ = self.json_request(
            "/api/auth/me", headers={"X-User-Role": "Admin", "X-User-Id": "1"},
        )
        self.assertEqual(status_code, 401, body)

    def test_crud_authorization_uses_authenticated_server_role(self):
        tts_token, _ = self.login("tuan.lm@internship.vn")
        status_code, _, _ = self.json_request("/api/interns", token=tts_token)
        self.assertEqual(status_code, 403)
        status_code, _, _ = self.json_request("/api/mentors", "POST", tts_token, {
            "ho_ten": "Unauthorized", "email": "unauthorized@test.invalid", "mat_khau": "123456",
        })
        self.assertEqual(status_code, 403)
        mentor_token, _ = self.login("mentor@internship.vn")
        status_code, _, _ = self.json_request("/api/interns", "POST", mentor_token, {
            "ho_ten": "Unauthorized", "email": "unauthorized2@test.invalid",
        })
        self.assertEqual(status_code, 403)

    def test_us08_approval_email_outbox_and_notification_ownership(self):
        admin_token, _ = self.login("admin@internship.vn")
        suffix = str(time.time_ns())
        approved_email = f"us08.approved.{suffix}@test.invalid"
        rejected_email = f"us08.rejected.{suffix}@test.invalid"
        approved_data = {
            "ho_ten": "US08 Approved", "email": approved_email, "ma_phong_ban": 1,
            "ma_truong": 1, "chuyen_nganh": "QA", "trang_thai_xet_duyet": "ChoDuyet",
            "trang_thai_thuc_tap": "DangThucTap",
        }
        status_code, approved, _ = self.json_request("/api/interns", "POST", admin_token, approved_data)
        self.assertEqual(status_code, 201, approved)
        approved_data["trang_thai_xet_duyet"] = "DaDuyet"
        status_code, _, _ = self.json_request(
            f"/api/interns/{approved['ma_ho_so']}", "PUT", admin_token, approved_data,
        )
        self.assertEqual(status_code, 200)

        rejected_data = {**approved_data, "ho_ten": "US08 Rejected", "email": rejected_email,
                         "trang_thai_xet_duyet": "ChoDuyet"}
        status_code, rejected, _ = self.json_request("/api/interns", "POST", admin_token, rejected_data)
        self.assertEqual(status_code, 201, rejected)
        rejected_data["trang_thai_xet_duyet"] = "TuChoi"
        status_code, _, _ = self.json_request(
            f"/api/interns/{rejected['ma_ho_so']}", "PUT", admin_token, rejected_data,
        )
        self.assertEqual(status_code, 200)

        db = sqlite3.connect(self.db_path)
        try:
            approved_notification = db.execute(
                "SELECT ma_thong_bao FROM THONG_BAO WHERE ma_nguoi_dung=?", (approved["ma_nguoi_dung"],),
            ).fetchone()[0]
            rejected_notification = db.execute(
                "SELECT ma_thong_bao FROM THONG_BAO WHERE ma_nguoi_dung=?", (rejected["ma_nguoi_dung"],),
            ).fetchone()[0]
            rejected_email_status = db.execute(
                "SELECT status FROM EMAIL_OUTBOX WHERE recipient_email=?", (rejected_email,),
            ).fetchone()[0]
        finally:
            db.close()
        self.assertEqual(rejected_email_status, "PENDING")

        status_code, outbox, _ = self.json_request("/api/notifications/email-outbox", token=admin_token)
        self.assertEqual(status_code, 200)
        self.assertEqual({row["recipient_email"] for row in outbox if row["recipient_email"] in {
            approved_email, rejected_email}}, {approved_email, rejected_email})
        self.assertTrue(all("last_error" in row for row in outbox))

        approved_token, _ = self.login(approved_email)
        status_code, own_notifications, _ = self.json_request("/api/notifications", token=approved_token)
        self.assertEqual(status_code, 200)
        self.assertEqual(len(own_notifications), 1)
        self.assertEqual(own_notifications[0]["email_status"], "PENDING")
        status_code, _, _ = self.json_request("/api/notifications/email-outbox", token=approved_token)
        self.assertEqual(status_code, 403)
        status_code, _, _ = self.json_request(
            f"/api/notifications/{approved_notification}/read", "PUT", approved_token,
        )
        self.assertEqual(status_code, 200)
        self.assertIsNotNone(self.json_request("/api/notifications", token=approved_token)[1][0]["thoi_gian_doc"])

        self.assertNotIn(rejected_notification, {item["ma_thong_bao"] for item in own_notifications})
        status_code, _, _ = self.json_request(
            f"/api/notifications/{rejected_notification}/read", "PUT", approved_token,
        )
        self.assertEqual(status_code, 404)


if __name__ == "__main__":
    unittest.main()
