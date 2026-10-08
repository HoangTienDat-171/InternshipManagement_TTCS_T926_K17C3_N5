import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from starlette.datastructures import FormData, UploadFile

from app import database
from app.leave_service import LeaveService, get_approved_leaves_for_profile
from app.routes import leave_routes
from app.schemas import LeaveRequestCreate, LeaveRequestReview


def request_for(user=None):
    return SimpleNamespace(state=SimpleNamespace(current_user=user))


class _AsyncFormContext:
    def __init__(self, form):
        self.form = form

    async def __aenter__(self):
        return self.form

    async def __aexit__(self, exc_type, exc, traceback):
        await self.form.close()


class LeaveRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us24-")
        cls.db_path = Path(cls.temp_dir.name) / "us24.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()

        # Set up ASGI test app
        cls.http_app = FastAPI()

        async def add_test_identity(request, call_next):
            test_user = request.scope.get("state", {}).get("test_user")
            request.state.current_user = test_user
            return await call_next(request)

        async def override_db():
            yield cls.active_db

        cls.http_app.middleware("http")(add_test_identity)
        cls.http_app.dependency_overrides[database.get_db] = override_db
        cls.http_app.include_router(leave_routes.router)
        cls.active_db = None

        db = database.get_db_connection()

        # Admin & HR
        admin_cur = db.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES ('Admin US24', 'admin.us24@example.test', 'hash', 'Admin', 'HoatDong')
        """)
        cls.admin_id = admin_cur.lastrowid
        cls.admin = {"ma_nguoi_dung": cls.admin_id, "vai_tro": "Admin", "ho_ten": "Admin US24"}

        hr_cur = db.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES ('HR US24', 'hr.us24@example.test', 'hash', 'HR', 'HoatDong')
        """)
        cls.hr_id = hr_cur.lastrowid
        cls.hr = {"ma_nguoi_dung": cls.hr_id, "vai_tro": "HR", "ho_ten": "HR US24"}

        # Mentor
        mentor_cur = db.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES ('Mentor US24', 'mentor.us24@example.test', 'hash', 'Mentor', 'HoatDong')
        """)
        cls.mentor_id = mentor_cur.lastrowid
        cls.mentor = {"ma_nguoi_dung": cls.mentor_id, "vai_tro": "Mentor", "ho_ten": "Mentor US24"}

        # Program 1 (active: 2026-10-01 to 2026-12-31)
        p1_cur = db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, chi_tieu, ngay_bat_dau, ngay_ket_thuc, trang_thai)
            VALUES ('PROG-2026-1', 'Chương trình thực tập Thu Đông 2026', 10, '2026-10-01', '2026-12-31', 'DangMo')
        """)
        cls.program_1_id = p1_cur.lastrowid

        # Program 2 (sequential/future: 2027-01-01 to 2027-03-31)
        p2_cur = db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, chi_tieu, ngay_bat_dau, ngay_ket_thuc, trang_thai)
            VALUES ('PROG-2027-1', 'Chương trình thực tập Xuân 2027', 10, '2027-01-01', '2027-03-31', 'DangMo')
        """)
        cls.program_2_id = p2_cur.lastrowid

        # Intern A
        u_a = db.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES ('TTS Nguyen Van A', 'intern.a@example.test', 'hash', 'ThucTapSinh', 'HoatDong')
        """)
        cls.intern_a_id = u_a.lastrowid
        cls.intern_a = {"ma_nguoi_dung": cls.intern_a_id, "vai_tro": "ThucTapSinh", "ho_ten": "TTS Nguyen Van A"}

        prof_a = db.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, trang_thai_xet_duyet, trang_thai_thuc_tap)
            VALUES (?, 'DaDuyet', 'DangThucTap')
        """, (cls.intern_a_id,))
        cls.profile_a_id = prof_a.lastrowid

        # Approved application for Intern A on Program 1
        app_a1 = db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet)
            VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP)
        """, (cls.program_1_id, cls.profile_a_id))
        cls.app_a1_id = app_a1.lastrowid

        # Approved applications must still be excluded when their program is future or closed.
        future_program = db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, chi_tieu, ngay_bat_dau, ngay_ket_thuc, trang_thai)
            VALUES ('PROG-FUTURE', 'Chương trình sắp tới', 10, '2026-10-09', '2026-11-30', 'DangMo')
        """)
        cls.future_program_id = future_program.lastrowid
        future_application = db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet)
            VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP)
        """, (cls.future_program_id, cls.profile_a_id))
        cls.future_application_id = future_application.lastrowid

        closed_program = db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, chi_tieu, ngay_bat_dau, ngay_ket_thuc, trang_thai)
            VALUES ('PROG-CLOSED', 'Chương trình đã đóng', 10, '2026-10-01', '2026-12-31', 'DaDong')
        """)
        cls.closed_program_id = closed_program.lastrowid
        closed_application = db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet)
            VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP)
        """, (cls.closed_program_id, cls.profile_a_id))
        cls.closed_application_id = closed_application.lastrowid

        # Intern B
        u_b = db.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES ('TTS Le Thi B', 'intern.b@example.test', 'hash', 'ThucTapSinh', 'HoatDong')
        """)
        cls.intern_b_id = u_b.lastrowid
        cls.intern_b = {"ma_nguoi_dung": cls.intern_b_id, "vai_tro": "ThucTapSinh", "ho_ten": "TTS Le Thi B"}

        prof_b = db.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, trang_thai_xet_duyet, trang_thai_thuc_tap)
            VALUES (?, 'DaDuyet', 'DangThucTap')
        """, (cls.intern_b_id,))
        cls.profile_b_id = prof_b.lastrowid

        # Approved application for Intern B on Program 1
        app_b1 = db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet)
            VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP)
        """, (cls.program_1_id, cls.profile_b_id))
        cls.app_b1_id = app_b1.lastrowid

        # Pending application for Intern B on Program 2 (Not approved yet!)
        app_b2 = db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai)
            VALUES (?, ?, 'ChoDuyet')
        """, (cls.program_2_id, cls.profile_b_id))
        cls.app_b2_pending_id = app_b2.lastrowid

        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()
        self.__class__.active_db = self.db
        self.db.execute("DELETE FROM YEU_CAU_NGHI_PHEP")
        self.db.commit()
        self.service = LeaveService(self.db)

    def tearDown(self):
        self.__class__.active_db = None
        self.db.close()

    def _asgi_request(self, method, path, user=None, json_body=None):
        body_bytes = json.dumps(json_body).encode("utf-8") if json_body is not None else b""
        headers = [(b"host", b"testserver"), (b"content-length", str(len(body_bytes)).encode())]
        if json_body is not None:
            headers.append((b"content-type", b"application/json"))

        clean_path, _, qs = path.partition("?")
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": clean_path,
            "raw_path": clean_path.encode(),
            "query_string": qs.encode("utf-8"),
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "state": {"test_user": user},
        }

        response_meta = {}
        response_body = bytearray()

        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                response_meta["status"] = message["status"]
                response_meta["headers"] = dict(message.get("headers", []))
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))

        asyncio.run(self.http_app(scope, receive, send))

        raw_data = bytes(response_body).decode("utf-8")
        try:
            parsed = json.loads(raw_data) if raw_data else None
        except Exception:
            parsed = raw_data
        return response_meta.get("status", 500), parsed

    def _multipart_request(self, files, user=None, application_id=None):
        form_values = [
            ("ma_ung_tuyen", str(application_id or self.app_a1_id)),
            ("start_date", "2026-10-15"),
            ("end_date", "2026-10-16"),
            ("ly_do", "Xin nghỉ phép để kiểm tra minh chứng tải lên"),
        ]
        form_values.extend(
            ("files", UploadFile(filename=name, file=BytesIO(content)))
            for name, content in files
        )
        form = FormData(form_values)
        return SimpleNamespace(
            headers={"content-type": "multipart/form-data; boundary=us24-test"},
            state=SimpleNamespace(current_user=user or self.intern_a),
            form=lambda: _AsyncFormContext(form),
        )

    # ================= 1. CREATE VALID LEAVE =================
    def test_create_valid_own_request(self):
        payload = {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-10-15",
            "end_date": "2026-10-16",
            "ly_do": "  Bận việc gia đình có xin phép mentor  ",
        }
        res = self.service.create_request(self.intern_a_id, payload)
        self.assertEqual(res["trang_thai"], "ChoDuyet")
        self.assertEqual(res["ma_ho_so"], self.profile_a_id)
        self.assertEqual(res["ma_chuong_trinh"], self.program_1_id)
        self.assertEqual(res["start_date"], "2026-10-15")
        self.assertEqual(res["end_date"], "2026-10-16")
        self.assertEqual(res["ly_do"], "Bận việc gia đình có xin phép mentor")
        self.assertIsNone(res["reviewed_by"])
        self.assertIsNone(res["reviewed_at"])

    def test_eligible_programs_only_include_approved_current_programs(self):
        eligible = self.service.list_eligible_programs(self.intern_a_id, today=date(2026, 10, 8))
        self.assertEqual([item["ma_ung_tuyen"] for item in eligible], [self.app_a1_id])

        # Program start and end dates are inclusive.
        self.assertEqual(
            [item["ma_ung_tuyen"] for item in self.service.list_eligible_programs(self.intern_a_id, today=date(2026, 10, 1))],
            [self.app_a1_id],
        )
        self.assertEqual(
            [item["ma_ung_tuyen"] for item in self.service.list_eligible_programs(self.intern_a_id, today=date(2026, 12, 31))],
            [self.app_a1_id],
        )

        status_code, response = self._asgi_request(
            "GET", "/api/interns/me/leave-programs", user=self.intern_a
        )
        self.assertEqual(status_code, 200)
        self.assertEqual([item["ma_ung_tuyen"] for item in response], [self.app_a1_id])

    def test_create_request_rejects_future_or_closed_programs(self):
        for application_id in (self.future_application_id, self.closed_application_id):
            with self.subTest(application_id=application_id):
                with self.assertRaises(HTTPException) as ctx:
                    self.service.create_request(
                        self.intern_a_id,
                        {
                            "ma_ung_tuyen": application_id,
                            "start_date": "2026-10-15",
                            "end_date": "2026-10-16",
                            "ly_do": "Xin nghỉ phép",
                        },
                        today=date(2026, 10, 8),
                    )
                self.assertEqual(ctx.exception.status_code, 409)

    def test_evidence_metadata_schema_has_unique_storage_and_request_cascade(self):
        columns = {
            row["name"] for row in self.db.execute("PRAGMA table_info(YEU_CAU_NGHI_PHEP_TEP)").fetchall()
        }
        self.assertTrue(
            {"id", "leave_request_id", "storage_key", "original_filename", "mime_type", "file_size"}
            <= columns
        )
        foreign_keys = self.db.execute("PRAGMA foreign_key_list(YEU_CAU_NGHI_PHEP_TEP)").fetchall()
        self.assertTrue(any(
            row["from"] == "leave_request_id"
            and row["table"] == "YEU_CAU_NGHI_PHEP"
            and row["to"] == "id"
            and row["on_delete"] == "CASCADE"
            for row in foreign_keys
        ))
        unique_indexes = self.db.execute("PRAGMA index_list(YEU_CAU_NGHI_PHEP_TEP)").fetchall()
        self.assertTrue(any(
            row["unique"]
            and [col["name"] for col in self.db.execute(
                f"PRAGMA index_info({row['name']})"
            ).fetchall()] == ["storage_key"]
            for row in unique_indexes
        ))

    def test_evidence_upload_is_private_persisted_and_owner_scoped(self):
        """Valid evidence has random storage, persisted metadata, and owner-only retrieval."""
        pdf_bytes = b"%PDF-1.4\nprivate leave evidence"
        request = self._multipart_request([("../../medical-proof.pdf", pdf_bytes)])

        with tempfile.TemporaryDirectory(prefix="ims-us24-evidence-") as evidence_dir:
            with patch.object(leave_routes, "_evidence_root", return_value=Path(evidence_dir)):
                created = asyncio.run(leave_routes.create_leave_request(request, self.db))

                self.assertEqual(created["attachment_count"], 1)
                attachment = created["attachments"][0]
                self.assertEqual(attachment["original_filename"], "medical-proof.pdf")
                self.assertEqual(attachment["file_size"], len(pdf_bytes))
                self.assertNotIn("storage_key", attachment)

                metadata = self.db.execute(
                    "SELECT storage_key FROM YEU_CAU_NGHI_PHEP_TEP WHERE id = ?",
                    (attachment["id"],),
                ).fetchone()
                storage_key = metadata["storage_key"]
                self.assertRegex(storage_key, r"^[0-9a-f]{32}\.pdf$")
                stored_path = Path(evidence_dir) / storage_key
                self.assertEqual(stored_path.read_bytes(), pdf_bytes)

                response = leave_routes.get_my_leave_attachment(
                    created["id"], attachment["id"], request, db=self.db
                )
                self.assertEqual(Path(response.path), stored_path)
                self.assertIn("medical-proof.pdf", response.headers["content-disposition"])

                other_intern_request = SimpleNamespace(
                    state=SimpleNamespace(current_user=self.intern_b),
                )
                with self.assertRaises(HTTPException) as ctx:
                    leave_routes.get_my_leave_attachment(
                        created["id"], attachment["id"], other_intern_request, db=self.db
                    )
                self.assertEqual(ctx.exception.status_code, 403)

    def test_evidence_upload_rejects_invalid_extension_and_oversize_without_artifacts(self):
        invalid_files = [
            ("evidence.exe", b"%PDF-1.4 invalid extension"),
            ("invalid.pdf", b"not a PDF document"),
            ("oversized.pdf", b"%PDF-1.4" + b"x" * (5 * 1024 * 1024)),
        ]
        for filename, content in invalid_files:
            with self.subTest(filename=filename):
                request = self._multipart_request([(filename, content)])
                with tempfile.TemporaryDirectory(prefix="ims-us24-invalid-evidence-") as evidence_dir:
                    with patch.object(leave_routes, "_evidence_root", return_value=Path(evidence_dir)):
                        with self.assertRaises(HTTPException) as ctx:
                            asyncio.run(leave_routes.create_leave_request(request, self.db))
                        self.assertEqual(ctx.exception.status_code, 400)
                        self.assertEqual(list(Path(evidence_dir).iterdir()), [])
                        self.assertEqual(
                            self.db.execute("SELECT COUNT(*) AS total FROM YEU_CAU_NGHI_PHEP").fetchone()["total"],
                            0,
                        )

    def test_evidence_files_are_removed_when_request_persistence_fails(self):
        request = self._multipart_request([("proof.pdf", b"%PDF-1.4 evidence")])
        with tempfile.TemporaryDirectory(prefix="ims-us24-rollback-evidence-") as evidence_dir:
            with patch.object(leave_routes, "_evidence_root", return_value=Path(evidence_dir)):
                with patch.object(LeaveService, "create_request", side_effect=RuntimeError("simulated insert failure")):
                    with self.assertRaisesRegex(RuntimeError, "simulated insert failure"):
                        asyncio.run(leave_routes.create_leave_request(request, self.db))
                self.assertEqual(list(Path(evidence_dir).iterdir()), [])

    # ================= 2. DATE VALIDATION =================
    def test_date_validation_rules(self):
        # start > end: blocked
        with self.assertRaises(HTTPException) as ctx:
            self.service.create_request(self.intern_a_id, {
                "ma_ung_tuyen": self.app_a1_id,
                "start_date": "2026-10-20",
                "end_date": "2026-10-15",
                "ly_do": "Nghỉ phép",
            })
        self.assertEqual(ctx.exception.status_code, 400)

        # same-day leave: ALLOWED
        same_day = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-10-25",
            "end_date": "2026-10-25",
            "ly_do": "Nghỉ 1 ngày khám sức khỏe",
        })
        self.assertEqual(same_day["start_date"], same_day["end_date"])

        # Pydantic schema validation for start > end
        with self.assertRaises(ValidationError):
            LeaveRequestCreate(
                ma_ung_tuyen=self.app_a1_id,
                start_date=date(2026, 10, 20),
                end_date=date(2026, 10, 10),
                ly_do="Lý do",
            )

        # Pydantic schema validation for empty reason
        with self.assertRaises(ValidationError):
            LeaveRequestCreate(
                ma_ung_tuyen=self.app_a1_id,
                start_date=date(2026, 10, 10),
                end_date=date(2026, 10, 12),
                ly_do="   ",
            )

    # ================= 3. PROGRAM PERIOD VALIDATION =================
    def test_program_period_validation(self):
        # Program 1 runs 2026-10-01 to 2026-12-31

        # Leave starts before program starts (2026-09-28) -> BLOCKED
        with self.assertRaises(HTTPException) as ctx:
            self.service.create_request(self.intern_a_id, {
                "ma_ung_tuyen": self.app_a1_id,
                "start_date": "2026-09-28",
                "end_date": "2026-10-05",
                "ly_do": "Xin nghỉ sớm",
            })
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("không được trước ngày bắt đầu chương trình", ctx.exception.detail)

        # Leave ends after program ends (2027-01-05) -> BLOCKED
        with self.assertRaises(HTTPException) as ctx:
            self.service.create_request(self.intern_a_id, {
                "ma_ung_tuyen": self.app_a1_id,
                "start_date": "2026-12-28",
                "end_date": "2027-01-05",
                "ly_do": "Xin nghỉ kéo dài",
            })
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("không được sau ngày kết thúc chương trình", ctx.exception.detail)

    # ================= 4. OWNERSHIP & IDOR PROTECTION =================
    def test_ownership_and_idor_protection(self):
        # Intern A tries to create leave using Intern B's application (app_b1_id) -> 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            self.service.create_request(self.intern_a_id, {
                "ma_ung_tuyen": self.app_b1_id,
                "start_date": "2026-10-15",
                "end_date": "2026-10-16",
                "ly_do": "Chiếm quyền tạo đơn",
            })
        self.assertEqual(ctx.exception.status_code, 403)

        # Intern B creates a legitimate request
        req_b = self.service.create_request(self.intern_b_id, {
            "ma_ung_tuyen": self.app_b1_id,
            "start_date": "2026-10-18",
            "end_date": "2026-10-19",
            "ly_do": "Đơn của B",
        })
        b_req_id = req_b["id"]

        # Intern A tries to view Intern B's leave detail -> 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            self.service.get_intern_request_detail(self.intern_a_id, b_req_id)
        self.assertEqual(ctx.exception.status_code, 403)

        # Intern A tries to cancel Intern B's leave request -> 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            self.service.cancel_intern_request(self.intern_a_id, b_req_id)
        self.assertEqual(ctx.exception.status_code, 403)

    # ================= 5. INVALID APPLICATION STATE =================
    def test_invalid_application_state_blocks_request(self):
        # Intern B tries to create leave on pending application app_b2_pending_id -> 409 Conflict
        with self.assertRaises(HTTPException) as ctx:
            self.service.create_request(self.intern_b_id, {
                "ma_ung_tuyen": self.app_b2_pending_id,
                "start_date": "2027-01-10",
                "end_date": "2027-01-12",
                "ly_do": "Xin nghỉ ở chương trình chưa duyệt",
            })
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Chỉ đơn ứng tuyển đã được duyệt", ctx.exception.detail)

        # Nonexistent application -> 404
        with self.assertRaises(HTTPException) as ctx:
            self.service.create_request(self.intern_a_id, {
                "ma_ung_tuyen": 999999,
                "start_date": "2026-10-15",
                "end_date": "2026-10-16",
                "ly_do": "Đơn không tồn tại",
            })
        self.assertEqual(ctx.exception.status_code, 404)

    # ================= 6. INTERN OWN LIST IS SCOPED =================
    def test_intern_own_list_is_strictly_isolated(self):
        # Create request for A
        self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-10-15",
            "end_date": "2026-10-16",
            "ly_do": "Đơn của A",
        })
        # Create request for B
        self.service.create_request(self.intern_b_id, {
            "ma_ung_tuyen": self.app_b1_id,
            "start_date": "2026-10-20",
            "end_date": "2026-10-22",
            "ly_do": "Đơn của B",
        })

        list_a = self.service.list_intern_requests(self.intern_a_id)
        self.assertEqual(len(list_a), 1)
        self.assertEqual(list_a[0]["ly_do"], "Đơn của A")

        list_b = self.service.list_intern_requests(self.intern_b_id)
        self.assertEqual(len(list_b), 1)
        self.assertEqual(list_b[0]["ly_do"], "Đơn của B")

    # ================= 7. CANCEL PENDING LEAVE =================
    def test_cancel_pending_leave_request(self):
        req = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
            "ly_do": "Xin nghỉ việc riêng",
        })
        req_id = req["id"]

        cancelled = self.service.cancel_intern_request(self.intern_a_id, req_id)
        self.assertEqual(cancelled["trang_thai"], "DaHuy")

        # Double cancel -> 409 Conflict
        with self.assertRaises(HTTPException) as ctx:
            self.service.cancel_intern_request(self.intern_a_id, req_id)
        self.assertEqual(ctx.exception.status_code, 409)

    # ================= 8. CANCEL REVIEWED LEAVE IS BLOCKED =================
    def test_cancel_reviewed_leave_is_blocked(self):
        req = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-11-05",
            "end_date": "2026-11-06",
            "ly_do": "Xin nghỉ phép",
        })
        req_id = req["id"]

        # HR approves
        self.service.review_request(self.hr_id, req_id, "DaDuyet")

        # Intern tries to cancel approved request -> 409 Conflict
        with self.assertRaises(HTTPException) as ctx:
            self.service.cancel_intern_request(self.intern_a_id, req_id)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Chỉ có thể hủy đơn nghỉ phép đang ở trạng thái Chờ duyệt", ctx.exception.detail)

    # ================= 9. HR / ADMIN APPROVAL =================
    def test_hr_admin_approval_lifecycle(self):
        req = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-11-10",
            "end_date": "2026-11-11",
            "ly_do": "Xin nghỉ tham gia hội thảo",
        })
        req_id = req["id"]

        reviewed = self.service.review_request(self.admin_id, req_id, "DaDuyet")
        self.assertEqual(reviewed["trang_thai"], "DaDuyet")
        self.assertEqual(reviewed["reviewed_by"], self.admin_id)
        self.assertIsNotNone(reviewed["reviewed_at"])

        # Second approval -> 409 Conflict
        with self.assertRaises(HTTPException) as ctx:
            self.service.review_request(self.hr_id, req_id, "DaDuyet")
        self.assertEqual(ctx.exception.status_code, 409)

    # ================= 10. HR / ADMIN REJECTION =================
    def test_hr_admin_rejection_with_reason(self):
        req = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-11-15",
            "end_date": "2026-11-16",
            "ly_do": "Xin nghỉ",
        })
        req_id = req["id"]

        # Reject without reason -> 400 Bad Request
        with self.assertRaises(HTTPException) as ctx:
            self.service.review_request(self.hr_id, req_id, "TuChoi", "")
        self.assertEqual(ctx.exception.status_code, 400)

        # Reject with valid reason
        reviewed = self.service.review_request(self.hr_id, req_id, "TuChoi", "Trùng lịch demo dự án quan trọng")
        self.assertEqual(reviewed["trang_thai"], "TuChoi")
        self.assertEqual(reviewed["ly_do_tu_choi"], "Trùng lịch demo dự án quan trọng")
        self.assertEqual(reviewed["reviewed_by"], self.hr_id)

        # Intern reads rejection reason
        detail = self.service.get_intern_request_detail(self.intern_a_id, req_id)
        self.assertEqual(detail["ly_do_tu_choi"], "Trùng lịch demo dự án quan trọng")

        # Invalid transition: Rejected -> Approved is blocked
        with self.assertRaises(HTTPException) as ctx:
            self.service.review_request(self.admin_id, req_id, "DaDuyet")
        self.assertEqual(ctx.exception.status_code, 409)

    # ================= 11. ROLE PERMISSIONS & RBAC =================
    def test_review_roles_rbac(self):
        req = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-11-20",
            "end_date": "2026-11-21",
            "ly_do": "Xin nghỉ",
        })
        req_id = req["id"]

        # Mentor tries to review via route -> 403 Forbidden
        status_code, _ = self._asgi_request(
            "POST",
            f"/api/leave-requests/{req_id}/review",
            user=self.mentor,
            json_body={"trang_thai": "DaDuyet"},
        )
        self.assertEqual(status_code, 403)

        # TTS tries to review -> 403 Forbidden
        status_code, _ = self._asgi_request(
            "POST",
            f"/api/leave-requests/{req_id}/review",
            user=self.intern_a,
            json_body={"trang_thai": "DaDuyet"},
        )
        self.assertEqual(status_code, 403)

        # Anonymous tries to review -> 401
        status_code, _ = self._asgi_request(
            "POST",
            f"/api/leave-requests/{req_id}/review",
            user=None,
            json_body={"trang_thai": "DaDuyet"},
        )
        self.assertEqual(status_code, 401)

        # HR review -> 200 OK
        status_code, body = self._asgi_request(
            "POST",
            f"/api/leave-requests/{req_id}/review",
            user=self.hr,
            json_body={"trang_thai": "DaDuyet"},
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(body["trang_thai"], "DaDuyet")

    # ================= 12. NO SELF APPROVAL =================
    def test_self_approval_is_blocked(self):
        # Create an account that has Admin role but also owns the intern profile
        db = database.get_db_connection()
        dual_user_cur = db.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES ('Dual User Admin-TTS', 'dual@example.test', 'hash', 'Admin', 'HoatDong')
        """)
        dual_user_id = dual_user_cur.lastrowid
        dual_user = {"ma_nguoi_dung": dual_user_id, "vai_tro": "Admin", "ho_ten": "Dual User"}

        dual_prof = db.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, trang_thai_xet_duyet, trang_thai_thuc_tap)
            VALUES (?, 'DaDuyet', 'DangThucTap')
        """, (dual_user_id,))
        dual_prof_id = dual_prof.lastrowid

        dual_app = db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet)
            VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP)
        """, (self.program_1_id, dual_prof_id))
        dual_app_id = dual_app.lastrowid
        db.commit()
        db.close()

        req = self.service.create_request(dual_user_id, {
            "ma_ung_tuyen": dual_app_id,
            "start_date": "2026-10-15",
            "end_date": "2026-10-16",
            "ly_do": "Đơn của dual user",
        })
        req_id = req["id"]

        # Dual user attempts to approve own request as Admin -> 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            self.service.review_request(dual_user_id, req_id, "DaDuyet")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("không được tự duyệt đơn nghỉ phép của chính mình", ctx.exception.detail)

    # ================= 13. CONCURRENCY & RACE CONDITIONS =================
    def test_concurrent_review_and_cancel_race(self):
        # Test 1: HR approve vs HR reject concurrently -> Exactly one wins
        req1 = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-10-15",
            "end_date": "2026-10-16",
            "ly_do": "Concurrent test 1",
        })
        req1_id = req1["id"]

        results = []
        errors = []

        def do_approve():
            db_th = database.get_db_connection()
            try:
                r = LeaveService(db_th).review_request(self.admin_id, req1_id, "DaDuyet")
                results.append(("APPROVE", r))
            except HTTPException as e:
                errors.append(("APPROVE", e.status_code))
            finally:
                db_th.close()

        def do_reject():
            db_th = database.get_db_connection()
            try:
                r = LeaveService(db_th).review_request(self.hr_id, req1_id, "TuChoi", "Từ chối")
                results.append(("REJECT", r))
            except HTTPException as e:
                errors.append(("REJECT", e.status_code))
            finally:
                db_th.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(do_approve)
            f2 = executor.submit(do_reject)
            f1.result()
            f2.result()

        # Exactly 1 succeeded and 1 got 409
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][1], 409)

        # Test 2: Intern cancel vs HR approve concurrently -> Exactly one wins
        req2 = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-10-22",
            "end_date": "2026-10-23",
            "ly_do": "Concurrent test 2",
        })
        req2_id = req2["id"]

        results_race = []
        errors_race = []

        def do_cancel():
            db_th = database.get_db_connection()
            try:
                r = LeaveService(db_th).cancel_intern_request(self.intern_a_id, req2_id)
                results_race.append(("CANCEL", r))
            except HTTPException as e:
                errors_race.append(("CANCEL", e.status_code))
            finally:
                db_th.close()

        def do_hr_approve():
            db_th = database.get_db_connection()
            try:
                r = LeaveService(db_th).review_request(self.hr_id, req2_id, "DaDuyet")
                results_race.append(("APPROVE", r))
            except HTTPException as e:
                errors_race.append(("APPROVE", e.status_code))
            finally:
                db_th.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(do_cancel)
            f2 = executor.submit(do_hr_approve)
            f1.result()
            f2.result()

        self.assertEqual(len(results_race), 1)
        self.assertEqual(len(errors_race), 1)
        self.assertEqual(errors_race[0][1], 409)

    # ================= 14. DUPLICATE SUBMISSION =================
    def test_duplicate_submission_blocked(self):
        self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-11-25",
            "end_date": "2026-11-26",
            "ly_do": "Đơn lần 1",
        })

        # Submit exact same request while pending -> 409 Conflict
        with self.assertRaises(HTTPException) as ctx:
            self.service.create_request(self.intern_a_id, {
                "ma_ung_tuyen": self.app_a1_id,
                "start_date": "2026-11-25",
                "end_date": "2026-11-26",
                "ly_do": "Gửi trùng lần 2",
            })
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("đang chờ xét duyệt", ctx.exception.detail)

    # ================= 15. ATTENDANCE TABLE IS NEVER MUTATED =================
    def test_attendance_table_is_never_mutated(self):
        # Ensure initial count of CHAM_CONG
        cnt_before = self.db.execute("SELECT COUNT(*) FROM CHAM_CONG").fetchone()[0]

        req = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-12-01",
            "end_date": "2026-12-02",
            "ly_do": "Nghỉ phép",
        })
        cnt_after_create = self.db.execute("SELECT COUNT(*) FROM CHAM_CONG").fetchone()[0]
        self.assertEqual(cnt_before, cnt_after_create)

        self.service.review_request(self.admin_id, req["id"], "DaDuyet")
        cnt_after_approve = self.db.execute("SELECT COUNT(*) FROM CHAM_CONG").fetchone()[0]
        self.assertEqual(cnt_before, cnt_after_approve)

    # ================= 16. ONLY APPROVED COUNTS AS LEAVE =================
    def test_approved_only_counts_as_leave_for_us22_compatibility(self):
        # 1. Approved leave
        r_approved = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-12-10",
            "end_date": "2026-12-11",
            "ly_do": "Nghỉ được duyệt",
        })
        self.service.review_request(self.admin_id, r_approved["id"], "DaDuyet")

        # 2. Pending leave
        self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-12-15",
            "end_date": "2026-12-16",
            "ly_do": "Nghỉ chờ duyệt",
        })

        # 3. Rejected leave
        r_rejected = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-12-20",
            "end_date": "2026-12-21",
            "ly_do": "Nghỉ bị từ chối",
        })
        self.service.review_request(self.admin_id, r_rejected["id"], "TuChoi", "Không duyệt")

        # 4. Cancelled leave
        r_cancelled = self.service.create_request(self.intern_a_id, {
            "ma_ung_tuyen": self.app_a1_id,
            "start_date": "2026-12-25",
            "end_date": "2026-12-26",
            "ly_do": "Nghỉ tự hủy",
        })
        self.service.cancel_intern_request(self.intern_a_id, r_cancelled["id"])

        # Query canonical approved leaves in December 2026
        approved_leaves = get_approved_leaves_for_profile(
            self.db, self.profile_a_id, date(2026, 12, 1), date(2026, 12, 31)
        )
        self.assertEqual(len(approved_leaves), 1)
        self.assertEqual(approved_leaves[0]["id"], r_approved["id"])
        self.assertEqual(approved_leaves[0]["trang_thai"], "DaDuyet")

    # ================= 17. HTTP LAYER END-TO-END =================
    def test_http_layer_end_to_end(self):
        # Intern A creates via HTTP POST
        status_code, body = self._asgi_request(
            "POST",
            "/api/interns/me/leave-requests",
            user=self.intern_a,
            json_body={
                "ma_ung_tuyen": self.app_a1_id,
                "start_date": "2026-10-15",
                "end_date": "2026-10-17",
                "ly_do": "Đơn HTTP Test",
            },
        )
        self.assertEqual(status_code, 201)
        req_id = body["id"]

        # Intern A lists own requests
        status_code, body_list = self._asgi_request(
            "GET",
            "/api/interns/me/leave-requests",
            user=self.intern_a,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(len(body_list), 1)
        self.assertEqual(body_list[0]["id"], req_id)

        # Intern A reads detail
        status_code, body_detail = self._asgi_request(
            "GET",
            f"/api/interns/me/leave-requests/{req_id}",
            user=self.intern_a,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(body_detail["id"], req_id)

        # HR lists leave requests
        status_code, hr_list = self._asgi_request(
            "GET",
            "/api/leave-requests?status=ChoDuyet",
            user=self.hr,
        )
        self.assertEqual(status_code, 200)
        self.assertGreaterEqual(len(hr_list), 1)

        # HR gets detail
        status_code, hr_detail = self._asgi_request(
            "GET",
            f"/api/leave-requests/{req_id}",
            user=self.hr,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(hr_detail["id"], req_id)

        # HR approves
        status_code, approved = self._asgi_request(
            "POST",
            f"/api/leave-requests/{req_id}/review",
            user=self.hr,
            json_body={"trang_thai": "DaDuyet"},
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(approved["trang_thai"], "DaDuyet")
        self.assertEqual(approved["reviewed_by"], self.hr_id)


if __name__ == "__main__":
    unittest.main()
