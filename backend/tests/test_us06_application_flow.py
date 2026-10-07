import asyncio
import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, UploadFile
from app import database
from app.routes import auth_routes, intern_routes, program_routes
from app.schemas import UserRegister


def make_request(user=None, ip="127.0.0.1"):
    return SimpleNamespace(
        state=SimpleNamespace(current_user=user),
        client=SimpleNamespace(host=ip),
    )


VALID_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


class US06ApplicationFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us06-")
        cls.db_path = Path(cls.temp_dir.name) / "us06.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        cls.auth_upload_patch = patch.object(auth_routes, "UPLOAD_ROOT", Path(cls.temp_dir.name) / "auth-uploads")
        cls.program_upload_patch = patch.object(program_routes, "UPLOAD_ROOT", Path(cls.temp_dir.name) / "program-uploads")
        cls.auth_upload_patch.start()
        cls.program_upload_patch.start()
        database.init_db()

        cls.http_app = FastAPI()

        @cls.http_app.middleware("http")
        async def add_test_identity(request, call_next):
            request.state.current_user = request.scope.get("state", {}).get("test_user")
            return await call_next(request)

        async def override_db():
            yield cls.active_db

        cls.http_app.dependency_overrides[database.get_db] = override_db
        cls.http_app.include_router(auth_routes.router)
        cls.http_app.include_router(program_routes.router)
        cls.http_app.include_router(intern_routes.router)
        cls.active_db = None

        db = database.get_db_connection()
        dept = db.execute("SELECT ma_phong_ban FROM PHONG_BAN ORDER BY ma_phong_ban LIMIT 1").fetchone()
        cls.dept_id = dept["ma_phong_ban"] if dept else 1

        # Seed an admin
        admin_row = db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro='Admin' LIMIT 1").fetchone()
        if not admin_row:
            cur = db.execute("""
                INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
                VALUES ('Admin User', 'admin.us06@example.com', 'dummy', 'Admin', 'HoatDong')
            """)
            cls.admin_id = cur.lastrowid
        else:
            cls.admin_id = admin_row["ma_nguoi_dung"]

        # Seed a mentor
        mentor_row = db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro='Mentor' LIMIT 1").fetchone()
        if not mentor_row:
            cur = db.execute("""
                INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
                VALUES ('Mentor User', 'mentor.us06@example.com', 'dummy', 'Mentor', 'HoatDong')
            """)
            cls.mentor_id = cur.lastrowid
        else:
            cls.mentor_id = mentor_row["ma_nguoi_dung"]

        # Seed an open program and a closed program
        c1 = db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, ma_phong_ban, chi_tieu, trang_thai)
            VALUES ('US06-OPEN-1', 'US06 Open Program 1', ?, 5, 'DangMo')
        """, (cls.dept_id,))
        cls.open_prog_id = c1.lastrowid

        c2 = db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, ma_phong_ban, chi_tieu, trang_thai)
            VALUES ('US06-CLOSED-1', 'US06 Closed Program 1', ?, 5, 'DaDong')
        """, (cls.dept_id,))
        cls.closed_prog_id = c2.lastrowid

        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        cls.program_upload_patch.stop()
        cls.auth_upload_patch.stop()
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()

    def tearDown(self):
        self.db.close()

    @staticmethod
    def _multipart(fields, file=None):
        boundary = "us06-test-boundary"
        chunks = []
        for name, value in fields.items():
            chunks.extend([
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode(),
                b"\r\n",
            ])
        if file is not None:
            name, filename, content_type, content = file
            chunks.extend([
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ])
        chunks.append(f"--{boundary}--\r\n".encode())
        return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

    async def _asgi_request_async(self, method, path, user=None, body=b"", content_type=None):
        headers = [(b"host", b"testserver"), (b"content-length", str(len(body)).encode())]
        if content_type:
            headers.append((b"content-type", content_type.encode()))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "state": {"test_user": user},
        }
        request_sent = False
        events = []

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(event):
            events.append(event)

        await self.http_app(scope, receive, send)
        response_start = next(event for event in events if event["type"] == "http.response.start")
        response_body = b"".join(
            event.get("body", b"") for event in events if event["type"] == "http.response.body"
        )
        parsed = json.loads(response_body) if response_body else None
        return response_start["status"], parsed

    def _http_request(self, method, path, user=None, body=b"", content_type=None):
        type(self).active_db = self.db
        return asyncio.run(self._asgi_request_async(method, path, user, body, content_type))

    def _create_tts_user(self, email_prefix="tts"):
        unique_id = os.urandom(4).hex()
        email = f"{email_prefix}.{unique_id}@student.edu.vn"
        phone = f"09{int(unique_id, 16) % 90000000 + 10000000}"
        cursor = self.db.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, so_dien_thoai, vai_tro, trang_thai)
            VALUES (?, ?, 'hashed_pw', ?, 'ThucTapSinh', 'HoatDong')
        """, (f"Student {unique_id}", email, phone))
        user_id = cursor.lastrowid
        c_prof = self.db.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet)
            VALUES (?, 'CNTT', 'ChoDuyet')
        """, (user_id,))
        profile_id = c_prof.lastrowid
        self.db.commit()
        user_dict = {
            "ma_nguoi_dung": user_id,
            "ho_ten": f"Student {unique_id}",
            "email": email,
            "so_dien_thoai": phone,
            "vai_tro": "ThucTapSinh",
            "trang_thai": "HoatDong",
            "ma_ho_so": profile_id,
        }
        return user_dict, profile_id

    # ---------------------------------------------------------
    # 1. Registration tests
    # ---------------------------------------------------------
    def test_tts_registration_default_role_and_pending_status(self):
        unique = os.urandom(4).hex()
        data = UserRegister(
            ho_ten="Nguyen Van Test",
            email=f"register.{unique}@student.vn",
            so_dien_thoai="0912345678",
            vai_tro="Admin",  # Client attempts to escalate role
            ma_phong_ban=self.dept_id,
        )
        req = make_request()
        res = auth_routes.register_user(data, req, self.db)

        self.assertEqual(res["vai_tro"], "ThucTapSinh")
        self.assertEqual(res["trang_thai"], "ChoDuyet")
        self.assertNotIn("mat_khau", res)
        self.assertNotIn("password", res)

        # Verify DB row
        user_row = self.db.execute(
            "SELECT vai_tro, trang_thai FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?",
            (res["ma_nguoi_dung"],),
        ).fetchone()
        self.assertEqual(user_row["vai_tro"], "ThucTapSinh")
        self.assertEqual(user_row["trang_thai"], "ChoDuyet")

        # Verify HO_SO_THUC_TAP row created
        prof = self.db.execute(
            "SELECT ma_ho_so, trang_thai_xet_duyet FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung = ?",
            (res["ma_nguoi_dung"],),
        ).fetchone()
        self.assertIsNotNone(prof)
        self.assertEqual(prof["trang_thai_xet_duyet"], "ChoDuyet")

    def test_tts_registration_duplicate_email_returns_conflict(self):
        unique = os.urandom(4).hex()
        email = f"dup.{unique}@student.vn"
        data1 = UserRegister(ho_ten="User One", email=email, so_dien_thoai="0911223344")
        auth_routes.register_user(data1, make_request(), self.db)

        data2 = UserRegister(ho_ten="User Two", email=email, so_dien_thoai="0955667788")
        with self.assertRaises(HTTPException) as ctx:
            auth_routes.register_user(data2, make_request(), self.db)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Email", ctx.exception.detail)

    def test_tts_registration_duplicate_phone_returns_conflict(self):
        unique = os.urandom(4).hex()
        phone = "09" + str(10000000 + int(unique, 16) % 89999999)
        auth_routes.register_user(
            UserRegister(ho_ten="Phone One", email=f"phone1.{unique}@student.vn", so_dien_thoai=phone),
            make_request(), self.db,
        )
        with self.assertRaises(HTTPException) as ctx:
            auth_routes.register_user(
                UserRegister(ho_ten="Phone Two", email=f"phone2.{unique}@student.vn", so_dien_thoai=phone),
                make_request(), self.db,
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Số điện thoại", ctx.exception.detail)

    def test_register_with_cv_http_conflicts_and_race_are_normalized(self):
        unique = os.urandom(4).hex()
        first_email = f"http-register.{unique}@student.vn"
        first_phone = "09" + str(10000000 + int(unique, 16) % 89999999)
        first_body, content_type = self._multipart({
            "ho_ten": "HTTP Candidate",
            "email": first_email,
            "so_dien_thoai": first_phone,
        })
        status_code, result = self._http_request(
            "POST", "/api/auth/register-with-cv", body=first_body, content_type=content_type,
        )
        self.assertEqual(status_code, 201, result)

        duplicate_email_body, content_type = self._multipart({
            "ho_ten": "Duplicate Email",
            "email": first_email.upper(),
            "so_dien_thoai": "0933445566",
        })
        status_code, result = self._http_request(
            "POST", "/api/auth/register-with-cv", body=duplicate_email_body, content_type=content_type,
        )
        self.assertEqual(status_code, 409, result)
        self.assertIn("Email", result["detail"])

        duplicate_phone_body, content_type = self._multipart({
            "ho_ten": "Duplicate Phone",
            "email": f"phone-http.{unique}@student.vn",
            "so_dien_thoai": first_phone,
        })
        status_code, result = self._http_request(
            "POST", "/api/auth/register-with-cv", body=duplicate_phone_body, content_type=content_type,
        )
        self.assertEqual(status_code, 409, result)
        self.assertIn("Số điện thoại", result["detail"])

        race_email = f"race-http.{unique}@student.vn"
        self.db.execute("""
            CREATE TRIGGER us06_registration_email_race
            BEFORE INSERT ON NGUOI_DUNG
            WHEN NEW.email LIKE 'race-http.%@student.vn'
            BEGIN
                INSERT INTO NGUOI_DUNG
                    (ma_phong_ban, ho_ten, email, mat_khau, must_change_password, so_dien_thoai, vai_tro, trang_thai)
                VALUES (NULL, 'Concurrent Candidate', NEW.email, 'fixture', 1, NULL, 'ThucTapSinh', 'ChoDuyet');
            END;
        """)
        self.db.commit()
        race_body, content_type = self._multipart({
            "ho_ten": "Race Candidate",
            "email": race_email,
            "so_dien_thoai": "0933445599",
        })
        status_code, result = self._http_request(
            "POST", "/api/auth/register-with-cv", body=race_body, content_type=content_type,
        )
        self.db.execute("DROP TRIGGER us06_registration_email_race")
        self.db.commit()
        self.assertEqual(status_code, 409, result)
        self.assertNotIn("UNIQUE constraint", result["detail"])
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM NGUOI_DUNG WHERE email = ?", (race_email,)).fetchone()[0],
            0,
        )

    def test_tts_registration_with_cv_upload(self):
        unique = os.urandom(4).hex()
        email = f"cvreg.{unique}@student.vn"
        cv_file = UploadFile(
            file=io.BytesIO(VALID_PDF_BYTES),
            filename=f"cv_{unique}.pdf",
        )
        req = make_request()
        res = asyncio.run(auth_routes.register_user_with_cv(
            request=req,
            ho_ten="Candidate With CV",
            email=email,
            so_dien_thoai="0988776655",
            cv=cv_file,
            db=self.db,
        ))
        self.assertEqual(res["vai_tro"], "ThucTapSinh")
        self.assertTrue(res["cv_da_nop"])

        # Verify TAI_LIEU_HO_SO
        user_id = res["ma_nguoi_dung"]
        doc = self.db.execute("""
            SELECT d.loai_tai_lieu, d.trang_thai_duyet, d.ten_file
            FROM TAI_LIEU_HO_SO d
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = d.ma_ho_so
            WHERE h.ma_nguoi_dung = ?
        """, (user_id,)).fetchone()
        self.assertIsNotNone(doc)
        self.assertEqual(doc["loai_tai_lieu"], "CV")
        self.assertEqual(doc["trang_thai_duyet"], "ChoDuyet")

    # ---------------------------------------------------------
    # 2. Application authorization & boundaries tests
    # ---------------------------------------------------------
    def test_apply_requires_authenticated_tts(self):
        cv = UploadFile(file=io.BytesIO(VALID_PDF_BYTES), filename="test.pdf")

        # Anonymous -> 401
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(program_routes.apply_to_program(
                program_id=self.open_prog_id,
                request=make_request(None),
                cv=cv,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 401)

        # Mentor -> 403
        mentor_user = {"ma_nguoi_dung": self.mentor_id, "vai_tro": "Mentor"}
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(program_routes.apply_to_program(
                program_id=self.open_prog_id,
                request=make_request(mentor_user),
                cv=cv,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 403)

        # Admin -> 403
        admin_user = {"ma_nguoi_dung": self.admin_id, "vai_tro": "Admin"}
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(program_routes.apply_to_program(
                program_id=self.open_prog_id,
                request=make_request(admin_user),
                cv=cv,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_apply_to_nonexistent_or_closed_program(self):
        tts_user, _ = self._create_tts_user()
        cv = UploadFile(file=io.BytesIO(VALID_PDF_BYTES), filename="cv.pdf")

        # Nonexistent program -> 404
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(program_routes.apply_to_program(
                program_id=999999,
                request=make_request(tts_user),
                cv=cv,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 404)

        # Closed program -> 400
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(program_routes.apply_to_program(
                program_id=self.closed_prog_id,
                request=make_request(tts_user),
                cv=cv,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("ngừng nhận hồ sơ", ctx.exception.detail)

    # ---------------------------------------------------------
    # 3. Application submission, file validation & approved profile reuse
    # ---------------------------------------------------------
    def test_apply_with_new_cv_success_and_notifications(self):
        tts_user, profile_id = self._create_tts_user("apply1")
        cv = UploadFile(file=io.BytesIO(VALID_PDF_BYTES), filename="fresh_cv.pdf")

        res = asyncio.run(program_routes.apply_to_program(
            program_id=self.open_prog_id,
            request=make_request(tts_user),
            cv=cv,
            use_approved_profile=False,
            db=self.db,
        ))
        self.assertEqual(res["trang_thai"], "ChoDuyet")
        self.assertIn("ma_ung_tuyen", res)

        # Verify application row in DB
        app_row = self.db.execute("""
            SELECT trang_thai, ma_ho_so, ma_chuong_trinh
            FROM UNG_TUYEN_CHUONG_TRINH
            WHERE ma_ung_tuyen = ?
        """, (res["ma_ung_tuyen"],)).fetchone()
        self.assertEqual(app_row["trang_thai"], "ChoDuyet")
        self.assertEqual(app_row["ma_ho_so"], profile_id)
        self.assertEqual(app_row["ma_chuong_trinh"], self.open_prog_id)

        # The application page already confirms success; only HR receives a persistent notification.
        notif = self.db.execute("""
            SELECT tieu_de FROM THONG_BAO
            WHERE ma_nguoi_dung = ? AND tieu_de = 'Nộp hồ sơ ứng tuyển thành công'
        """, (tts_user["ma_nguoi_dung"],)).fetchone()
        self.assertIsNone(notif)
        manager_notif = self.db.execute("""
            SELECT 1 FROM THONG_BAO
            WHERE tieu_de = 'Ứng viên chương trình mới'
            LIMIT 1
        """).fetchone()
        self.assertIsNotNone(manager_notif)

    def test_apply_with_invalid_cv_rejected(self):
        tts_user, _ = self._create_tts_user("badcv")

        # Wrong extension (.exe)
        bad_ext = UploadFile(file=io.BytesIO(b"executable"), filename="virus.exe")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(program_routes.apply_to_program(
                program_id=self.open_prog_id,
                request=make_request(tts_user),
                cv=bad_ext,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 400)

        # Invalid content (pretending to be PDF)
        fake_pdf = UploadFile(file=io.BytesIO(b"not a real pdf"), filename="fake.pdf")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(program_routes.apply_to_program(
                program_id=self.open_prog_id,
                request=make_request(tts_user),
                cv=fake_pdf,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("không khớp", ctx.exception.detail)

    def test_apply_with_approved_profile_requires_approval(self):
        tts_user, profile_id = self._create_tts_user("appr")

        # Profile is ChoDuyet -> cannot reuse
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(program_routes.apply_to_program(
                program_id=self.open_prog_id,
                request=make_request(tts_user),
                cv=None,
                use_approved_profile=True,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("chưa được duyệt", ctx.exception.detail)

        # Now approve profile, but no approved CV exists yet
        self.db.execute("UPDATE HO_SO_THUC_TAP SET trang_thai_xet_duyet='DaDuyet' WHERE ma_ho_so=?", (profile_id,))
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(program_routes.apply_to_program(
                program_id=self.open_prog_id,
                request=make_request(tts_user),
                cv=None,
                use_approved_profile=True,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("chưa có CV được duyệt", ctx.exception.detail)

        # Now add approved CV
        self.db.execute("""
            INSERT INTO TAI_LIEU_HO_SO (ma_ho_so, loai_tai_lieu, duong_dan_file, ten_file, kich_thuoc, trang_thai_duyet)
            VALUES (?, 'CV', 'documents/test.pdf', 'my_approved.pdf', 1024, 'DaDuyet')
        """, (profile_id,))
        self.db.commit()

        # Now reuse approved profile succeeds
        res = asyncio.run(program_routes.apply_to_program(
            program_id=self.open_prog_id,
            request=make_request(tts_user),
            cv=None,
            use_approved_profile=True,
            db=self.db,
        ))
        self.assertEqual(res["trang_thai"], "ChoDuyet")
        self.assertTrue(res["su_dung_ho_so_da_duyet"])

    # ---------------------------------------------------------
    # 4. Duplicate protection & concurrency tests
    # ---------------------------------------------------------
    def test_duplicate_apply_to_same_program_blocked(self):
        tts_user, _ = self._create_tts_user("dupapply")
        cv1 = UploadFile(file=io.BytesIO(VALID_PDF_BYTES), filename="cv1.pdf")
        asyncio.run(program_routes.apply_to_program(
            program_id=self.open_prog_id,
            request=make_request(tts_user),
            cv=cv1,
            db=self.db,
        ))

        # Attempt second apply to the same program
        cv2 = UploadFile(file=io.BytesIO(VALID_PDF_BYTES), filename="cv2.pdf")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(program_routes.apply_to_program(
                program_id=self.open_prog_id,
                request=make_request(tts_user),
                cv=cv2,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("đã ứng tuyển chương trình này", ctx.exception.detail)

    def test_concurrent_apply_allows_only_one_submission(self):
        tts_user, profile_id = self._create_tts_user("concurrent")

        # Create a new program specifically for concurrent test
        c = self.db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, ma_phong_ban, chi_tieu, trang_thai)
            VALUES ('US06-CONCURRENT', 'Concurrent Test Prog', ?, 10, 'DangMo')
        """, (self.dept_id,))
        prog_id = c.lastrowid
        self.db.commit()

        results = []
        errors = []

        def worker():
            db_conn = database.get_db_connection()
            cv = UploadFile(file=io.BytesIO(VALID_PDF_BYTES), filename="cv_c.pdf")
            try:
                res = asyncio.run(program_routes.apply_to_program(
                    program_id=prog_id,
                    request=make_request(tts_user),
                    cv=cv,
                    db=db_conn,
                ))
                results.append(res)
            except HTTPException as e:
                errors.append(e)
            finally:
                db_conn.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker)
            f2 = executor.submit(worker)
            f1.result()
            f2.result()

        self.assertEqual(len(results), 1, "Exactly one concurrent apply must succeed")
        self.assertEqual(len(errors), 1, "The second concurrent apply must be rejected")
        self.assertEqual(errors[0].status_code, 400)

        # Database must have exactly one row
        count = self.db.execute("""
            SELECT COUNT(*) AS total FROM UNG_TUYEN_CHUONG_TRINH
            WHERE ma_chuong_trinh = ? AND ma_ho_so = ?
        """, (prog_id, profile_id)).fetchone()["total"]
        self.assertEqual(count, 1)

    # ---------------------------------------------------------
    # 5. IDOR & application status isolation tests
    # ---------------------------------------------------------
    def test_tts_status_visibility_is_scoped_to_current_user(self):
        tts_a, prof_a = self._create_tts_user("user_a")
        tts_b, prof_b = self._create_tts_user("user_b")

        # Create 2 distinct open programs
        p1 = self.db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, ma_phong_ban, chi_tieu, trang_thai)
            VALUES ('US06-PROG-A', 'Program A', ?, 5, 'DangMo')
        """, (self.dept_id,)).lastrowid
        p2 = self.db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, ma_phong_ban, chi_tieu, trang_thai)
            VALUES ('US06-PROG-B', 'Program B', ?, 5, 'DangMo')
        """, (self.dept_id,)).lastrowid
        self.db.commit()

        # Apply through the URL used by the frontend.
        for user, program_id, filename in (
            (tts_a, p1, "cv_a.pdf"),
            (tts_b, p2, "cv_b.pdf"),
        ):
            body, content_type = self._multipart(
                {"use_approved_profile": "false"},
                ("cv", filename, "application/pdf", VALID_PDF_BYTES),
            )
            status_code, result = self._http_request(
                "POST", f"/api/programs/{program_id}/apply", user=user,
                body=body, content_type=content_type,
            )
            self.assertEqual(status_code, 201, result)
            self.assertEqual(result["trang_thai"], "ChoDuyet")

        # Program list and intern workspace are the existing frontend status surfaces.
        status_code, progs_view_a = self._http_request("GET", "/api/programs", user=tts_a)
        self.assertEqual(status_code, 200, progs_view_a)
        p1_for_a = next((p for p in progs_view_a if p["ma_chuong_trinh"] == p1), None)
        p2_for_a = next((p for p in progs_view_a if p["ma_chuong_trinh"] == p2), None)
        self.assertEqual(p1_for_a["trang_thai_ung_tuyen"], "ChoDuyet")
        self.assertIsNone(p2_for_a["trang_thai_ung_tuyen"])

        status_code, progs_view_b = self._http_request("GET", "/api/programs", user=tts_b)
        self.assertEqual(status_code, 200, progs_view_b)
        p1_for_b = next((p for p in progs_view_b if p["ma_chuong_trinh"] == p1), None)
        p2_for_b = next((p for p in progs_view_b if p["ma_chuong_trinh"] == p2), None)
        self.assertIsNone(p1_for_b["trang_thai_ung_tuyen"])
        self.assertEqual(p2_for_b["trang_thai_ung_tuyen"], "ChoDuyet")

        status_code, ws_a = self._http_request("GET", "/api/interns/me/workspace", user=tts_a)
        self.assertEqual(status_code, 200, ws_a)
        self.assertEqual(len(ws_a["applications"]), 1)
        self.assertEqual(ws_a["applications"][0]["ma_chuong_trinh"], p1)
        self.assertEqual(ws_a["applications"][0]["trang_thai_ung_tuyen"], "ChoDuyet")
        self.assertNotIn("ma_ung_tuyen", ws_a["applications"][0])

        status_code, ws_b = self._http_request("GET", "/api/interns/me/workspace", user=tts_b)
        self.assertEqual(status_code, 200, ws_b)
        self.assertEqual(len(ws_b["applications"]), 1)
        self.assertEqual(ws_b["applications"][0]["ma_chuong_trinh"], p2)
        self.assertNotIn("ma_ung_tuyen", ws_b["applications"][0])


if __name__ == "__main__":
    unittest.main()
