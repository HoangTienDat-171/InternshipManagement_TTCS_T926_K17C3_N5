import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app import database
from app.routes import support_request_routes
from app.routes.support_request_routes import MAX_SUPPORT_FILE_SIZE, _support_file_root
from app.schemas import SupportRequestCreate, SupportRequestResolve, SupportRequestReject
from app.support_request_service import SupportRequestService


class FakeUpload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content
        self._pos = 0

    async def read(self, size: int = -1):
        if size == -1:
            chunk = self._content[self._pos:]
            self._pos = len(self._content)
            return chunk
        chunk = self._content[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


class FakeForm:
    def __init__(self, fields: dict, files: list = None):
        self._fields = fields
        self._files = files or []

    def get(self, key, default=None):
        return self._fields.get(key, default)

    def multi_items(self):
        items = [(k, v) for k, v in self._fields.items()]
        for f in self._files:
            items.append(("file", f))
        return items

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def fake_request(user=None, headers=None, json_body=None, form_fields=None, form_files=None):
    import uuid
    headers = dict(headers or {})
    if json_body is not None and "loai_yeu_cau" in json_body:
        json_body = dict(json_body)
        json_body.setdefault("idempotency_key", uuid.uuid4().hex)
    if form_fields is not None:
        form_fields = dict(form_fields)
        form_fields.setdefault("idempotency_key", uuid.uuid4().hex)
    req = SimpleNamespace(
        state=SimpleNamespace(current_user=user),
        headers=headers,
    )

    async def _json():
        if json_body is None:
            raise ValueError("No JSON body provided")
        return json_body

    req.json = _json
    if form_fields is not None or form_files is not None:
        headers["content-type"] = "multipart/form-data; boundary=----fake"
        req.form = lambda **kwargs: FakeForm(form_fields or {}, form_files or [])
    return req


def call_list_my_requests(request, db, trang_thai=None, loai_yeu_cau=None, page=1, page_size=10):
    return support_request_routes.list_my_support_requests(
        request=request,
        trang_thai=trang_thai,
        loai_yeu_cau=loai_yeu_cau,
        status=None,
        type=None,
        page=page,
        page_size=page_size,
        db=db,
    )


def call_list_hr_requests(
    request, db, trang_thai=None, loai_yeu_cau=None, search=None, intern_id=None, date_from=None, date_to=None, page=1, page_size=10
):
    return support_request_routes.list_support_requests_hr(
        request=request,
        trang_thai=trang_thai,
        loai_yeu_cau=loai_yeu_cau,
        status=None,
        type=None,
        search=search,
        intern_id=intern_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        db=db,
    )


class SupportRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us27-us28-")
        cls.db_path = Path(cls.temp_dir.name) / "us27_us28.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.backend_patch.stop()
        cls.path_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        import uuid
        self.conn = database.get_db_connection()
        self.service = SupportRequestService(self.conn)

        uid = uuid.uuid4().hex[:6]
        self.intern1_id = self._insert_user("TTS Nguyễn Văn A", f"tts.a.{uid}@test.vn", "ThucTapSinh")
        self.intern2_id = self._insert_user("TTS Trần Thị B", f"tts.b.{uid}@test.vn", "ThucTapSinh")
        self.hr_id = self._insert_user("HR Lê Thu C", f"hr.c.{uid}@test.vn", "HR")
        self.admin_id = self._insert_user("Admin Hoàng D", f"admin.d.{uid}@test.vn", "Admin")
        self.mentor_id = self._insert_user("Mentor Vũ E", f"mentor.e.{uid}@test.vn", "Mentor")

        cursor = self.conn.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet)
            VALUES (?, 'Công nghệ thông tin', 'DaDuyet')
        """, (self.intern1_id,))
        self.profile1_id = cursor.lastrowid
        self.conn.commit()

        self.users = {
            "intern1": {"ma_nguoi_dung": self.intern1_id, "vai_tro": "ThucTapSinh", "ho_ten": "TTS Nguyễn Văn A", "email": f"tts.a.{uid}@test.vn"},
            "intern2": {"ma_nguoi_dung": self.intern2_id, "vai_tro": "ThucTapSinh", "ho_ten": "TTS Trần Thị B", "email": f"tts.b.{uid}@test.vn"},
            "hr": {"ma_nguoi_dung": self.hr_id, "vai_tro": "HR", "ho_ten": "HR Lê Thu C", "email": f"hr.c.{uid}@test.vn"},
            "admin": {"ma_nguoi_dung": self.admin_id, "vai_tro": "Admin", "ho_ten": "Admin Hoàng D", "email": f"admin.d.{uid}@test.vn"},
            "mentor": {"ma_nguoi_dung": self.mentor_id, "vai_tro": "Mentor", "ho_ten": "Mentor Vũ E", "email": f"mentor.e.{uid}@test.vn"},
        }

    def create_request(self, intern_user_id, payload, attachments=None):
        import uuid
        request_payload = dict(payload)
        request_payload.setdefault("idempotency_key", uuid.uuid4().hex)
        return self.service.create_request(intern_user_id, request_payload, attachments)

    def make_asgi_app(self, max_body_size=20 * 1024 * 1024):
        app = FastAPI()
        app.add_middleware(
            support_request_routes.SupportRequestBodyLimitMiddleware,
            max_body_size=max_body_size,
        )
        app.include_router(support_request_routes.router)
        self.observed_content_lengths = []

        @app.middleware("http")
        async def set_test_user(request: Request, call_next):
            self.observed_content_lengths.append(request.headers.get("content-length"))
            request.state.current_user = self.users["intern1"]
            return await call_next(request)

        def test_db():
            conn = database.get_db_connection()
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[support_request_routes.get_db] = test_db
        return app

    @staticmethod
    def multipart_body(file_content: bytes, idempotency_key="asgi-test-key") -> bytes:
        boundary = b"ims-support-boundary"
        parts = [
            b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"loai_yeu_cau\"\r\n\r\nOTHER\r\n",
            b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"noi_dung\"\r\n\r\nNeed help\r\n",
            b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"idempotency_key\"\r\n\r\n" + idempotency_key.encode() + b"\r\n",
            b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"files\"; filename=\"proof.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
            + file_content + b"\r\n",
            b"--" + boundary + b"--\r\n",
        ]
        return b"".join(parts)

    @staticmethod
    async def stream_body(body: bytes):
        for offset in range(0, len(body), 257):
            yield body[offset:offset + 257]

    def post_multipart(self, app, body: bytes):
        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                return await client.post(
                    "/api/support-requests",
                    headers={"content-type": "multipart/form-data; boundary=ims-support-boundary"},
                    content=self.stream_body(body),
                )

        return asyncio.run(send())

    def tearDown(self):
        try:
            self.conn.execute("DELETE FROM THONG_BAO")
            self.conn.execute("DELETE FROM YEU_CAU_HO_TRO_TEP")
            self.conn.execute("DELETE FROM YEU_CAU_HO_TRO")
            self.conn.execute("DELETE FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung IN (?, ?)", (self.intern1_id, self.intern2_id))
            self.conn.execute("DELETE FROM NGUOI_DUNG WHERE ma_nguoi_dung IN (?, ?, ?, ?, ?)", (self.intern1_id, self.intern2_id, self.hr_id, self.admin_id, self.mentor_id))
            self.conn.commit()
            root = _support_file_root()
            if root.exists():
                for f in root.glob("*"):
                    if f.is_file():
                        f.unlink(missing_ok=True)
        finally:
            self.conn.close()

    def _insert_user(self, name: str, email: str, role: str) -> int:
        import random
        phone = "09" + "".join(str(random.randint(0, 9)) for _ in range(8))
        cursor = self.conn.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, so_dien_thoai, vai_tro, trang_thai)
            VALUES (?, ?, '$2b$12$dummyhash', ?, ?, 'HoatDong')
        """, (name, email, phone, role))
        return cursor.lastrowid

    # =========================================================================
    # 1. KIỂM THỬ QUYỀN & RBAC (ROLE-BASED ACCESS CONTROL)
    # =========================================================================

    def test_rbac_intern_create_and_view_access(self):
        """TTS được phép tạo yêu cầu (JSON) và xem danh sách yêu cầu của chính mình"""
        req_obj = fake_request(
            user=self.users["intern1"],
            json_body={"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Cần cấp giấy chứng nhận thực tập", "ma_ho_so": self.profile1_id}
        )
        created = asyncio.run(support_request_routes.create_support_request(req_obj, db=self.conn))
        self.assertEqual(created["ma_nguoi_dung"], self.intern1_id)
        self.assertEqual(created["trang_thai"], "PENDING")

        list_req = fake_request(user=self.users["intern1"])
        my_list = call_list_my_requests(list_req, db=self.conn)
        self.assertEqual(my_list["total"], 1)
        self.assertEqual(my_list["items"][0]["id"], created["id"])

    def test_rbac_intern_denied_hr_management_endpoints(self):
        """TTS bị từ chối 403 khi gọi API giải quyết hoặc từ chối của HR"""
        req_data = self.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Yêu cầu cần duyệt"})

        intern_req = fake_request(user=self.users["intern1"], json_body={"phan_hoi_hr": "Tự duyệt"})
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.resolve_support_request(req_data["id"], intern_req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 403)

        reject_req = fake_request(user=self.users["intern1"], json_body={"ly_do_tu_choi": "Tự từ chối"})
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.reject_support_request(req_data["id"], reject_req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 403)

    def test_rbac_mentor_denied_all_support_endpoints(self):
        """Mentor không thuộc đối tượng xử lý yêu cầu hỗ trợ -> bị chặn 403 trên toàn bộ các route"""
        req_data = self.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Xin chứng chỉ"})

        mentor_req = fake_request(user=self.users["mentor"])

        # 1. Không tạo được yêu cầu
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(
                fake_request(user=self.users["mentor"], json_body={"loai_yeu_cau": "OTHER", "noi_dung": "Mentor tạo"}),
                db=self.conn
            ))
        self.assertEqual(cm.exception.status_code, 403)

        # 2. Không xem danh sách riêng
        with self.assertRaises(HTTPException) as cm:
            call_list_my_requests(mentor_req, db=self.conn)
        self.assertEqual(cm.exception.status_code, 403)

        # 3. Không xem danh sách quản lý HR
        with self.assertRaises(HTTPException) as cm:
            call_list_hr_requests(mentor_req, db=self.conn)
        self.assertEqual(cm.exception.status_code, 403)

        # 4. Không xem chi tiết quản lý HR
        with self.assertRaises(HTTPException) as cm:
            support_request_routes.get_support_request_detail_hr(req_data["id"], mentor_req, db=self.conn)
        self.assertEqual(cm.exception.status_code, 403)

        # 5. Không giải quyết yêu cầu
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.resolve_support_request(
                req_data["id"],
                fake_request(user=self.users["mentor"], json_body={"phan_hoi_hr": "Mentor duyệt"}),
                db=self.conn
            ))
        self.assertEqual(cm.exception.status_code, 403)

        # 6. Không từ chối yêu cầu
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.reject_support_request(
                req_data["id"],
                fake_request(user=self.users["mentor"], json_body={"ly_do_tu_choi": "Mentor từ chối"}),
                db=self.conn
            ))
        self.assertEqual(cm.exception.status_code, 403)

    def test_rbac_hr_cannot_create_support_request(self):
        """HR không được phép tạo yêu cầu hỗ trợ (chức năng dành riêng cho TTS) -> bị từ chối 403"""
        hr_create_req = fake_request(
            user=self.users["hr"],
            json_body={"loai_yeu_cau": "DOCUMENT", "noi_dung": "HR muốn xin tài liệu"}
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(hr_create_req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 403)

    def test_rbac_admin_has_full_management_access(self):
        """Admin có toàn quyền quản lý: xem danh sách, xem chi tiết, giải quyết và từ chối yêu cầu"""
        req1 = self.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Yêu cầu 1"})
        req2 = self.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Yêu cầu 2"})

        admin_req = fake_request(user=self.users["admin"])

        # Admin xem danh sách
        all_res = call_list_hr_requests(admin_req, db=self.conn)
        self.assertEqual(all_res["total"], 2)

        # Admin xem chi tiết
        detail = support_request_routes.get_support_request_detail_hr(req1["id"], admin_req, db=self.conn)
        self.assertEqual(detail["id"], req1["id"])

        # Admin giải quyết req1
        resolve_req = fake_request(user=self.users["admin"], json_body={"phan_hoi_hr": "Admin đã phê duyệt giấy chứng nhận."})
        res1 = asyncio.run(support_request_routes.resolve_support_request(req1["id"], resolve_req, db=self.conn))
        self.assertEqual(res1["trang_thai"], "RESOLVED")
        self.assertEqual(res1["nguoi_xu_ly"], self.admin_id)

        # Admin từ chối req2
        reject_req = fake_request(user=self.users["admin"], json_body={"ly_do_tu_choi": "Admin từ chối vì chưa đủ hồ sơ."})
        res2 = asyncio.run(support_request_routes.reject_support_request(req2["id"], reject_req, db=self.conn))
        self.assertEqual(res2["trang_thai"], "REJECTED")
        self.assertEqual(res2["nguoi_xu_ly"], self.admin_id)

    def test_rbac_unauthenticated_request_rejected(self):
        """Yêu cầu chưa đăng nhập (user=None) bị từ chối 401 Unauthorized"""
        unauth_req = fake_request(user=None)
        with self.assertRaises(HTTPException) as cm:
            call_list_my_requests(unauth_req, db=self.conn)
        self.assertEqual(cm.exception.status_code, 401)

        with self.assertRaises(HTTPException) as cm:
            call_list_hr_requests(unauth_req, db=self.conn)
        self.assertEqual(cm.exception.status_code, 401)

    # =========================================================================
    # 2. KIỂM THỬ TỆP ĐÍNH KÈM (FILE UPLOAD & DOWNLOAD VALIDATION)
    # =========================================================================

    def test_asgi_multipart_upload_without_content_length_uses_real_parser(self):
        app = self.make_asgi_app()
        body = self.multipart_body(b"%PDF-1.4\nproof")

        response = self.post_multipart(app, body)

        self.assertEqual(response.status_code, 201, response.text)
        self.assertIsNone(self.observed_content_lengths[-1])
        self.assertEqual(response.json()["so_luong_tep"], 1)

    def test_asgi_multipart_body_limit_without_content_length(self):
        app = self.make_asgi_app(max_body_size=512)
        body = self.multipart_body(b"%PDF-1.4\n" + b"x" * 2048)

        response = self.post_multipart(app, body)

        self.assertEqual(response.status_code, 413, response.text)
        self.assertIsNone(self.observed_content_lengths[-1])
        root = _support_file_root()
        self.assertFalse(root.exists() and any(root.iterdir()))

    def test_asgi_multipart_file_count_is_limited_during_parsing(self):
        app = self.make_asgi_app()
        boundary = b"ims-support-boundary"
        parts = [
            b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"loai_yeu_cau\"\r\n\r\nOTHER\r\n",
            b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"noi_dung\"\r\n\r\nNeed help\r\n",
            b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"idempotency_key\"\r\n\r\nasgi-six-files\r\n",
        ]
        for index in range(6):
            parts.append(
                b"--" + boundary
                + f"\r\nContent-Disposition: form-data; name=\"files\"; filename=\"proof-{index}.pdf\"\r\n".encode()
                + b"Content-Type: application/pdf\r\n\r\n%PDF-1.4 test\r\n"
            )
        parts.append(b"--" + boundary + b"--\r\n")
        response = self.post_multipart(app, b"".join(parts))
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Too many files", response.text)
        root = _support_file_root()
        self.assertFalse(root.exists() and any(root.iterdir()))

    def test_asgi_file_validation_failure_removes_staged_file(self):
        app = self.make_asgi_app()
        body = self.multipart_body(b"%PDF-1.4\n" + b"x" * 64)

        with patch.object(support_request_routes, "MAX_SUPPORT_FILE_SIZE", 8):
            response = self.post_multipart(app, body)

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIsNone(self.observed_content_lengths[-1])
        root = _support_file_root()
        self.assertFalse(root.exists() and any(root.iterdir()))

    def test_file_upload_valid_multipart_success(self):
        """TTS gửi yêu cầu hỗ trợ kèm file PDF và PNG hợp lệ qua multipart/form-data thành công 201"""
        pdf_bytes = b"%PDF-1.4 sample pdf content for internship test"
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

        form_fields = {
            "loai_yeu_cau": "CERTIFICATE",
            "noi_dung": "Gửi kèm mẫu đơn xin chứng nhận và ảnh thẻ.",
            "ma_ho_so": str(self.profile1_id),
        }
        form_files = [
            FakeUpload("mau_don.pdf", pdf_bytes),
            FakeUpload("anh_the.png", png_bytes),
        ]

        req = fake_request(
            user=self.users["intern1"],
            form_fields=form_fields,
            form_files=form_files,
        )

        res = asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(res["trang_thai"], "PENDING")
        self.assertEqual(len(res["attachments"]), 2)

        filenames = [att["original_filename"] for att in res["attachments"]]
        self.assertIn("mau_don.pdf", filenames)
        self.assertIn("anh_the.png", filenames)

        # Kiểm tra file thực tế đã được lưu trên máy chủ
        root = _support_file_root()
        for att in res["attachments"]:
            disk_path = root / att["storage_key"]
            self.assertTrue(disk_path.is_file())
            self.assertEqual(disk_path.stat().st_size, att["file_size"])

    def test_file_upload_valid_docx_multipart_success(self):
        """TTS gửi yêu cầu hỗ trợ kèm file DOCX thực tế (>64KB) qua multipart thành công 201"""
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types></Types>")
            zf.writestr("word/document.xml", "A" * 100000)
        docx_bytes = buf.getvalue()

        req = fake_request(
            user=self.users["intern1"],
            form_fields={
                "loai_yeu_cau": "DOCUMENT",
                "noi_dung": "Gửi kèm file báo cáo word docx.",
                "ma_ho_so": str(self.profile1_id),
            },
            form_files=[FakeUpload("bao_cao.docx", docx_bytes)],
        )

        res = asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(res["trang_thai"], "PENDING")
        self.assertEqual(len(res["attachments"]), 1)
        self.assertEqual(res["attachments"][0]["original_filename"], "bao_cao.docx")

    def test_file_upload_docx_spoofed_text_rejected(self):
        """File .docx giả mạo (không phải zip header PK) bị từ chối 400"""
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Tệp giả mạo"},
            form_files=[FakeUpload("fake.docx", b"This is just plain text, not docx")],
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Nội dung tệp không khớp định dạng đã chọn", cm.exception.detail)

    def test_file_upload_docx_invalid_zip_missing_xml_rejected(self):
        """File .docx là zip nhưng không chứa word/document.xml bị từ chối 400"""
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("some_other_file.txt", "hello")
        bad_zip = buf.getvalue()

        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Zip không phải docx"},
            form_files=[FakeUpload("invalid.docx", bad_zip)],
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Nội dung tệp không khớp định dạng đã chọn", cm.exception.detail)

    def test_file_upload_invalid_extension_rejected(self):
        """File có đuôi mở rộng không được hỗ trợ (.exe, .sh) bị từ chối 400"""
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Cần hỗ trợ tệp"},
            form_files=[FakeUpload("malware.exe", b"MZ\x90\x00\x03\x00\x00\x00")],
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Chỉ hỗ trợ PNG, JPG, JPEG, PDF, DOC hoặc DOCX", cm.exception.detail)

    def test_file_upload_spoofed_content_magic_bytes_rejected(self):
        """File giả mạo định dạng (đuôi .pdf nhưng nội dung là text thường) bị từ chối 400"""
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Cần hỗ trợ tệp"},
            form_files=[FakeUpload("fake.pdf", b"This is plainly not a real PDF file")],
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Nội dung tệp không khớp định dạng đã chọn", cm.exception.detail)

    def test_file_upload_oversized_rejected(self):
        """File vượt quá giới hạn 5 MB bị từ chối 400"""
        oversized_data = b"%PDF-1.4 " + b"X" * (MAX_SUPPORT_FILE_SIZE + 10)
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Đơn quá dung lượng"},
            form_files=[FakeUpload("heavy.pdf", oversized_data)],
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("dung lượng từ 1 byte đến 5 MB", cm.exception.detail)

    def test_file_upload_empty_rejected(self):
        """File rỗng 0 byte bị từ chối 400"""
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "File rỗng"},
            form_files=[FakeUpload("empty.pdf", b"")],
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("dung lượng từ 1 byte đến 5 MB", cm.exception.detail)

    def test_file_upload_invalid_filename_rejected(self):
        """Tên file chứa ký tự điều khiển hoặc quá dài bị từ chối 400"""
        bad_name = "test\x00file.pdf"
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Tên file xấu"},
            form_files=[FakeUpload(bad_name, b"%PDF-1.4 valid")],
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 400)
    def test_file_upload_exceeds_max_files_count_rejected(self):
        """Vượt giới hạn số file (> 5 tệp) bị từ chối 400 Bad Request"""
        six_files = [
            FakeUpload(f"doc_{i}.pdf", b"%PDF-1.4 test") for i in range(6)
        ]
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Đơn gửi quá nhiều file"},
            form_files=six_files,
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("tối đa 5 tệp", cm.exception.detail)

    def test_file_upload_exceeds_total_size_rejected(self):
        """Tổng dung lượng các tệp vượt quá 15 MB bị từ chối 400 Bad Request"""
        # 4 files, mỗi file 4.5 MB = 18 MB > 15 MB
        part_data = b"%PDF-1.4 " + (b"A" * (4 * 1024 * 1024))
        heavy_files = [
            FakeUpload(f"heavy_{i}.pdf", part_data) for i in range(4)
        ]
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Đơn tổng dung lượng quá nặng"},
            form_files=heavy_files,
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Tổng dung lượng các tệp đính kèm không được vượt quá 15 MB", cm.exception.detail)

    def test_file_upload_exceeds_content_length_rejected(self):
        """Content-Length header vượt quá giới hạn 20 MB bị từ chối 400 ngay lập tức"""
        req = fake_request(
            user=self.users["intern1"],
            headers={"content-length": str(25 * 1024 * 1024)},
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Header quá lớn"},
            form_files=[FakeUpload("doc.pdf", b"%PDF-1.4 small")],
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Dung lượng yêu cầu vượt quá giới hạn", cm.exception.detail)

    def test_file_upload_cleanup_on_error(self):
        """Nếu lưu yêu cầu thất bại, các file vừa staging phải được dọn sạch."""
        root = _support_file_root()
        before_files = set(root.glob("*")) if root.exists() else set()
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Đơn xin chứng nhận"},
            form_files=[FakeUpload("temp_doc.pdf", b"%PDF-1.4 test content")],
        )

        with patch.object(
            support_request_routes.SupportRequestService,
            "create_request",
            side_effect=RuntimeError("synthetic persistence failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic persistence failure"):
                asyncio.run(support_request_routes.create_support_request(req, db=self.conn))

        after_files = set(root.glob("*")) if root.exists() else set()
        self.assertEqual(after_files - before_files, set())

    def test_file_download_owner_intern_and_hr_admin_success(self):
        """TTS sở hữu, HR và Admin đều tải được tệp đính kèm hợp lệ qua route download"""
        # Tạo yêu cầu với tệp đính kèm
        pdf_bytes = b"%PDF-1.4 sample file for download test"
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Đơn có file tải"},
            form_files=[FakeUpload("tai_lieu.pdf", pdf_bytes)],
        )
        created = asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        request_id = created["id"]
        file_id = created["attachments"][0]["id"]

        # 1. TTS sở hữu tải thành công
        dl_res_intern = support_request_routes.download_support_request_file(
            request_id=request_id,
            file_id=file_id,
            request=fake_request(user=self.users["intern1"]),
            db=self.conn,
        )
        self.assertIsInstance(dl_res_intern, FileResponse)
        self.assertEqual(dl_res_intern.filename, "tai_lieu.pdf")
        self.assertEqual(dl_res_intern.media_type, "application/pdf")

        # 2. HR tải thành công
        dl_res_hr = support_request_routes.download_support_request_file(
            request_id=request_id,
            file_id=file_id,
            request=fake_request(user=self.users["hr"]),
            db=self.conn,
        )
        self.assertIsInstance(dl_res_hr, FileResponse)
        self.assertEqual(dl_res_hr.filename, "tai_lieu.pdf")

        # 3. Admin tải thành công
        dl_res_admin = support_request_routes.download_support_request_file(
            request_id=request_id,
            file_id=file_id,
            request=fake_request(user=self.users["admin"]),
            db=self.conn,
        )
        self.assertIsInstance(dl_res_admin, FileResponse)
        self.assertEqual(dl_res_admin.filename, "tai_lieu.pdf")

    def test_file_download_idor_other_intern_forbidden(self):
        """TTS khác tải file của người khác qua route download bị chặn 403 Forbidden (chống IDOR)"""
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Đơn bí mật của intern 1"},
            form_files=[FakeUpload("bi_mat.pdf", b"%PDF-1.4 private document")],
        )
        created = asyncio.run(support_request_routes.create_support_request(req, db=self.conn))
        request_id = created["id"]
        file_id = created["attachments"][0]["id"]

        # Intern 2 cố tải file của Intern 1
        with self.assertRaises(HTTPException) as cm:
            support_request_routes.download_support_request_file(
                request_id=request_id,
                file_id=file_id,
                request=fake_request(user=self.users["intern2"]),
                db=self.conn,
            )
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("Không có quyền truy cập tệp đính kèm", cm.exception.detail)

    def test_file_download_mentor_forbidden(self):
        """Mentor cố tải tệp đính kèm bị chặn 403 Forbidden tại route"""
        req = fake_request(
            user=self.users["intern1"],
            form_fields={"loai_yeu_cau": "DOCUMENT", "noi_dung": "Đơn có file"},
            form_files=[FakeUpload("file.pdf", b"%PDF-1.4 mentor test")],
        )
        created = asyncio.run(support_request_routes.create_support_request(req, db=self.conn))

        with self.assertRaises(HTTPException) as cm:
            support_request_routes.download_support_request_file(
                request_id=created["id"],
                file_id=created["attachments"][0]["id"],
                request=fake_request(user=self.users["mentor"]),
                db=self.conn,
            )
        self.assertEqual(cm.exception.status_code, 403)

    def test_file_download_nonexistent_or_path_traversal_404(self):
        """Tải file không tồn tại hoặc storage_key sai quy cách trả về 404 Not Found"""
        req_data = self.create_request(self.intern1_id, {"loai_yeu_cau": "OTHER", "noi_dung": "Không kèm file"})

        # Tải file ID không tồn tại
        with self.assertRaises(HTTPException) as cm:
            support_request_routes.download_support_request_file(
                request_id=req_data["id"],
                file_id=99999,
                request=fake_request(user=self.users["intern1"]),
                db=self.conn,
            )
        self.assertEqual(cm.exception.status_code, 404)

        # Chống path traversal qua storage_key
        with self.assertRaises(HTTPException) as cm:
            support_request_routes._support_file_path("../../windows/win.ini")
        self.assertEqual(cm.exception.status_code, 404)

    # =========================================================================
    # 3. KIỂM THỬ CHỐNG DUPLICATE SUBMIT (GỬI TRÙNG LẶP)
    # =========================================================================

    def test_identical_independent_requests_are_allowed_while_pending(self):
        """Nội dung giống nhau được phép khi mỗi thao tác có idempotency key riêng"""
        payload = {
            "loai_yeu_cau": "CERTIFICATE",
            "noi_dung": "Em cần cấp giấy xác nhận thời gian thực tập.",
        }
        req1 = self.create_request(self.intern1_id, payload)
        self.assertEqual(req1["trang_thai"], "PENDING")

        req2 = self.create_request(self.intern1_id, payload)
        self.assertNotEqual(req1["id"], req2["id"])
        self.assertEqual(req2["trang_thai"], "PENDING")

    def test_missing_idempotency_key_is_rejected(self):
        with self.assertRaises(HTTPException) as cm:
            self.service.create_request(self.intern1_id, {
                "loai_yeu_cau": "OTHER",
                "noi_dung": "A request without an operation key",
            })
        self.assertEqual(cm.exception.status_code, 422)

    def test_duplicate_submit_route_level_json_is_idempotent(self):
        """Route (JSON): cùng idempotency key trả lại cùng bản ghi"""
        payload = {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Xin cấp tài liệu bảo mật", "idempotency_key": "json-operation-1"}

        req1 = fake_request(user=self.users["intern1"], json_body=payload)
        res1 = asyncio.run(support_request_routes.create_support_request(req1, db=self.conn))
        self.assertEqual(res1["trang_thai"], "PENDING")

        req2 = fake_request(user=self.users["intern1"], json_body=payload)
        res2 = asyncio.run(support_request_routes.create_support_request(req2, db=self.conn))
        self.assertEqual(res1["id"], res2["id"])

    def test_duplicate_submit_route_level_multipart_is_idempotent(self):
        """Route (Multipart): cùng idempotency key trả lại cùng bản ghi"""
        fields = {"loai_yeu_cau": "OTHER", "noi_dung": "Hỗ trợ đổi người hướng dẫn", "idempotency_key": "multipart-operation-1"}

        req1 = fake_request(user=self.users["intern1"], form_fields=fields)
        res1 = asyncio.run(support_request_routes.create_support_request(req1, db=self.conn))
        self.assertEqual(res1["trang_thai"], "PENDING")

        req2 = fake_request(user=self.users["intern1"], form_fields=fields)
        res2 = asyncio.run(support_request_routes.create_support_request(req2, db=self.conn))
        self.assertEqual(res1["id"], res2["id"])

    def test_duplicate_submit_allowed_after_resolved(self):
        """Khi yêu cầu trước đã được RESOLVED, TTS ĐƯỢC PHÉP gửi lại yêu cầu cùng loại và nội dung (201 Created)"""
        payload = {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Cần cấp chứng nhận"}
        req1 = self.create_request(self.intern1_id, payload)
        self.service.resolve_request(self.hr_id, req1["id"], "Đã hoàn thành cấp chứng nhận đợt 1.")

        # Gửi lại yêu cầu thứ 2 với nội dung tương tự -> Cho phép thành công
        req2 = self.create_request(self.intern1_id, payload)
        self.assertIsNotNone(req2["id"])
        self.assertNotEqual(req1["id"], req2["id"])
        self.assertEqual(req2["trang_thai"], "PENDING")

    def test_duplicate_submit_allowed_after_rejected(self):
        """Khi yêu cầu trước đã bị REJECTED, TTS ĐƯỢC PHÉP gửi lại yêu cầu cùng loại và nội dung (201 Created)"""
        payload = {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Xin cấp tài liệu chuyên ngành"}
        req1 = self.create_request(self.intern1_id, payload)
        self.service.reject_request(self.hr_id, req1["id"], "Chưa đủ điều kiện xét duyệt.")

        # Gửi lại sau khi bị từ chối -> Cho phép thành công
        req2 = self.create_request(self.intern1_id, payload)
        self.assertIsNotNone(req2["id"])
        self.assertNotEqual(req1["id"], req2["id"])
        self.assertEqual(req2["trang_thai"], "PENDING")

    def test_duplicate_submit_different_content_or_different_user_allowed(self):
        """Cho phép gửi nếu khác nội dung, khác loại, hoặc là TTS khác"""
        self.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Nội dung 1"})

        # Cùng TTS 1 nhưng khác loại -> Thành công
        req_diff_type = self.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Nội dung 1"})
        self.assertEqual(req_diff_type["trang_thai"], "PENDING")

        # Cùng TTS 1 nhưng khác nội dung -> Thành công
        req_diff_content = self.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Nội dung 2"})
        self.assertEqual(req_diff_content["trang_thai"], "PENDING")

        # TTS 2 gửi cùng loại và cùng nội dung với TTS 1 -> Thành công (không bị nhầm lẫn giữa các người dùng)
        req_other_user = self.create_request(self.intern2_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Nội dung 1"})
        self.assertEqual(req_other_user["ma_nguoi_dung"], self.intern2_id)

    def test_concurrent_duplicate_submission_with_idempotency_key(self):
        """Gửi đồng thời nhiều yêu cầu mang cùng idempotency_key: kết quả nhất quán, chỉ tạo ĐÚNG 1 bản ghi trong DB"""
        results = []
        key = "idem-test-race-uuid-1"

        def send_concurrent(idx):
            conn = database.get_db_connection()
            try:
                srv = SupportRequestService(conn)
                res = srv.create_request(
                    self.intern1_id,
                    {
                        "loai_yeu_cau": "CERTIFICATE",
                        "noi_dung": "Yêu cầu cấp giấy chứng nhận có idempotency key",
                        "idempotency_key": key,
                    }
                )
                results.append(("SUCCESS", res["id"]))
            except Exception as e:
                results.append(("ERROR", str(e)))
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(send_concurrent, i) for i in range(4)]
            for f in futures:
                f.result()

        # Tất cả đều thành công và trả về cùng 1 ID yêu cầu duy nhất
        self.assertEqual(len(results), 4)
        statuses = [r[0] for r in results]
        self.assertTrue(all(s == "SUCCESS" for s in statuses), f"Có request thất bại: {results}")
        returned_ids = {r[1] for r in results}
        self.assertEqual(len(returned_ids), 1, "Idempotency key phải trả về cùng một ID")

        # Kiểm tra trong DB chỉ tồn tại ĐÚNG 1 bản ghi mang key này
        rows = self.conn.execute(
            "SELECT count(*) FROM YEU_CAU_HO_TRO WHERE ma_nguoi_dung = ? AND idempotency_key = ?",
            (self.intern1_id, key)
        ).fetchone()
        self.assertEqual(rows[0], 1)

    def test_mysql_duplicate_key_race_returns_committed_idempotent_request(self):
        """A MySQL 1062 unique-key race rolls back and reads the winning request."""
        key = "mysql-race-idempotency-key"
        existing = self.service.create_request(self.intern1_id, {
            "loai_yeu_cau": "OTHER",
            "noi_dung": "Concurrent retry",
            "idempotency_key": key,
        })

        class SyntheticMySQLIntegrityError(Exception):
            pass

        SyntheticMySQLIntegrityError.__name__ = "IntegrityError"
        SyntheticMySQLIntegrityError.__module__ = "pymysql.err"

        class EmptyCursor:
            def fetchone(self):
                return None

        class ConcurrentMySQLWriteProxy:
            def __init__(self, connection):
                self.connection = connection
                self.hide_existing_once = True
                self.raise_duplicate_once = True

            def execute(self, statement, params=()):
                normalized = " ".join(statement.split()).upper()
                if "SELECT ID FROM YEU_CAU_HO_TRO" in normalized and self.hide_existing_once:
                    self.hide_existing_once = False
                    return EmptyCursor()
                if "INSERT INTO YEU_CAU_HO_TRO" in normalized and self.raise_duplicate_once:
                    self.raise_duplicate_once = False
                    raise SyntheticMySQLIntegrityError(1062, "Duplicate entry for idempotency key")
                return self.connection.execute(statement, params)

            def rollback(self):
                return self.connection.rollback()

            def commit(self):
                return self.connection.commit()

        replay = SupportRequestService(ConcurrentMySQLWriteProxy(self.conn)).create_request(
            self.intern1_id,
            {
                "loai_yeu_cau": "OTHER",
                "noi_dung": "Concurrent retry",
                "idempotency_key": key,
            },
        )
        self.assertEqual(replay["id"], existing["id"])
        count = self.conn.execute(
            "SELECT COUNT(*) FROM YEU_CAU_HO_TRO WHERE ma_nguoi_dung = ? AND idempotency_key = ?",
            (self.intern1_id, key),
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_concurrent_identical_content_with_distinct_keys_creates_independent_requests(self):
        """Các yêu cầu độc lập cùng nội dung nhưng key khác nhau không bị gộp hoặc chặn"""
        results = []
        noi_dung = "Yêu cầu tranh chấp không key"

        def send_concurrent(idx):
            conn = database.get_db_connection()
            try:
                srv = SupportRequestService(conn)
                res = srv.create_request(
                    self.intern1_id,
                    {
                        "loai_yeu_cau": "OTHER",
                        "noi_dung": noi_dung,
                        "idempotency_key": f"independent-operation-{idx}",
                    }
                )
                results.append(("SUCCESS", 201, res["id"]))
            except HTTPException as e:
                results.append(("CONFLICT", e.status_code, e.detail))
            except Exception as e:
                results.append(("ERROR", 500, str(e)))
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(send_concurrent, i) for i in range(4)]
            for f in futures:
                f.result()

        successes = [r for r in results if r[0] == "SUCCESS"]
        self.assertEqual(len(successes), 4, results)
        self.assertEqual(len({r[2] for r in successes}), 4)

        # Mỗi key biểu diễn một thao tác riêng, dù nội dung giống nhau.
        rows = self.conn.execute(
            "SELECT count(*) FROM YEU_CAU_HO_TRO WHERE ma_nguoi_dung = ? AND loai_yeu_cau = 'OTHER' AND noi_dung = ?",
            (self.intern1_id, noi_dung)
        ).fetchone()
        self.assertEqual(rows[0], 4)

    # =========================================================================
    # 4. KIỂM THỬ TRẠNG THÁI & STATE TRANSITIONS
    # =========================================================================

    def test_state_transition_pending_to_resolved_success(self):
        """Chuyển trạng thái PENDING -> RESOLVED kèm nội dung phản hồi, người xử lý và thời gian xử lý"""
        req = self.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Xin cấp chứng nhận"})
        self.assertEqual(req["trang_thai"], "PENDING")

        resolved = self.service.resolve_request(self.hr_id, req["id"], "HR xác nhận đã cấp chứng nhận thành công.")
        self.assertEqual(resolved["trang_thai"], "RESOLVED")
        self.assertEqual(resolved["phan_hoi_hr"], "HR xác nhận đã cấp chứng nhận thành công.")
        self.assertEqual(resolved["nguoi_xu_ly"], self.hr_id)
        self.assertIsNotNone(resolved["thoi_gian_xu_ly"])

    def test_state_transition_pending_to_rejected_success(self):
        """Chuyển trạng thái PENDING -> REJECTED kèm lý do từ chối, người xử lý và thời gian xử lý"""
        req = self.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Yêu cầu tài liệu không phù hợp"})
        self.assertEqual(req["trang_thai"], "PENDING")

        rejected = self.service.reject_request(self.hr_id, req["id"], "Tài liệu này thuộc diện bảo mật nội bộ.")
        self.assertEqual(rejected["trang_thai"], "REJECTED")
        self.assertEqual(rejected["phan_hoi_hr"], "Tài liệu này thuộc diện bảo mật nội bộ.")
        self.assertEqual(rejected["nguoi_xu_ly"], self.hr_id)
        self.assertIsNotNone(rejected["thoi_gian_xu_ly"])

    def test_state_transition_terminal_to_terminal_forbidden(self):
        """Không cho phép chuyển trạng thái từ trạng thái kết thúc (RESOLVED hoặc REJECTED) -> 409 Conflict"""
        # 1. Từ RESOLVED không được resolve lại hay reject
        req1 = self.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Req 1"})
        self.service.resolve_request(self.hr_id, req1["id"], "Đã xong.")

        with self.assertRaises(HTTPException) as cm:
            self.service.resolve_request(self.hr_id, req1["id"], "Cố resolve lại")
        self.assertEqual(cm.exception.status_code, 409)

        with self.assertRaises(HTTPException) as cm:
            self.service.reject_request(self.hr_id, req1["id"], "Cố reject sau khi đã resolve")
        self.assertEqual(cm.exception.status_code, 409)

        # 2. Từ REJECTED không được reject lại hay resolve
        req2 = self.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Req 2"})
        self.service.reject_request(self.hr_id, req2["id"], "Từ chối lần đầu.")

        with self.assertRaises(HTTPException) as cm:
            self.service.reject_request(self.hr_id, req2["id"], "Cố reject lại lần 2")
        self.assertEqual(cm.exception.status_code, 409)

        with self.assertRaises(HTTPException) as cm:
            self.service.resolve_request(self.hr_id, req2["id"], "Cố resolve sau khi đã reject")
        self.assertEqual(cm.exception.status_code, 409)

    def test_state_transition_reject_without_reason_rejected(self):
        """Từ chối mà không có lý do hoặc toàn ký tự trắng bị từ chối 400 Bad Request"""
        req = self.create_request(self.intern1_id, {"loai_yeu_cau": "OTHER", "noi_dung": "Hỗ trợ chung"})
        with self.assertRaises(HTTPException) as cm:
            self.service.reject_request(self.hr_id, req["id"], "     ")
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("lý do từ chối", cm.exception.detail)

    def test_state_transition_concurrent_resolve_reject_race_condition(self):
        """Chống tranh chấp khi 2 nhân sự xử lý đồng thời cùng một yêu cầu PENDING: chỉ đúng 1 bên thành công, 1 bên nhận 409"""
        req = self.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Xử lý đồng thời"})

        results = []

        def worker_resolve(actor_id, note):
            conn = database.get_db_connection()
            try:
                srv = SupportRequestService(conn)
                srv.resolve_request(actor_id, req["id"], note)
                results.append(200)
            except HTTPException as e:
                results.append(e.status_code)
            finally:
                conn.close()

        def worker_reject(actor_id, reason):
            conn = database.get_db_connection()
            try:
                srv = SupportRequestService(conn)
                srv.reject_request(actor_id, req["id"], reason)
                results.append(200)
            except HTTPException as e:
                results.append(e.status_code)
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker_resolve, self.hr_id, "HR xử lý")
            f2 = executor.submit(worker_reject, self.admin_id, "Admin từ chối")
            f1.result()
            f2.result()

        # Đúng 1 bên thành công (200), 1 bên bị xung đột (409)
        self.assertEqual(sorted(results), [200, 409])

    # =========================================================================
    # 5. KIỂM THỬ CHỐNG IDOR (INSECURE DIRECT OBJECT REFERENCE)
    # =========================================================================

    def test_idor_intern_cannot_view_other_intern_detail_my_route(self):
        """Chống IDOR (/api/support-requests/my/{id}): TTS 1 không được xem chi tiết của TTS 2 -> 403 Forbidden"""
        req2 = self.create_request(self.intern2_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Đơn của TTS 2"})

        # Qua service
        with self.assertRaises(HTTPException) as cm:
            self.service.get_my_request_detail(self.intern1_id, req2["id"])
        self.assertEqual(cm.exception.status_code, 403)

        # Qua route
        req_obj = fake_request(user=self.users["intern1"])
        with self.assertRaises(HTTPException) as cm:
            support_request_routes.get_my_support_request_detail(req2["id"], req_obj, db=self.conn)
        self.assertEqual(cm.exception.status_code, 403)

    def test_idor_intern_cannot_view_other_intern_detail_shared_route(self):
        """Chống IDOR (/api/support-requests/{id}): TTS 1 gọi route chung xem request của TTS 2 -> 403 Forbidden"""
        req2 = self.create_request(self.intern2_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Tài liệu của TTS 2"})

        req_obj = fake_request(user=self.users["intern1"])
        with self.assertRaises(HTTPException) as cm:
            support_request_routes.get_support_request_detail_hr(req2["id"], req_obj, db=self.conn)
        self.assertEqual(cm.exception.status_code, 403)

    def test_idor_intern_cannot_download_other_intern_file(self):
        """Chống IDOR tải file: TTS 1 không được tải file đính kèm thuộc yêu cầu của TTS 2 -> 403 Forbidden"""
        attachments = [{
            "storage_key": "aabbccddeeff00112233445566778899.pdf",
            "original_filename": "chung_nhan_b.pdf",
            "mime_type": "application/pdf",
            "file_size": 2048,
        }]
        req2 = self.create_request(
            self.intern2_id,
            {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "File của B"},
            attachments=attachments,
        )
        file_id = req2["attachments"][0]["id"]

        with self.assertRaises(HTTPException) as cm:
            self.service.get_attachment(req2["id"], file_id, self.users["intern1"])
        self.assertEqual(cm.exception.status_code, 403)

    def test_idor_intern_cannot_spoof_other_intern_profile_id(self):
        """Chống IDOR khi tạo yêu cầu: TTS 1 cố ý gán ma_ho_so của TTS 2 bị từ chối 403 Forbidden"""
        cursor = self.conn.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet)
            VALUES (?, 'An toàn thông tin', 'DaDuyet')
        """, (self.intern2_id,))
        profile2_id = cursor.lastrowid
        self.conn.commit()

        with self.assertRaises(HTTPException) as cm:
            self.create_request(self.intern1_id, {
                "loai_yeu_cau": "CERTIFICATE",
                "noi_dung": "Gán profile người khác",
                "ma_ho_so": profile2_id,
            })
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("không thuộc về bạn", cm.exception.detail)

    def test_idor_intern_list_strict_isolation(self):
        """Cách ly dữ liệu danh sách: TTS chỉ thấy các yêu cầu của chính mình, không thấy của TTS khác"""
        self.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Của A1"})
        self.create_request(self.intern1_id, {"loai_yeu_cau": "OTHER", "noi_dung": "Của A2"})
        self.create_request(self.intern2_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Của B1"})

        res1 = self.service.list_my_requests(self.intern1_id)
        self.assertEqual(res1["total"], 2)
        self.assertTrue(all(item["ma_nguoi_dung"] == self.intern1_id for item in res1["items"]))

        res2 = self.service.list_my_requests(self.intern2_id)
        self.assertEqual(res2["total"], 1)
        self.assertEqual(res2["items"][0]["ma_nguoi_dung"], self.intern2_id)

    # =========================================================================
    # 6. KIỂM THỬ LỊCH SỬ PHẢN HỒI (FEEDBACK HISTORY & AUDIT TRAIL)
    # =========================================================================

    def test_feedback_history_resolved_contains_response_and_handler_info(self):
        """Lịch sử phản hồi: TTS xem chi tiết yêu cầu RESOLVED thấy đầy đủ phản hồi HR, tên/email người xử lý và ngày xử lý"""
        req = self.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Xin cấp chứng nhận thực tập"})
        self.service.resolve_request(self.hr_id, req["id"], "Giấy chứng nhận đã được xuất và gửi qua email cho bạn.")

        detail = self.service.get_my_request_detail(self.intern1_id, req["id"])
        self.assertEqual(detail["trang_thai"], "RESOLVED")
        self.assertEqual(detail["trang_thai_label"], "Đã giải quyết")
        self.assertEqual(detail["loai_label"], "Giấy chứng nhận")
        self.assertEqual(detail["phan_hoi_hr"], "Giấy chứng nhận đã được xuất và gửi qua email cho bạn.")
        self.assertEqual(detail["noi_dung_phan_hoi"], "Giấy chứng nhận đã được xuất và gửi qua email cho bạn.")
        self.assertIsNotNone(detail["thoi_gian_xu_ly"])
        self.assertEqual(detail["ngay_xu_ly"], detail["thoi_gian_xu_ly"])

        # Kiểm tra thông tin người xử lý phản hồi
        self.assertIsNotNone(detail["nguoi_xu_ly_info"])
        self.assertEqual(detail["nguoi_xu_ly_info"]["ma_nguoi_dung"], self.hr_id)
        self.assertEqual(detail["nguoi_xu_ly_info"]["ho_ten"], "HR Lê Thu C")
        self.assertEqual(detail["nguoi_xu_ly_info"]["email"], self.users["hr"]["email"])

    def test_feedback_history_rejected_contains_reason_and_handler_info(self):
        """Lịch sử phản hồi: TTS xem chi tiết yêu cầu REJECTED thấy rõ lý do từ chối và thông tin HR xử lý"""
        req = self.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Xin tài liệu dự án ABC"})
        self.service.reject_request(self.hr_id, req["id"], "Dự án ABC thuộc diện tài liệu mật cấp công ty, không được cung cấp.")

        detail = self.service.get_my_request_detail(self.intern1_id, req["id"])
        self.assertEqual(detail["trang_thai"], "REJECTED")
        self.assertEqual(detail["trang_thai_label"], "Đã từ chối")
        self.assertEqual(detail["phan_hoi_hr"], "Dự án ABC thuộc diện tài liệu mật cấp công ty, không được cung cấp.")
        self.assertEqual(detail["noi_dung_phan_hoi"], "Dự án ABC thuộc diện tài liệu mật cấp công ty, không được cung cấp.")
        self.assertIsNotNone(detail["thoi_gian_xu_ly"])
        self.assertEqual(detail["nguoi_xu_ly_info"]["ho_ten"], "HR Lê Thu C")

    def test_feedback_history_multiple_requests_chronological_order(self):
        """Lịch sử danh sách yêu cầu hiển thị đúng theo thứ tự thời gian giảm dần với đầy đủ trạng thái khác nhau"""
        r1 = self.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Yêu cầu 1 (Cũ nhất)"})
        self.service.resolve_request(self.hr_id, r1["id"], "Đã xử lý 1")

        r2 = self.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Yêu cầu 2 (Giữa)"})
        self.service.reject_request(self.hr_id, r2["id"], "Từ chối 2")

        r3 = self.create_request(self.intern1_id, {"loai_yeu_cau": "OTHER", "noi_dung": "Yêu cầu 3 (Mới nhất)"})

        history = self.service.list_my_requests(self.intern1_id)
        self.assertEqual(history["total"], 3)
        items = history["items"]

        # Kiểm tra thứ tự mới nhất đứng đầu (r3 -> r2 -> r1)
        self.assertEqual(items[0]["id"], r3["id"])
        self.assertEqual(items[0]["trang_thai"], "PENDING")
        self.assertIsNone(items[0]["nguoi_xu_ly_info"])

        self.assertEqual(items[1]["id"], r2["id"])
        self.assertEqual(items[1]["trang_thai"], "REJECTED")
        self.assertEqual(items[1]["phan_hoi_hr"], "Từ chối 2")

        self.assertEqual(items[2]["id"], r1["id"])
        self.assertEqual(items[2]["trang_thai"], "RESOLVED")
        self.assertEqual(items[2]["phan_hoi_hr"], "Đã xử lý 1")

    def test_feedback_history_notifications_audit_on_resolve_and_reject(self):
        """Khi HR phản hồi giải quyết hoặc từ chối, hệ thống tạo thông báo tự động cho TTS để theo dõi lịch sử phản hồi"""
        req1 = self.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Xin chứng nhận"})
        self.service.resolve_request(self.hr_id, req1["id"], "Đã hoàn thành cấp chứng nhận.")

        req2 = self.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Xin tài liệu mật"})
        self.service.reject_request(self.hr_id, req2["id"], "Từ chối do chính sách bảo mật.")

        notifs = self.conn.execute("""
            SELECT tieu_de, noi_dung, loai, reference_id
            FROM THONG_BAO
            WHERE ma_nguoi_dung = ?
            ORDER BY ma_thong_bao ASC
        """, (self.intern1_id,)).fetchall()

        self.assertEqual(len(notifs), 2)

        # Thông báo cho req1 (RESOLVED)
        self.assertIn("giải quyết", notifs[0]["tieu_de"])
        self.assertIn("Đã hoàn thành cấp chứng nhận", notifs[0]["noi_dung"])
        self.assertEqual(int(notifs[0]["reference_id"]), req1["id"])

        # Thông báo cho req2 (REJECTED)
        self.assertIn("từ chối", notifs[1]["tieu_de"])
        self.assertIn("Từ chối do chính sách bảo mật", notifs[1]["noi_dung"])
        self.assertEqual(int(notifs[1]["reference_id"]), req2["id"])


if __name__ == "__main__":
    unittest.main()
