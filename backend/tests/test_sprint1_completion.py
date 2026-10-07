"""Focused Sprint 1 API regressions using a disposable SQLite database."""
import base64
from concurrent.futures import ThreadPoolExecutor
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
DOC = bytes.fromhex("D0CF11E0A1B11AE1") + b"Sprint 1 legacy Word test"


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
        environment["SMTP_HOST"] = ""
        environment["SMTP_USERNAME"] = ""
        environment["SMTP_PASSWORD"] = ""
        environment["SMTP_FROM"] = ""
        environment["IMS_COMPANY_NAME"] = "Test Organization"
        environment["IMS_PORTAL_URL"] = "https://ims.example.test"
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

    def upload_pending_document(self, intern_email="tuan.lm@internship.vn"):
        intern_token, _ = self.login(intern_email)
        status_code, workspace, _ = self.json_request("/api/interns/me/workspace", token=intern_token)
        self.assertEqual(status_code, 200, workspace)
        profile_id = workspace["profile"]["ma_ho_so"]
        admin_token, admin_user = self.login("admin@internship.vn")
        filename = f"us05-review-{time.time_ns()}.pdf"
        status_code, raw, _ = self.upload(admin_token, filename, "CV", PDF, profile_id=profile_id)
        self.assertEqual(status_code, 201, raw)
        saved = json.loads(raw)
        return {
            "document_id": saved["ma_tai_lieu"],
            "profile_id": profile_id,
            "intern_token": intern_token,
            "admin_token": admin_token,
            "admin_user_id": admin_user["ma_nguoi_dung"],
        }

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

    def test_registration_duplicate_phone_returns_conflict_instead_of_server_error(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                CREATE TRIGGER reject_duplicate_registration_phone
                BEFORE INSERT ON NGUOI_DUNG
                WHEN NEW.so_dien_thoai = '0920000000'
                BEGIN
                    SELECT RAISE(ABORT, 'UNIQUE constraint failed: NGUOI_DUNG.so_dien_thoai');
                END
            """)

        boundary = "----RegistrationDuplicatePhoneBoundary"
        form_fields = {
            "ho_ten": "Duplicate Phone Regression",
            "email": "duplicate.phone.regression@test.invalid",
            "so_dien_thoai": "0920000000",
        }
        body = b"".join(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8")
            for name, value in form_fields.items()
        ) + f"--{boundary}--\r\n".encode("ascii")
        status_code, raw, _ = self.request(
            "/api/auth/register-with-cv",
            method="POST",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        response = json.loads(raw)
        self.assertEqual(status_code, 409, response)
        self.assertIn("detail", response)

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
            "so_dien_thoai": "0912345678", "ma_phong_ban": 2,
            "ma_truong": 2, "chuyen_nganh": "Data Engineering",
            "trang_thai_thuc_tap": "DangThucTap",
        })
        self.assertEqual(status_code, 200, updated)
        status_code, detail, _ = self.json_request(f"/api/interns/{profile_id}", token=token)
        self.assertEqual(
            (status_code, detail["so_dien_thoai"], detail["chuyen_nganh"], detail["ma_truong"]),
            (200, "0912345678", "Data Engineering", 2),
        )

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

        uploaded_documents = {}
        for kind, filename in (("CV", "resume.pdf"), ("DonXinThucTap", "application.pdf")):
            status_code, raw, _ = self.upload(token, filename, kind, PDF, other_profile)
            self.assertEqual(status_code, 201, raw)
            saved = json.loads(raw)
            self.assertEqual((saved["ma_ho_so"], saved["loai_tai_lieu"]), (own_profile, kind))
            uploaded_documents[kind] = saved
        doc_id = uploaded_documents["DonXinThucTap"]["ma_tai_lieu"]

        status_code, rows, _ = self.json_request("/api/interns/me/workspace", token=token)
        self.assertEqual(status_code, 200)
        self.assertEqual({row["loai_tai_lieu"] for row in rows["documents"]}, {"CV", "DonXinThucTap"})
        status_code, file_body, headers = self.request(f"/api/documents/{doc_id}/file", token=token)
        self.assertEqual((status_code, file_body, headers.get_content_type()), (200, PDF, "application/pdf"))
        status_code, _, _ = self.request(f"/api/documents/{doc_id}/file")
        self.assertEqual(status_code, 401)
        another_tts, _ = self.login("lananh.hoang@internship.vn")
        status_code, _, _ = self.request(f"/api/documents/{doc_id}/file", token=another_tts)
        self.assertEqual(status_code, 404)
        status_code, _, _ = self.request(f"/api/documents/{doc_id}", "DELETE", another_tts)
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
        status_code, raw, _ = self.upload(tuan_token, "resume.doc", "CV", DOC)
        self.assertEqual(status_code, 201, raw)
        word_document_id = json.loads(raw)["ma_tai_lieu"]
        status_code, _, _ = self.upload(tuan_token, "legacy.png", "CV", b"\x89PNG\r\n\x1a\n")
        self.assertEqual(status_code, 400)
        status_code, _, _ = self.upload(tuan_token, "large.pdf", "CV", b"%PDF-" + b"x" * (5 * 1024 * 1024))
        self.assertEqual(status_code, 400)

        admin_token, _ = self.login("admin@internship.vn")
        hr_token, _ = self.login("hr@internship.vn")
        for manager_token in (admin_token, hr_token):
            status_code, file_body, _ = self.request(f"/api/documents/{doc_id}/file", token=manager_token)
            self.assertEqual((status_code, file_body), (200, PDF))
        status_code, _, _ = self.request(f"/api/documents/{word_document_id}", "DELETE", admin_token)
        self.assertEqual(status_code, 403)
        db = sqlite3.connect(self.db_path)
        try:
            stored_path = db.execute(
                "SELECT duong_dan_file FROM TAI_LIEU_HO_SO WHERE ma_tai_lieu = ?", (doc_id,),
            ).fetchone()[0]
        finally:
            db.close()
        deleted_file = self.db_path.parent / "uploads" / "documents" / Path(stored_path).name
        self.assertTrue(deleted_file.is_file())
        status_code, _, _ = self.request(f"/api/documents/{doc_id}", "DELETE", tuan_token)
        self.assertEqual(status_code, 204)
        self.assertFalse(deleted_file.exists())
        status_code, _, _ = self.request(f"/api/documents/{doc_id}/file", token=tuan_token)
        self.assertEqual(status_code, 404)

    def test_us05_hr_approval_persists_actor_time_and_prevents_second_decision(self):
        context = self.upload_pending_document()
        hr_token, hr_user = self.login("hr@internship.vn")
        with sqlite3.connect(self.db_path) as db:
            outbox_before = db.execute("SELECT COUNT(*) FROM EMAIL_OUTBOX").fetchone()[0]
            review_notice_before = db.execute(
                "SELECT COUNT(*) FROM THONG_BAO WHERE reference_type='document' AND reference_id=?",
                (str(context["document_id"]),),
            ).fetchone()[0]

        status_code, approved, _ = self.json_request(
            f"/api/documents/{context['document_id']}/review", "PUT", hr_token,
            {"trang_thai_duyet": "DaDuyet"},
        )
        self.assertEqual(status_code, 200, approved)
        self.assertEqual(approved["trang_thai_duyet"], "DaDuyet")
        self.assertEqual(approved["reviewed_by"], hr_user["ma_nguoi_dung"])
        self.assertEqual(approved["reviewer_name"], hr_user["ho_ten"])
        self.assertIsNotNone(approved["reviewed_at"])
        self.assertIsNone(approved["review_reason"])
        self.assertNotIn("duong_dan_file", approved)

        status_code, listing, _ = self.json_request("/api/documents?page=1&pageSize=100", token=hr_token)
        self.assertEqual(status_code, 200, listing)
        listed = next(item for item in listing["items"] if item["ma_tai_lieu"] == context["document_id"])
        self.assertEqual((listed["reviewed_by"], listed["reviewer_name"]), (hr_user["ma_nguoi_dung"], hr_user["ho_ten"]))
        self.assertNotIn("duong_dan_file", listed)

        status_code, workspace, _ = self.json_request("/api/interns/me/workspace", token=context["intern_token"])
        self.assertEqual(status_code, 200, workspace)
        intern_document = next(item for item in workspace["documents"] if item["ma_tai_lieu"] == context["document_id"])
        self.assertEqual(intern_document["trang_thai_duyet"], "DaDuyet")
        self.assertEqual(intern_document["reviewed_by"], hr_user["ma_nguoi_dung"])

        with sqlite3.connect(self.db_path) as db:
            saved_before = db.execute(
                "SELECT trang_thai_duyet, reviewed_by, review_reason, reviewed_at FROM TAI_LIEU_HO_SO WHERE ma_tai_lieu=?",
                (context["document_id"],),
            ).fetchone()
            status_code, _, _ = self.json_request(
                f"/api/documents/{context['document_id']}/review", "PUT", context["admin_token"],
                {"trang_thai_duyet": "TuChoi", "review_reason": "Không hợp lệ"},
            )
            self.assertEqual(status_code, 409)
            saved_after = db.execute(
                "SELECT trang_thai_duyet, reviewed_by, review_reason, reviewed_at FROM TAI_LIEU_HO_SO WHERE ma_tai_lieu=?",
                (context["document_id"],),
            ).fetchone()
            review_notice_after = db.execute(
                "SELECT COUNT(*) FROM THONG_BAO WHERE reference_type='document' AND reference_id=?",
                (str(context["document_id"]),),
            ).fetchone()[0]
            outbox_after = db.execute("SELECT COUNT(*) FROM EMAIL_OUTBOX").fetchone()[0]
        self.assertEqual(saved_after, saved_before)
        self.assertEqual(review_notice_after, review_notice_before + 1)
        self.assertEqual(outbox_after, outbox_before)

    def test_us05_rejection_requires_trimmed_reason_and_tts_can_read_it(self):
        context = self.upload_pending_document("lananh.hoang@internship.vn")
        admin_token, admin_user = self.login("admin@internship.vn")
        path = f"/api/documents/{context['document_id']}/review"
        for reason in (None, "", " \t\n "):
            payload = {"trang_thai_duyet": "TuChoi", "review_reason": reason}
            status_code, response, _ = self.json_request(path, "PUT", admin_token, payload)
            self.assertEqual(status_code, 400, response)
            self.assertIn("lý do", response["detail"].lower())

        with sqlite3.connect(self.db_path) as db:
            pending = db.execute(
                "SELECT trang_thai_duyet, reviewed_by, review_reason, reviewed_at FROM TAI_LIEU_HO_SO WHERE ma_tai_lieu=?",
                (context["document_id"],),
            ).fetchone()
        self.assertEqual(pending, ("ChoDuyet", None, None, None))

        status_code, rejected, _ = self.json_request(path, "PUT", admin_token, {
            "trang_thai_duyet": "TuChoi", "review_reason": "  Thiếu giấy tờ đối chiếu. \n",
        })
        self.assertEqual(status_code, 200, rejected)
        self.assertEqual(rejected["review_reason"], "Thiếu giấy tờ đối chiếu.")
        self.assertEqual(rejected["reviewed_by"], admin_user["ma_nguoi_dung"])
        self.assertIsNotNone(rejected["reviewed_at"])

        status_code, workspace, _ = self.json_request("/api/interns/me/workspace", token=context["intern_token"])
        self.assertEqual(status_code, 200, workspace)
        intern_document = next(item for item in workspace["documents"] if item["ma_tai_lieu"] == context["document_id"])
        self.assertEqual(intern_document["review_reason"], "Thiếu giấy tờ đối chiếu.")
        self.assertEqual(intern_document["reviewer_name"], admin_user["ho_ten"])

        hr_token, _ = self.login("hr@internship.vn")
        status_code, _, _ = self.json_request(path, "PUT", hr_token, {"trang_thai_duyet": "DaDuyet"})
        self.assertEqual(status_code, 409)

    def test_us05_rbac_and_client_cannot_spoof_review_actor_or_time(self):
        context = self.upload_pending_document()
        hr_token, hr_user = self.login("hr@internship.vn")
        path = f"/api/documents/{context['document_id']}/review"
        status_code, response, _ = self.json_request(path, "PUT", hr_token, {
            "trang_thai_duyet": "DaDuyet",
            "reviewed_by": context["profile_id"],
            "reviewed_at": "2000-01-01 00:00:00",
        })
        self.assertEqual(status_code, 422, response)

        mentor_token, _ = self.login("mentor@internship.vn")
        other_tts_token, _ = self.login("lananh.hoang@internship.vn")
        for token, expected in ((None, 401), (mentor_token, 403), (context["intern_token"], 403), (other_tts_token, 403)):
            status_code, _, _ = self.json_request(path, "PUT", token, {"trang_thai_duyet": "DaDuyet"})
            self.assertEqual(status_code, expected)

        status_code, _, _ = self.json_request("/api/documents", token=context["intern_token"])
        self.assertEqual(status_code, 403)
        with sqlite3.connect(self.db_path) as db:
            saved = db.execute(
                "SELECT trang_thai_duyet, reviewed_by, review_reason, reviewed_at FROM TAI_LIEU_HO_SO WHERE ma_tai_lieu=?",
                (context["document_id"],),
            ).fetchone()
        self.assertEqual(saved, ("ChoDuyet", None, None, None))

    def test_us05_concurrent_hr_admin_review_allows_only_one_decision(self):
        context = self.upload_pending_document()
        hr_token, hr_user = self.login("hr@internship.vn")
        requests = (
            (hr_token, {"trang_thai_duyet": "DaDuyet"}),
            (context["admin_token"], {"trang_thai_duyet": "TuChoi", "review_reason": "Bổ sung hồ sơ."}),
        )
        path = f"/api/documents/{context['document_id']}/review"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda args: self.json_request(path, "PUT", args[0], args[1]), requests))
        self.assertEqual(sorted(result[0] for result in results), [200, 409], results)

        with sqlite3.connect(self.db_path) as db:
            saved = db.execute(
                "SELECT trang_thai_duyet, reviewed_by, review_reason, reviewed_at FROM TAI_LIEU_HO_SO WHERE ma_tai_lieu=?",
                (context["document_id"],),
            ).fetchone()
            notices = db.execute(
                "SELECT COUNT(*) FROM THONG_BAO WHERE reference_type='document' AND reference_id=?",
                (str(context["document_id"]),),
            ).fetchone()[0]
        self.assertIn(saved[0], ("DaDuyet", "TuChoi"))
        self.assertIn(saved[1], (hr_user["ma_nguoi_dung"], context["admin_user_id"]))
        self.assertIsNotNone(saved[3])
        self.assertEqual(notices, 1)

    def test_us05_legacy_review_metadata_stays_null(self):
        context = self.upload_pending_document()
        with sqlite3.connect(self.db_path) as db:
            reviewer_fk = next(
                row for row in db.execute("PRAGMA foreign_key_list(TAI_LIEU_HO_SO)").fetchall()
                if row[3] == "reviewed_by"
            )
            self.assertEqual((reviewer_fk[2], reviewer_fk[4], reviewer_fk[6]), ("NGUOI_DUNG", "ma_nguoi_dung", "SET NULL"))
            db.execute(
                "UPDATE TAI_LIEU_HO_SO SET trang_thai_duyet='TuChoi' WHERE ma_tai_lieu=?",
                (context["document_id"],),
            )
            db.commit()
        hr_token, _ = self.login("hr@internship.vn")
        status_code, listing, _ = self.json_request("/api/documents?page=1&pageSize=100", token=hr_token)
        self.assertEqual(status_code, 200, listing)
        legacy = next(item for item in listing["items"] if item["ma_tai_lieu"] == context["document_id"])
        self.assertEqual(legacy["trang_thai_duyet"], "TuChoi")
        self.assertIsNone(legacy["reviewed_by"])
        self.assertIsNone(legacy["reviewed_at"])
        self.assertIsNone(legacy["review_reason"])

    def test_us05_secure_download_keeps_mentor_assignment_scope(self):
        suffix = str(time.time_ns())
        with sqlite3.connect(self.db_path) as db:
            mentor_id = db.execute(
                "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email='mentor@internship.vn'",
            ).fetchone()[0]
            profile_ids = []
            for index in range(2):
                cursor = db.execute("""
                    INSERT INTO NGUOI_DUNG
                        (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
                    VALUES (1, ?, ?, 'unused-test-hash', 'ThucTapSinh', 'HoatDong')
                """, (f"US05 Download Intern {index}", f"us05.download.{suffix}.{index}@test.invalid"))
                profile_cursor = db.execute("""
                    INSERT INTO HO_SO_THUC_TAP
                        (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
                    VALUES (?, 'US05 QA', 'DaDuyet', 'DangThucTap')
                """, (cursor.lastrowid,))
                profile_ids.append(profile_cursor.lastrowid)
            db.execute(
                "INSERT INTO PHAN_CONG_MENTOR_TTS (ma_nguoi_dung_mentor, ma_ho_so) VALUES (?, ?)",
                (mentor_id, profile_ids[0]),
            )

        admin_token, _ = self.login("admin@internship.vn")
        document_ids = []
        for profile_id in profile_ids:
            status_code, raw, _ = self.upload(
                admin_token, f"us05-mentor-{profile_id}.pdf", "CV", PDF, profile_id=profile_id,
            )
            self.assertEqual(status_code, 201, raw)
            document_ids.append(json.loads(raw)["ma_tai_lieu"])

        mentor_token, _ = self.login("mentor@internship.vn")
        allowed_status, allowed_body, _ = self.request(f"/api/documents/{document_ids[0]}/file", token=mentor_token)
        denied_status, _, _ = self.request(f"/api/documents/{document_ids[1]}/file", token=mentor_token)
        self.assertEqual((allowed_status, allowed_body), (200, PDF))
        self.assertEqual(denied_status, 404)

    def test_us05_notification_failure_rolls_back_review_metadata(self):
        context = self.upload_pending_document()
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                CREATE TRIGGER fail_us05_review_notification
                BEFORE INSERT ON THONG_BAO
                WHEN NEW.reference_type = 'document'
                BEGIN
                    SELECT RAISE(ABORT, 'US05 notification failure test');
                END
            """)

        try:
            status_code, _, _ = self.request(
                f"/api/documents/{context['document_id']}/review", "PUT", context["admin_token"],
                json.dumps({"trang_thai_duyet": "DaDuyet"}).encode("utf-8"),
                "application/json",
            )
            self.assertEqual(status_code, 500)
            with sqlite3.connect(self.db_path) as db:
                saved = db.execute(
                    "SELECT trang_thai_duyet, reviewed_by, review_reason, reviewed_at FROM TAI_LIEU_HO_SO WHERE ma_tai_lieu=?",
                    (context["document_id"],),
                ).fetchone()
            self.assertEqual(saved, ("ChoDuyet", None, None, None))
        finally:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DROP TRIGGER IF EXISTS fail_us05_review_notification")

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

        program = {
            "ma_ct": f"HR-{int(time.time())}", "ten_ct": "HR-created test program",
            "ma_phong_ban": 1, "ngay_bat_dau": "2026-10-01", "ngay_ket_thuc": "2026-12-31",
            "chi_tieu": 2, "mo_ta_cong_viec": "API regression", "yeu_cau": "Test requirements",
        }
        hr_token, _ = self.login("hr@internship.vn")
        status_code, created, _ = self.json_request("/api/programs", "POST", hr_token, program)
        self.assertEqual(status_code, 201, created)
        status_code, denied, _ = self.json_request("/api/programs", "POST", tts_token, {
            **program, "ma_ct": f"DENIED-{int(time.time())}",
        })
        self.assertEqual(status_code, 403, denied)

        db = sqlite3.connect(self.db_path)
        try:
            admin_password_hash = db.execute(
                "SELECT mat_khau FROM NGUOI_DUNG WHERE email='admin@internship.vn'",
            ).fetchone()[0]
            mentor_cursor = db.execute("""
                INSERT INTO NGUOI_DUNG
                    (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
                VALUES (1, 'HR Assignment Mentor', 'hr.assignment.mentor@test.invalid', ?, 'Mentor', 'HoatDong')
            """, (admin_password_hash,))
            mentor_id = mentor_cursor.lastrowid
            db.execute("""
                INSERT INTO MENTOR_PROFILE (ma_nguoi_dung, chuyen_mon, so_tts_toi_da)
                VALUES (?, 'Regression QA', 3)
            """, (mentor_id,))
            profile_ids = [row[0] for row in db.execute("""
                SELECT ma_ho_so FROM HO_SO_THUC_TAP
                WHERE ma_nguoi_dung IN (
                    SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email LIKE 'pagination.case%'
                )
                ORDER BY ma_ho_so LIMIT 2
            """).fetchall()]
            hr_user_id = db.execute(
                "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE email='hr@internship.vn'",
            ).fetchone()[0]
            db.commit()
        finally:
            db.close()

        self.assertEqual(len(profile_ids), 2)
        status_code, denied_assignment, _ = self.json_request(
            f"/api/mentors/{mentor_id}/assignments/batch", "POST", tts_token,
            {"ma_ho_so_list": [profile_ids[0]]},
        )
        self.assertEqual(status_code, 403, denied_assignment)
        status_code, assigned, _ = self.json_request(
            f"/api/mentors/{mentor_id}/interns/{profile_ids[0]}", "POST", hr_token,
        )
        self.assertEqual(status_code, 201, assigned)
        status_code, assigned_batch, _ = self.json_request(
            f"/api/mentors/{mentor_id}/assignments/batch", "POST", hr_token,
            {"ma_ho_so_list": [profile_ids[1]]},
        )
        self.assertEqual(status_code, 201, assigned_batch)
        db = sqlite3.connect(self.db_path)
        try:
            assigning_user_ids = [row[0] for row in db.execute("""
                SELECT ma_nguoi_phan_cong FROM PHAN_CONG_MENTOR_TTS
                WHERE ma_nguoi_dung_mentor=? ORDER BY ma_ho_so
            """, (mentor_id,)).fetchall()]
        finally:
            db.close()
        self.assertEqual(assigning_user_ids, [hr_user_id, hr_user_id])

        status_code, denied_unassignment, _ = self.json_request(
            f"/api/mentors/{mentor_id}/interns/{profile_ids[0]}", "DELETE", tts_token,
        )
        self.assertEqual(status_code, 403, denied_unassignment)
        status_code, unassigned, _ = self.json_request(
            f"/api/mentors/{mentor_id}/interns/{profile_ids[0]}", "DELETE", hr_token,
        )
        self.assertEqual(status_code, 200, unassigned)
        status_code, repeated_unassignment, _ = self.json_request(
            f"/api/mentors/{mentor_id}/interns/{profile_ids[0]}", "DELETE", hr_token,
        )
        self.assertEqual(status_code, 404, repeated_unassignment)
        status_code, available_interns, _ = self.json_request(
            "/api/mentors/unassigned-interns", token=hr_token,
        )
        self.assertEqual(status_code, 200, available_interns)
        self.assertIn(profile_ids[0], [intern["ma_ho_so"] for intern in available_interns])
        db = sqlite3.connect(self.db_path)
        try:
            remaining_assignments = db.execute(
                "SELECT ma_ho_so FROM PHAN_CONG_MENTOR_TTS WHERE ma_nguoi_dung_mentor=?",
                (mentor_id,),
            ).fetchall()
            unassigned_profile_still_exists = db.execute(
                "SELECT 1 FROM HO_SO_THUC_TAP WHERE ma_ho_so=?", (profile_ids[0],),
            ).fetchone()
        finally:
            db.close()
        self.assertEqual(remaining_assignments, [(profile_ids[1],)])
        self.assertIsNotNone(unassigned_profile_still_exists)

        status_code, workspace, _ = self.json_request("/api/interns/me/workspace", token=tts_token)
        self.assertEqual(status_code, 200)
        profile = workspace["profile"]
        status_code, _, _ = self.json_request(
            f"/api/interns/{profile['ma_ho_so']}", "PUT", tts_token,
            {
                "ho_ten": profile["ho_ten"], "email": profile["email"],
                "so_dien_thoai": "0912345678", "ma_phong_ban": None,
                "ma_truong": profile["ma_truong"], "chuyen_nganh": "Unauthorized",
                "trang_thai_thuc_tap": "DangThucTap",
            },
        )
        self.assertEqual(status_code, 403)

    def test_us08_approval_email_outbox_and_notification_ownership(self):
        admin_token, _ = self.login("admin@internship.vn")
        suffix = str(time.time_ns())
        approved_email = f"us08.approved.{suffix}@test.invalid"
        rejected_email = f"us08.rejected.{suffix}@test.invalid"
        db = sqlite3.connect(self.db_path)
        try:
            password_hash = db.execute(
                "SELECT mat_khau FROM NGUOI_DUNG WHERE email='admin@internship.vn'",
            ).fetchone()[0]
            profiles = {}
            for full_name, email in (("US08 Approved", approved_email), ("US08 Rejected", rejected_email)):
                cursor = db.execute("""
                    INSERT INTO NGUOI_DUNG
                        (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
                    VALUES (1, ?, ?, ?, 'ThucTapSinh', 'HoatDong')
                """, (full_name, email, password_hash))
                user_id = cursor.lastrowid
                cursor = db.execute("""
                    INSERT INTO HO_SO_THUC_TAP
                        (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
                    VALUES (?, 1, 'QA', 'ChoDuyet', NULL)
                """, (user_id,))
                profiles[email] = (user_id, cursor.lastrowid)
            db.commit()
        finally:
            db.close()

        approved_user_id, approved_profile_id = profiles[approved_email]
        rejected_user_id, rejected_profile_id = profiles[rejected_email]
        status_code, _, _ = self.json_request(
            f"/api/auth/users/{approved_user_id}/approve", "PUT", admin_token,
        )
        self.assertEqual(status_code, 200)

        status_code, _, _ = self.json_request(
            f"/api/auth/users/{rejected_user_id}/reject", "PUT", admin_token,
        )
        self.assertEqual(status_code, 200)

        db = sqlite3.connect(self.db_path)
        try:
            approved_notification = db.execute(
                "SELECT ma_thong_bao FROM THONG_BAO WHERE ma_nguoi_dung=?", (approved_user_id,),
            ).fetchone()[0]
            rejected_notification = db.execute(
                "SELECT ma_thong_bao FROM THONG_BAO WHERE ma_nguoi_dung=?", (rejected_user_id,),
            ).fetchone()[0]
            rejected_email_status = db.execute(
                "SELECT status FROM EMAIL_OUTBOX WHERE recipient_email=?", (rejected_email,),
            ).fetchone()[0]
            db.execute("""
                INSERT INTO THONG_BAO
                    (ma_nguoi_dung, tieu_de, noi_dung, kenh, loai, reference_type, reference_id)
                VALUES (?, 'Old mailbox message', 'Legacy message', 'App',
                        'mailbox_message', 'internal_message', 'legacy-1')
            """, (approved_user_id,))
            # Restore the shared test password after the approval endpoint rotates
            # real credentials, so ownership checks can authenticate this fixture.
            db.execute(
                "UPDATE NGUOI_DUNG SET mat_khau=?, must_change_password=0 WHERE ma_nguoi_dung=?",
                (password_hash, approved_user_id),
            )
            db.commit()
        finally:
            db.close()
        self.assertEqual(rejected_email_status, "PENDING")
        status_code, intern_rows, _ = self.json_request(
            f"/api/interns?search={approved_email}", token=admin_token,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(intern_rows["items"][0]["email_status"], "PENDING")

        status_code, outbox, _ = self.json_request("/api/notifications/email-outbox", token=admin_token)
        self.assertEqual(status_code, 200)
        self.assertEqual({row["recipient_email"] for row in outbox if row["recipient_email"] in {
            approved_email, rejected_email}}, {approved_email, rejected_email})
        self.assertTrue(all("last_error" in row for row in outbox))
        self.assertTrue(all("body" not in row for row in outbox))
        self.assertTrue(all("attempts_made" in row for row in outbox))
        hr_token, _ = self.login("hr@internship.vn")
        self.assertEqual(self.json_request("/api/notifications/email-outbox", token=hr_token)[0], 200)

        approved_token, _ = self.login(approved_email)
        status_code, own_notifications, _ = self.json_request("/api/notifications", token=approved_token)
        self.assertEqual(status_code, 200)
        self.assertEqual(len(own_notifications), 1)
        self.assertNotIn("email_status", own_notifications[0])
        self.assertEqual(own_notifications[0]["reference_type"], "intern_profile")
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

    def test_admin_status_approval_queues_temporary_credentials_email(self):
        admin_token, _ = self.login("admin@internship.vn")
        email = f"status.approval.{time.time_ns()}@test.invalid"
        db = sqlite3.connect(self.db_path)
        try:
            password_hash = db.execute(
                "SELECT mat_khau FROM NGUOI_DUNG WHERE email='admin@internship.vn'",
            ).fetchone()[0]
            cursor = db.execute("""
                INSERT INTO NGUOI_DUNG
                    (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
                VALUES (1, 'Status Approval Test', ?, ?, 'ThucTapSinh', 'ChoDuyet')
            """, (email, password_hash))
            user_id = cursor.lastrowid
            db.execute("""
                INSERT INTO HO_SO_THUC_TAP
                    (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet)
                VALUES (?, 1, 'QA', 'ChoDuyet')
            """, (user_id,))
            db.commit()
        finally:
            db.close()

        status_code, raw_response, _ = self.request(
            f"/api/auth/users/{user_id}/status", "PUT", admin_token,
            json.dumps({"trang_thai": "HoatDong"}).encode("utf-8"),
            "application/json",
        )
        response = raw_response.decode("utf-8", errors="replace")
        self.assertEqual(status_code, 200, response)

        db = sqlite3.connect(self.db_path)
        try:
            account_status = db.execute(
                "SELECT trang_thai, must_change_password FROM NGUOI_DUNG WHERE ma_nguoi_dung=?",
                (user_id,),
            ).fetchone()
            email_row = db.execute(
                "SELECT recipient_email, status, template_type, body FROM EMAIL_OUTBOX WHERE recipient_email=?",
                (email,),
            ).fetchone()
        finally:
            db.close()
        self.assertEqual(account_status, ("HoatDong", 1))
        self.assertIsNotNone(email_row)
        self.assertEqual(email_row[:3], (email, "PENDING", "temporary_credentials"))
        self.assertIn(email, email_row[3])

    def test_intern_profile_update_rejects_approval_fields_and_dedicated_review_works(self):
        admin_token, _ = self.login("admin@internship.vn")
        hr_token, _ = self.login("hr@internship.vn")
        email = f"us08.concurrent.{time.time_ns()}@test.invalid"
        db = sqlite3.connect(self.db_path)
        try:
            password_hash = db.execute(
                "SELECT mat_khau FROM NGUOI_DUNG WHERE email='admin@internship.vn'",
            ).fetchone()[0]
            cursor = db.execute("""
                INSERT INTO NGUOI_DUNG
                    (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
                VALUES (1, 'US08 Concurrent', ?, ?, 'ThucTapSinh', 'HoatDong')
            """, (email, password_hash))
            user_id = cursor.lastrowid
            cursor = db.execute("""
                INSERT INTO HO_SO_THUC_TAP
                    (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
                VALUES (?, 1, 'QA', 'ChoDuyet', NULL)
            """, (user_id,))
            profile_id = cursor.lastrowid
            db.commit()
        finally:
            db.close()

        status_code, _, _ = self.json_request(f"/api/interns/{profile_id}", "PUT", admin_token, {
            "ho_ten": "US08 Concurrent", "email": email, "ma_phong_ban": 1,
            "ma_truong": 1, "chuyen_nganh": "QA",
            "trang_thai_xet_duyet": "DaDuyet", "trang_thai_thuc_tap": "DangThucTap",
        })
        self.assertEqual(status_code, 422)

        db = sqlite3.connect(self.db_path)
        try:
            final_status = db.execute(
                "SELECT trang_thai_xet_duyet FROM HO_SO_THUC_TAP WHERE ma_ho_so=?", (profile_id,),
            ).fetchone()[0]
            email_count = db.execute(
                "SELECT COUNT(*) FROM EMAIL_OUTBOX WHERE deduplication_key LIKE ?",
                (f"us08:intern_profile:{profile_id}:%",),
            ).fetchone()[0]
            notification_count = db.execute(
                "SELECT COUNT(*) FROM THONG_BAO WHERE ma_nguoi_dung=?", (user_id,),
            ).fetchone()[0]
        finally:
            db.close()
        self.assertEqual(final_status, "ChoDuyet")
        self.assertEqual((email_count, notification_count), (0, 0))

        status_code, _, _ = self.json_request(
            f"/api/auth/users/{user_id}/approve", "PUT", hr_token,
        )
        self.assertEqual(status_code, 200)

        db = sqlite3.connect(self.db_path)
        try:
            retry_status = db.execute(
                "SELECT trang_thai_xet_duyet FROM HO_SO_THUC_TAP WHERE ma_ho_so=?", (profile_id,),
            ).fetchone()[0]
            retry_email_count = db.execute(
                "SELECT COUNT(*) FROM EMAIL_OUTBOX WHERE deduplication_key LIKE ?",
                (f"us08:intern_profile:{profile_id}:%",),
            ).fetchone()[0]
            retry_notification_count = db.execute(
                "SELECT COUNT(*) FROM THONG_BAO WHERE ma_nguoi_dung=?", (user_id,),
            ).fetchone()[0]
        finally:
            db.close()
        self.assertEqual(retry_status, "DaDuyet")
        self.assertEqual((retry_email_count, retry_notification_count), (1, 1))

    def test_us08_program_review_is_serialized_and_queues_complete_result_emails(self):
        admin_token, _ = self.login("admin@internship.vn")
        hr_token, _ = self.login("hr@internship.vn")
        suffix = str(time.time_ns())[-12:]
        program_name = f"US08 Review {suffix}"
        status_code, program, _ = self.json_request("/api/programs", "POST", admin_token, {
            "ma_ct": f"US08-{suffix}", "ten_ct": program_name, "ma_phong_ban": 1,
            "ngay_bat_dau": "2026-11-01", "ngay_ket_thuc": "2026-12-01",
            "chi_tieu": 1, "mo_ta_cong_viec": "US08 test program",
            "yeu_cau": "Test only", "quyen_loi": "Test",
        })
        self.assertEqual(status_code, 201, program)
        program_id = program["ma_chuong_trinh"]

        test_emails = (
            "tuan.lm@internship.vn",
            "minh.khoi.nguyen@internship.vn",
            "ngoc.tran@internship.vn",
        )
        db = sqlite3.connect(self.db_path)
        try:
            placeholders = ",".join("?" for _ in test_emails)
            profiles = db.execute(f"""
                SELECT h.ma_ho_so, u.email
                FROM HO_SO_THUC_TAP h JOIN NGUOI_DUNG u ON u.ma_nguoi_dung=h.ma_nguoi_dung
                WHERE u.email IN ({placeholders})
            """, test_emails).fetchall()
            profile_by_email = {email: profile_id for profile_id, email in profiles}
            self.assertEqual(set(profile_by_email), set(test_emails))
            application_ids = {}
            for email in test_emails:
                cursor = db.execute("""
                    INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai)
                    VALUES (?, ?, 'ChoDuyet')
                """, (program_id, profile_by_email[email]))
                application_ids[email] = cursor.lastrowid
            db.commit()
        finally:
            db.close()

        def approve(application_id, token):
            return self.json_request(
                f"/api/programs/{program_id}/applications/{application_id}", "PUT", token,
                {"trang_thai": "DaDuyet"},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(
                lambda values: approve(*values),
                ((application_ids[test_emails[0]], admin_token),
                 (application_ids[test_emails[1]], hr_token)),
            ))
        self.assertEqual(sorted(status for status, _, _ in outcomes), [200, 400])

        db = sqlite3.connect(self.db_path)
        try:
            decisions = dict(db.execute("""
                SELECT ma_ung_tuyen, trang_thai FROM UNG_TUYEN_CHUONG_TRINH
                WHERE ma_chuong_trinh = ?
            """, (program_id,)).fetchall())
        finally:
            db.close()
        approved_id = next(app_id for app_id, decision in decisions.items() if decision == "DaDuyet")
        pending_ids = [app_id for app_id, decision in decisions.items() if decision == "ChoDuyet"]
        self.assertEqual(len(pending_ids), 2)
        rejected_id = pending_ids[0]
        status_code, rejected_response, _ = self.json_request(
            f"/api/programs/{program_id}/applications/{rejected_id}", "PUT", hr_token,
            {"trang_thai": "TuChoi", "reject_reason": "Thiếu kinh nghiệm chuyên môn."},
        )
        self.assertEqual(status_code, 200, rejected_response)
        blank_reason_id = pending_ids[1]
        status_code, blank_response, _ = self.json_request(
            f"/api/programs/{program_id}/applications/{blank_reason_id}", "PUT", admin_token,
            {"trang_thai": "TuChoi", "reject_reason": "  "},
        )
        self.assertEqual(status_code, 200, blank_response)

        db = sqlite3.connect(self.db_path)
        try:
            rows = db.execute("""
                SELECT reference_id, subject, body, status, retry_count, max_retry
                FROM EMAIL_OUTBOX WHERE reference_type='program_application'
                  AND reference_id IN (?, ?, ?)
            """, tuple(str(application_ids[email]) for email in test_emails)).fetchall()
        finally:
            db.close()
        self.assertEqual(len(rows), 3)
        by_application = {int(row[0]): row for row in rows}
        approved_mail = by_application[approved_id]
        self.assertIn("[Test Organization] Thông báo kết quả xét duyệt hồ sơ thực tập sinh", approved_mail[1])
        for expected in ("Chúc mừng", program_name, "Test Organization", "2026-11-01",
                         "2026-12-01", "Bước tiếp theo", "hợp đồng", "https://ims.example.test"):
            self.assertIn(expected, approved_mail[2])
        self.assertNotIn("None", approved_mail[2])
        self.assertEqual((approved_mail[3], approved_mail[4], approved_mail[5]), ("PENDING", 0, 4))

        rejected_mail = by_application[rejected_id]
        self.assertIn("Thiếu kinh nghiệm chuyên môn.", rejected_mail[2])
        self.assertIn("lưu hồ sơ", rejected_mail[2])
        blank_reason_mail = by_application[blank_reason_id]
        self.assertNotIn("Ghi chú từ HR:", blank_reason_mail[2])
        self.assertNotIn("None", blank_reason_mail[2])


    def create_contract_intern(self, suffix, approval="DaDuyet"):
        email = f"us09.{suffix}@test.invalid"
        db = sqlite3.connect(self.db_path)
        try:
            password_hash = db.execute(
                "SELECT mat_khau FROM NGUOI_DUNG WHERE email='tuan.lm@internship.vn'",
            ).fetchone()[0]
            user = db.execute("""
                INSERT INTO NGUOI_DUNG
                    (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
                VALUES (1, ?, ?, ?, 'ThucTapSinh', 'HoatDong')
            """, (f"US09 Intern {suffix}", email, password_hash))
            profile = db.execute("""
                INSERT INTO HO_SO_THUC_TAP
                    (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
                VALUES (?, 1, 'Backend QA', ?, 'DangThucTap')
            """, (user.lastrowid, approval))
            db.commit()
            return {"user_id": user.lastrowid, "profile_id": profile.lastrowid, "email": email}
        finally:
            db.close()

    def upload_contract(self, token, profile_id, filename="contract.pdf", content=PDF, mime_type="application/pdf"):
        boundary = "----US09ContractBoundary6f4d"
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"ma_ho_so\"\r\n\r\n{profile_id}\r\n".encode(),
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
             f"Content-Type: {mime_type}\r\n\r\n").encode() + content + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        status_code, body, headers = self.request(
            "/api/contracts", "POST", token, b"".join(parts),
            f"multipart/form-data; boundary={boundary}",
        )
        return status_code, json.loads(body) if body else None, headers

    def test_us09_contract_upload_creates_private_file_notification_and_outbox(self):
        suffix = str(time.time_ns())
        intern_a = self.create_contract_intern(f"a.{suffix}")
        intern_b = self.create_contract_intern(f"b.{suffix}")
        admin_token, admin = self.login("admin@internship.vn")
        hr_token, hr = self.login("hr@internship.vn")

        db = sqlite3.connect(self.db_path)
        try:
            program = db.execute("""
                INSERT INTO CHUONG_TRINH_THUC_TAP
                    (ma_ct, ten_ct, ma_phong_ban, ngay_bat_dau, ngay_ket_thuc, chi_tieu, trang_thai)
                VALUES (?, 'US09 Backend Internship', 1, '2026-10-10', '2026-12-10', 2, 'DangMo')
            """, (f"US09-{suffix}",))
            db.execute("""
                INSERT INTO UNG_TUYEN_CHUONG_TRINH
                    (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet, nguoi_xet_duyet)
                VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP, ?)
            """, (program.lastrowid, intern_a["profile_id"], admin["ma_nguoi_dung"]))
            db.commit()
        finally:
            db.close()

        status_code, contract_a, _ = self.upload_contract(admin_token, intern_a["profile_id"])
        self.assertEqual(status_code, 201, contract_a)
        contract_id = contract_a["ma_hop_dong"]
        self.assertEqual(contract_a["trang_thai"], "PENDING_CONFIRMATION")
        self.assertEqual(contract_a["ten_chuong_trinh"], "US09 Backend Internship")
        self.assertNotIn("storage_key", contract_a)

        status_code, contract_b, _ = self.upload_contract(hr_token, intern_b["profile_id"])
        self.assertEqual(status_code, 201, contract_b)

        tts_a_token, tts_a_user = self.login(intern_a["email"])
        tts_b_token, tts_b_user = self.login(intern_b["email"])
        status_code, owned, _ = self.json_request("/api/contracts/mine", token=tts_a_token)
        self.assertEqual(status_code, 200)
        self.assertEqual(owned["ma_hop_dong"], contract_id)
        self.assertNotIn("storage_key", owned)
        status_code, detail, _ = self.json_request(f"/api/contracts/{contract_id}", token=tts_a_token)
        self.assertEqual(status_code, 200, detail)
        self.assertNotIn("storage_key", detail)
        self.assertNotIn("uploaded_by", detail)
        self.assertEqual(
            [(item["action"], item["old_status"], item["new_status"]) for item in detail["history"]],
            [("UPLOADED", None, "PENDING_CONFIRMATION")],
        )
        status_code, _, _ = self.json_request(f"/api/contracts/{contract_b['ma_hop_dong']}", token=tts_a_token)
        self.assertEqual(status_code, 404)
        status_code, _, _ = self.json_request(f"/api/contracts/{contract_id}/confirm", "POST", token=admin_token)
        self.assertEqual(status_code, 403)

        status_code, body, headers = self.request(
            f"/api/contracts/{contract_id}/preview", token=tts_a_token,
        )
        self.assertEqual((status_code, body, headers.get_content_type()), (200, PDF, "application/pdf"))
        self.assertIn("no-store", headers.get("Cache-Control", ""))
        status_code, body, headers = self.request(
            f"/api/contracts/{contract_id}/download", token=tts_a_token,
        )
        self.assertEqual((status_code, body), (200, PDF))
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        status_code, _, _ = self.request(
            f"/api/contracts/{contract_b['ma_hop_dong']}/preview", token=tts_a_token,
        )
        self.assertEqual(status_code, 404)
        status_code, _, _ = self.request(
            f"/api/contracts/{contract_b['ma_hop_dong']}/download", token=tts_a_token,
        )
        self.assertEqual(status_code, 404)

        status_code, second_contract_a, _ = self.upload_contract(admin_token, intern_a["profile_id"])
        self.assertEqual(status_code, 201, second_contract_a)
        self.assertNotEqual(second_contract_a["ma_hop_dong"], contract_id)
        status_code, all_owned_contracts, _ = self.json_request(
            "/api/contracts/mine/all", token=tts_a_token,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(
            {item["ma_hop_dong"] for item in all_owned_contracts},
            {contract_id, second_contract_a["ma_hop_dong"]},
        )

        status_code, _, _ = self.json_request(
            f"/api/contracts/{contract_id}/confirm", "POST", token=tts_b_token,
        )
        self.assertEqual(status_code, 404)
        status_code, _, _ = self.json_request(
            f"/api/contracts/{contract_id}/reject", "POST", token=tts_b_token,
            data={"reason": "Sai thông tin hợp đồng."},
        )
        self.assertEqual(status_code, 404)
        for invalid_reason in ("", "   ", "ngắn", "x" * 501):
            status_code, _, _ = self.json_request(
                f"/api/contracts/{second_contract_a['ma_hop_dong']}/reject", "POST", token=tts_a_token,
                data={"reason": invalid_reason},
            )
            self.assertEqual(status_code, 422, invalid_reason)
        status_code, confirmed_contract, _ = self.json_request(
            f"/api/contracts/{contract_id}/confirm", "POST", token=tts_a_token,
            data={"confirmed_by": tts_b_user["ma_nguoi_dung"], "confirmed_at": "2000-01-01 00:00:00", "trang_thai": "REJECTED"},
        )
        self.assertEqual(status_code, 200, confirmed_contract)
        self.assertEqual(confirmed_contract["trang_thai"], "CONFIRMED")
        status_code, _, _ = self.json_request(
            f"/api/contracts/{contract_id}/confirm", "POST", token=tts_a_token,
        )
        self.assertEqual(status_code, 409)
        rejection_reason = "Sai thông tin thời gian thực tập."
        status_code, rejected_contract, _ = self.json_request(
            f"/api/contracts/{second_contract_a['ma_hop_dong']}/reject", "POST", token=tts_a_token,
            data={
                "reason": rejection_reason,
                "rejected_by": tts_b_user["ma_nguoi_dung"],
                "rejected_at": "2000-01-01 00:00:00",
                "trang_thai": "CONFIRMED",
            },
        )
        self.assertEqual(status_code, 200, rejected_contract)
        self.assertEqual(rejected_contract["trang_thai"], "REJECTED")
        self.assertEqual(rejected_contract["rejection_reason"], rejection_reason)
        self.assertEqual(rejected_contract["history"][-1]["reason"], rejection_reason)
        status_code, _, _ = self.json_request(
            f"/api/contracts/{second_contract_a['ma_hop_dong']}/reject", "POST", token=tts_a_token,
            data={"reason": "Changed reason after final state."},
        )
        self.assertEqual(status_code, 409)
        status_code, all_owned_contracts, _ = self.json_request(
            "/api/contracts/mine/all", token=tts_a_token,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(
            {item["ma_hop_dong"]: item["trang_thai"] for item in all_owned_contracts},
            {contract_id: "CONFIRMED", second_contract_a["ma_hop_dong"]: "REJECTED"},
        )

        db = sqlite3.connect(self.db_path)
        try:
            record = db.execute("""
                SELECT storage_key, uploaded_by, original_file_name, file_size, mime_type, trang_thai,
                       confirmed_by, confirmed_at
                FROM HOP_DONG_THUC_TAP WHERE ma_hop_dong=?
            """, (contract_id,)).fetchone()
            rejected_record = db.execute("""
                SELECT rejected_by, rejected_at, rejection_reason
                FROM HOP_DONG_THUC_TAP WHERE ma_hop_dong=?
            """, (second_contract_a["ma_hop_dong"],)).fetchone()
            history = db.execute("""
                SELECT action, old_status, new_status, actor_id, actor_name, actor_role, reason
                FROM HOP_DONG_THUC_TAP_LICH_SU WHERE ma_hop_dong=? ORDER BY history_id
            """, (contract_id,)).fetchall()
            notice = db.execute("""
                SELECT loai, reference_type, reference_id FROM THONG_BAO
                WHERE ma_nguoi_dung=? AND reference_type='internship_contract'
            """, (intern_a["user_id"],)).fetchone()
            email = db.execute("""
                SELECT recipient_email, template_type, reference_type, reference_id,
                       deduplication_key, status, body
                FROM EMAIL_OUTBOX WHERE deduplication_key=?
            """, (f"us09:contract:{contract_id}:uploaded",)).fetchone()
            decision_email = db.execute("""
                SELECT recipient_email, template_type, reference_type, reference_id,
                       deduplication_key, body
                FROM EMAIL_OUTBOX WHERE deduplication_key=?
            """, (f"us10:contract:{second_contract_a['ma_hop_dong']}:rejected",)).fetchone()
        finally:
            db.close()
        self.assertEqual(record[1:6], (admin["ma_nguoi_dung"], "contract.pdf", len(PDF), "application/pdf", "CONFIRMED"))
        self.assertEqual(record[6], tts_a_user["ma_nguoi_dung"])
        self.assertIsNotNone(record[7])
        self.assertEqual(rejected_record[0], tts_a_user["ma_nguoi_dung"])
        self.assertNotEqual(rejected_record[1], "2000-01-01 00:00:00")
        self.assertEqual(rejected_record[2], rejection_reason)
        self.assertEqual(
            [item[:3] for item in history],
            [("UPLOADED", None, "PENDING_CONFIRMATION"), ("CONFIRMED", "PENDING_CONFIRMATION", "CONFIRMED")],
        )
        self.assertEqual(history[1][3:6], (tts_a_user["ma_nguoi_dung"], tts_a_user["ho_ten"], "ThucTapSinh"))
        self.assertEqual(decision_email[:5], ("admin@internship.vn", "contract_decision", "internship_contract", str(second_contract_a["ma_hop_dong"]), f"us10:contract:{second_contract_a['ma_hop_dong']}:rejected"))
        self.assertIn(rejection_reason, decision_email[5])
        self.assertTrue(record[0].endswith(".pdf"))
        self.assertEqual(notice, ("contract_uploaded", "internship_contract", str(contract_id)))
        self.assertEqual(email[:6], (intern_a["email"], "contract_uploaded", "internship_contract", str(contract_id), f"us09:contract:{contract_id}:uploaded", "PENDING"))
        self.assertIn("US09 Backend Internship", email[6])
        self.assertIn("Phòng ban: Trung tâm Công nghệ Thông tin", email[6])
        self.assertIn("Thời gian dự kiến: 2026-10-10 – 2026-12-10", email[6])
        self.assertIn("Trạng thái hợp đồng: Chờ xác nhận", email[6])
        self.assertIn(f"https://ims.example.test/login?next=%2Fcontracts%2F{contract_id}", email[6])
        self.assertIn("không đính kèm hợp đồng", email[6])
        status_code, _, _ = self.json_request("/api/contracts?page=1&pageSize=10", token=tts_a_token)
        self.assertEqual(status_code, 403)
        contract_path = self.temp_path / "uploads" / "contracts" / record[0]
        self.assertTrue(contract_path.is_file())

    def test_us10_concurrent_confirm_and_reject_only_create_one_transition(self):
        suffix = str(time.time_ns())
        intern = self.create_contract_intern(f"us10-race.{suffix}")
        admin_token, _ = self.login("admin@internship.vn")
        status_code, contract, _ = self.upload_contract(admin_token, intern["profile_id"])
        self.assertEqual(status_code, 201, contract)
        intern_token, _ = self.login(intern["email"])
        contract_id = contract["ma_hop_dong"]

        def submit(decision):
            if decision == "confirm":
                return self.json_request(f"/api/contracts/{contract_id}/confirm", "POST", token=intern_token)
            return self.json_request(
                f"/api/contracts/{contract_id}/reject", "POST", token=intern_token,
                data={"reason": "Thông tin thời gian chưa đúng."},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(submit, ("confirm", "reject")))
        self.assertEqual(sorted(outcome[0] for outcome in outcomes), [200, 409])
        winning_response = next(outcome[1] for outcome in outcomes if outcome[0] == 200)
        self.assertIn(winning_response["trang_thai"], {"CONFIRMED", "REJECTED"})

        status_code, detail, _ = self.json_request(f"/api/contracts/{contract_id}", token=intern_token)
        self.assertEqual(status_code, 200)
        self.assertEqual([event["action"] for event in detail["history"]], ["UPLOADED", winning_response["trang_thai"]])
        db = sqlite3.connect(self.db_path)
        try:
            decisions = db.execute("""
                SELECT action, COUNT(*) FROM HOP_DONG_THUC_TAP_LICH_SU
                WHERE ma_hop_dong=? AND action IN ('CONFIRMED', 'REJECTED') GROUP BY action
            """, (contract_id,)).fetchall()
        finally:
            db.close()
        self.assertEqual(sum(count for _, count in decisions), 1)

    def test_us10_outbox_failure_rolls_back_decision_and_history(self):
        suffix = str(time.time_ns())
        intern = self.create_contract_intern(f"us10-rollback.{suffix}")
        admin_token, _ = self.login("admin@internship.vn")
        status_code, contract, _ = self.upload_contract(admin_token, intern["profile_id"])
        self.assertEqual(status_code, 201, contract)
        intern_token, _ = self.login(intern["email"])
        contract_id = contract["ma_hop_dong"]

        with sqlite3.connect(self.db_path) as db:
            db.execute(f"""
                CREATE TRIGGER fail_us10_outbox_insert
                BEFORE INSERT ON EMAIL_OUTBOX
                WHEN NEW.deduplication_key = 'us10:contract:{contract_id}:confirmed'
                BEGIN SELECT RAISE(ABORT, 'forced isolated-test outbox failure'); END
            """)

        try:
            status_code, _, _ = self.json_request(
                f"/api/contracts/{contract_id}/confirm", "POST", token=intern_token,
            )
            self.assertEqual(status_code, 500)
            with sqlite3.connect(self.db_path) as db:
                record = db.execute(
                    "SELECT trang_thai FROM HOP_DONG_THUC_TAP WHERE ma_hop_dong=?",
                    (contract_id,),
                ).fetchone()
                history = db.execute(
                    "SELECT action FROM HOP_DONG_THUC_TAP_LICH_SU WHERE ma_hop_dong=? ORDER BY history_id",
                    (contract_id,),
                ).fetchall()
                decision_notifications = db.execute("""
                    SELECT COUNT(*) FROM THONG_BAO
                    WHERE reference_type='internship_contract' AND reference_id=? AND loai='contract_decision'
                """, (str(contract_id),)).fetchone()[0]
                decision_emails = db.execute(
                    "SELECT COUNT(*) FROM EMAIL_OUTBOX WHERE deduplication_key LIKE ?",
                    (f"us10:contract:{contract_id}:%",),
                ).fetchone()[0]
            self.assertEqual(record[0], "PENDING_CONFIRMATION")
            self.assertEqual([row[0] for row in history], ["UPLOADED"])
            self.assertEqual(decision_notifications, 0)
            self.assertEqual(decision_emails, 0)
        finally:
            with sqlite3.connect(self.db_path) as db:
                db.execute("DROP TRIGGER IF EXISTS fail_us10_outbox_insert")

    def test_us10_decision_requires_approved_profile_and_valid_pdf(self):
        suffix = str(time.time_ns())
        missing_file_intern = self.create_contract_intern(f"us10-missing.{suffix}")
        corrupt_file_intern = self.create_contract_intern(f"us10-corrupt.{suffix}")
        invalid_profile_intern = self.create_contract_intern(f"us10-profile.{suffix}")
        admin_token, _ = self.login("admin@internship.vn")
        intern_tokens = [self.login(item["email"])[0] for item in (
            missing_file_intern, corrupt_file_intern, invalid_profile_intern,
        )]
        contracts = []
        for intern in (missing_file_intern, corrupt_file_intern, invalid_profile_intern):
            status_code, contract, _ = self.upload_contract(admin_token, intern["profile_id"])
            self.assertEqual(status_code, 201, contract)
            contracts.append(contract)

        db = sqlite3.connect(self.db_path)
        try:
            storage_keys = [db.execute(
                "SELECT storage_key FROM HOP_DONG_THUC_TAP WHERE ma_hop_dong=?",
                (contract["ma_hop_dong"],),
            ).fetchone()[0] for contract in contracts]
            db.execute(
                "UPDATE HO_SO_THUC_TAP SET trang_thai_xet_duyet='TuChoi' WHERE ma_ho_so=?",
                (invalid_profile_intern["profile_id"],),
            )
            db.commit()
        finally:
            db.close()

        upload_dir = self.temp_path / "uploads" / "contracts"
        (upload_dir / storage_keys[0]).unlink()
        (upload_dir / storage_keys[1]).write_bytes(b"corrupt")
        status_code, _, _ = self.json_request(
            f"/api/contracts/{contracts[0]['ma_hop_dong']}/confirm", "POST", token=intern_tokens[0],
        )
        self.assertEqual(status_code, 404)
        status_code, _, _ = self.json_request(
            f"/api/contracts/{contracts[1]['ma_hop_dong']}/confirm", "POST", token=intern_tokens[1],
        )
        self.assertEqual(status_code, 409)
        status_code, _, _ = self.json_request(
            f"/api/contracts/{contracts[2]['ma_hop_dong']}/reject", "POST", token=intern_tokens[2],
            data={"reason": "Hồ sơ không còn được duyệt."},
        )
        self.assertEqual(status_code, 409)

        db = sqlite3.connect(self.db_path)
        try:
            states = [row[0] for row in db.execute(
                "SELECT trang_thai FROM HOP_DONG_THUC_TAP WHERE ma_hop_dong IN (?, ?, ?) ORDER BY ma_hop_dong",
                tuple(contract["ma_hop_dong"] for contract in contracts),
            )]
            decisions = db.execute(
                "SELECT COUNT(*) FROM HOP_DONG_THUC_TAP_LICH_SU WHERE action IN ('CONFIRMED', 'REJECTED') AND ma_hop_dong IN (?, ?, ?)",
                tuple(contract["ma_hop_dong"] for contract in contracts),
            ).fetchone()[0]
        finally:
            db.close()
        self.assertEqual(states, ["PENDING_CONFIRMATION"] * 3)
        self.assertEqual(decisions, 0)

    def test_us09_contract_upload_enforces_role_approval_and_pdf_validation(self):
        suffix = str(time.time_ns())
        approved = self.create_contract_intern(f"approved.{suffix}")
        pending = self.create_contract_intern(f"pending.{suffix}", approval="ChoDuyet")
        admin_token, _ = self.login("admin@internship.vn")
        tts_token, _ = self.login(approved["email"])
        mentor_token, _ = self.login("mentor@internship.vn")

        status_code, _, _ = self.upload_contract(None, approved["profile_id"])
        self.assertEqual(status_code, 401)
        status_code, _, _ = self.upload_contract(tts_token, approved["profile_id"])
        self.assertEqual(status_code, 403)
        status_code, _, _ = self.upload_contract(mentor_token, approved["profile_id"])
        self.assertEqual(status_code, 403)
        status_code, _, _ = self.upload_contract(admin_token, 99999999)
        self.assertEqual(status_code, 404)
        status_code, _, _ = self.upload_contract(admin_token, pending["profile_id"])
        self.assertEqual(status_code, 409)
        status_code, _, _ = self.upload_contract(admin_token, approved["profile_id"], filename="..\\..\\contract.pdf")
        self.assertEqual(status_code, 400)
        status_code, _, _ = self.upload_contract(admin_token, approved["profile_id"], content=b"not really a PDF")
        self.assertEqual(status_code, 400)
        status_code, _, _ = self.upload_contract(admin_token, approved["profile_id"], mime_type="text/plain")
        self.assertEqual(status_code, 400)
        status_code, _, _ = self.upload_contract(
            admin_token, approved["profile_id"], content=b"%PDF-" + b"x" * (15 * 1024 * 1024),
        )
        self.assertEqual(status_code, 400)

        db = sqlite3.connect(self.db_path)
        try:
            existing_keys = {row[0] for row in db.execute("SELECT storage_key FROM HOP_DONG_THUC_TAP")}
            db.execute("""
                CREATE TRIGGER fail_us09_contract_insert
                BEFORE INSERT ON HOP_DONG_THUC_TAP
                BEGIN SELECT RAISE(ABORT, 'forced isolated-test database failure'); END
            """)
            db.commit()
        finally:
            db.close()
        status_code, _, _ = self.upload_contract(admin_token, approved["profile_id"])
        self.assertEqual(status_code, 409)
        storage_dir = self.temp_path / "uploads" / "contracts"
        stored_keys = {path.name for path in storage_dir.glob("*.pdf")}
        self.assertEqual(stored_keys, existing_keys)
        db = sqlite3.connect(self.db_path)
        try:
            db.execute("DROP TRIGGER fail_us09_contract_insert")
            db.commit()
        finally:
            db.close()

    def test_us14_personal_schedule_is_session_scoped_and_week_filtered(self):
        suffix = str(time.time_ns())
        intern_a = self.create_contract_intern(f"us14-a.{suffix}")
        intern_b = self.create_contract_intern(f"us14-b.{suffix}")
        empty_intern = self.create_contract_intern(f"us14-empty.{suffix}")
        admin_token, admin = self.login("admin@internship.vn")
        mentor = self.login("mentor@internship.vn")[1]

        db = sqlite3.connect(self.db_path)
        try:
            program_a = db.execute("""
                INSERT INTO CHUONG_TRINH_THUC_TAP
                    (ma_ct, ten_ct, ma_phong_ban, ngay_bat_dau, ngay_ket_thuc, chi_tieu, trang_thai)
                VALUES (?, 'US14 Backend Internship', 1, '2026-09-28', '2026-10-04', 2, 'DangMo')
            """, (f"US14-A-{suffix}",)).lastrowid
            program_b = db.execute("""
                INSERT INTO CHUONG_TRINH_THUC_TAP
                    (ma_ct, ten_ct, ma_phong_ban, ngay_bat_dau, ngay_ket_thuc, chi_tieu, trang_thai)
                VALUES (?, 'US14 Data Internship', 2, '2026-10-05', '2026-10-11', 2, 'DangMo')
            """, (f"US14-B-{suffix}",)).lastrowid
            closed_program = db.execute("""
                INSERT INTO CHUONG_TRINH_THUC_TAP
                    (ma_ct, ten_ct, ma_phong_ban, ngay_bat_dau, ngay_ket_thuc, chi_tieu, trang_thai)
                VALUES (?, 'US14 Closed Internship', 1, '2026-09-28', '2026-10-04', 2, 'DaDong')
            """, (f"US14-CLOSED-{suffix}",)).lastrowid
            for program_id, intern in (
                (program_a, intern_a),
                (program_b, intern_b),
                (closed_program, intern_a),
            ):
                db.execute("""
                    INSERT INTO UNG_TUYEN_CHUONG_TRINH
                        (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet, nguoi_xet_duyet)
                    VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP, ?)
                """, (program_id, intern["profile_id"], admin["ma_nguoi_dung"]))
            db.execute("""
                INSERT INTO PHAN_CONG_MENTOR_TTS
                    (ma_nguoi_dung_mentor, ma_ho_so, ma_nguoi_phan_cong)
                VALUES (?, ?, ?)
            """, (mentor["ma_nguoi_dung"], intern_a["profile_id"], admin["ma_nguoi_dung"]))
            db.commit()
        finally:
            db.close()

        intern_a_token, _ = self.login(intern_a["email"])
        intern_b_token, _ = self.login(intern_b["email"])
        mentor_token, _ = self.login("mentor@internship.vn")

        status_code, _, _ = self.json_request("/api/interns/me/schedule")
        self.assertEqual(status_code, 401)
        status_code, _, _ = self.json_request("/api/interns/me/schedule", token=admin_token)
        self.assertEqual(status_code, 403)
        status_code, _, _ = self.json_request("/api/interns/me/schedule", token=mentor_token)
        self.assertEqual(status_code, 403)

        status_code, schedule, _ = self.json_request(
            f"/api/interns/me/schedule?week_start=2026-09-30&student_id={intern_b['user_id']}&user_id={intern_b['user_id']}",
            token=intern_a_token,
        )
        self.assertEqual(status_code, 200, schedule)
        self.assertEqual(schedule["week"], {"start_date": "2026-09-28", "end_date": "2026-10-04"})
        self.assertEqual(len(schedule["events"]), 1)
        event = schedule["events"][0]
        self.assertEqual(event["type"], "PROGRAM_PERIOD")
        self.assertEqual(event["status"], "APPROVED")
        self.assertEqual((event["program"]["id"], event["program"]["name"]), (program_a, "US14 Backend Internship"))
        self.assertEqual((event["start_date"], event["end_date"], event["all_day"]), ("2026-09-28", "2026-10-04", True))
        self.assertEqual(event["mentor"]["name"], mentor["ho_ten"])
        self.assertNotIn("terms", schedule["filters"])
        self.assertNotIn("location", event)
        self.assertNotIn("meeting_url", event)
        self.assertNotIn("department", event)
        self.assertNotIn("ma_nguoi_dung", event)
        self.assertNotIn("ma_ho_so", event)

        status_code, program_schedule, _ = self.json_request(
            f"/api/interns/me/schedule?week_start=2026-09-28&program_id={program_a}",
            token=intern_a_token,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(len(program_schedule["events"]), 1)
        self.assertEqual(
            [program["id"] for program in program_schedule["filters"]["programs"]],
            [program_a],
        )

        status_code, closed_schedule, _ = self.json_request(
            f"/api/interns/me/schedule?week_start=2026-09-28&program_id={closed_program}",
            token=intern_a_token,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(closed_schedule["events"], [])
        self.assertEqual(closed_schedule["filters"]["programs"], [])
        self.assertFalse(closed_schedule["has_program"])
        self.assertFalse(closed_schedule["mentor_assignment_pending"])

        status_code, next_week, _ = self.json_request(
            "/api/interns/me/schedule?week_start=2026-10-05", token=intern_a_token,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(next_week["events"], [])
        status_code, other_schedule, _ = self.json_request(
            "/api/interns/me/schedule?week_start=2026-10-05", token=intern_b_token,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(other_schedule["events"][0]["program"]["id"], program_b)
        self.assertTrue(other_schedule["has_program"])
        self.assertFalse(other_schedule["has_mentor"])
        self.assertTrue(other_schedule["mentor_assignment_pending"])

        status_code, empty_schedule, _ = self.json_request(
            "/api/interns/me/schedule?week_start=2026-09-28", token=self.login(empty_intern["email"])[0],
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(empty_schedule["events"], [])
        self.assertFalse(empty_schedule["has_program"])
        self.assertFalse(empty_schedule["mentor_assignment_pending"])

if __name__ == "__main__":
    unittest.main()
