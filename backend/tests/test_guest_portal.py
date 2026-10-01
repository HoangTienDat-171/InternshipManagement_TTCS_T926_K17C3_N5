"""Automated tests for Guest (Khách vãng lai) portal and security workflows."""
import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException, UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import database
from app.guest_security import (
    RATE_LIMIT_BUCKETS,
    check_guest_rate_limit,
    generate_captcha,
    validate_guest_cv_file,
    verify_captcha,
)
from app.routes.guest_routes import (
    get_captcha,
    get_guest_program_detail,
    list_guest_programs,
    submit_guest_application,
    track_guest_application,
)


class GuestPortalWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-guest-test-", ignore_cleanup_errors=True)
        cls.db_path = Path(cls.temp_dir.name) / "guest_test.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()
        conn = database.get_db_connection()
        conn.execute("""
            INSERT OR IGNORE INTO CHUONG_TRINH_THUC_TAP
                (ma_ct, ten_ct, ma_phong_ban, ngay_bat_dau, ngay_ket_thuc, chi_tieu, mo_ta_cong_viec, yeu_cau, quyen_loi, trang_thai)
            VALUES ('TTS-TEST-01', 'Thực tập sinh Backend Python', 1, '2026-10-01', '2026-12-31', 5, 'Mô tả', 'Python, FastAPI', 'Phụ cấp', 'DangMo')
        """)
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        RATE_LIMIT_BUCKETS.clear()
        self.db = database.get_db_connection()

    def tearDown(self):
        self.db.close()

    def test_public_browsing_open_programs(self):
        """Khách vãng lai có thể xem danh sách và chi tiết các vị trí thực tập đang mở."""
        result = list_guest_programs(keyword=None, department_id=None, page=1, page_size=10, db=self.db)
        self.assertIn("items", result)
        self.assertIn("total", result)
        self.assertGreater(result["total"], 0)

        # Check fields of the first job
        job = result["items"][0]
        self.assertIn("id", job)
        self.assertIn("title", job)
        self.assertIn("department_name", job)
        self.assertIn("requirements", job)
        self.assertIn("deadline", job)

        # Detail endpoint
        detail = get_guest_program_detail(program_id=job["id"], db=self.db)
        self.assertEqual(detail["id"], job["id"])
        self.assertEqual(detail["title"], job["title"])

    def test_captcha_generation_and_verification(self):
        """Kiểm tra mã bảo vệ (Captcha) token HMAC và xác thực kết quả."""
        captcha_res = get_captcha()
        token = captcha_res["captcha_token"]
        question = captcha_res["question"]
        self.assertTrue(question.endswith("= ?"))

        parts = token.split(":")
        self.assertEqual(len(parts), 3)
        expected_ans = parts[0]

        # Valid answer
        self.assertTrue(verify_captcha(token, expected_ans))
        # Wrong answer
        self.assertFalse(verify_captcha(token, "999"))
        # Tampered signature
        tampered_token = f"{expected_ans}:{parts[1]}:bad_signature"
        self.assertFalse(verify_captcha(tampered_token, expected_ans))

    def test_cv_file_validation_magic_bytes_and_size(self):
        """Kiểm tra phát hiện tệp giả mạo extension và giới hạn dung lượng 5MB."""
        # 1. Reject non-pdf/docx extension
        with self.assertRaises(HTTPException) as ctx:
            validate_guest_cv_file("resume.exe", b"executable_data")
        self.assertEqual(ctx.exception.status_code, 400)

        # 2. Reject fake PDF (wrong magic bytes)
        with self.assertRaises(HTTPException) as ctx:
            validate_guest_cv_file("fake.pdf", b"NOT_A_REAL_PDF_HEADER")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("không hợp lệ", ctx.exception.detail)

        # 3. Valid PDF magic bytes
        mime = validate_guest_cv_file("cv.pdf", b"%PDF-1.4\nTest PDF content")
        self.assertEqual(mime, "application/pdf")

        # 4. Reject oversized file > 5MB
        oversized = b"%PDF-1.4\n" + (b"X" * (5 * 1024 * 1024 + 10))
        with self.assertRaises(HTTPException) as ctx:
            validate_guest_cv_file("huge.pdf", oversized)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("5MB", ctx.exception.detail)

    def test_submit_guest_application_and_tracking_workflow(self):
        """Quy trình nộp đơn ứng tuyển khách vãng lai và tra cứu tiến độ trạng thái."""
        captcha_res = get_captcha()
        token = captcha_res["captcha_token"]
        answer = token.split(":")[0]

        valid_pdf_content = b"%PDF-1.4\nCandidate CV Content Sample"
        cv_file = UploadFile(
            filename="my_resume.pdf",
            file=io.BytesIO(valid_pdf_content),
        )

        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.50"
        mock_request.headers = {}
        mock_request.base_url = "http://testserver/"

        # 1. Submit application
        result = asyncio.run(submit_guest_application(
            request=mock_request,
            program_id=1,
            full_name="Nguyen Hoang Long",
            email="hoanglong.test@example.com",
            phone="0918889999",
            university="Đại học Bách Khoa Hà Nội",
            major="Kỹ thuật Phần mềm",
            year_of_study="Năm 4",
            expected_duration="3 tháng",
            portfolio_link="https://github.com/longtest",
            captcha_token=token,
            captcha_answer=answer,
            cv_file=cv_file,
            db=self.db,
        ))

        self.assertTrue(result["success"])
        self.assertTrue(result["tracking_code"].startswith("APP-"))
        tracking_code = result["tracking_code"]

        # 2. Verify confirmation email was queued in EMAIL_OUTBOX
        email_row = self.db.execute(
            "SELECT * FROM EMAIL_OUTBOX WHERE recipient_email = ? ORDER BY id DESC LIMIT 1",
            ("hoanglong.test@example.com",)
        ).fetchone()
        self.assertIsNotNone(email_row)
        self.assertIn(tracking_code, email_row["body"])
        self.assertIn(tracking_code, email_row["subject"])

        # 3. Track with correct tracking code and correct email
        track_data = track_guest_application(
            tracking_code=tracking_code,
            email="hoanglong.test@example.com",
            db=self.db,
        )
        self.assertEqual(track_data["tracking_code"], tracking_code)
        self.assertEqual(track_data["candidate_name"], "Nguyen Hoang Long")
        self.assertEqual(track_data["status"], "PENDING")
        self.assertNotIn("ghi_chu_noi_bo", track_data)
        self.assertNotIn("duong_dan_cv", track_data)

        # 4. Anti-enumeration: Track with correct tracking code but wrong email -> 404
        with self.assertRaises(HTTPException) as ctx:
            track_guest_application(
                tracking_code=tracking_code,
                email="wrong_email@gmail.com",
                db=self.db,
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_anti_abuse_rate_limiting(self):
        """Kiểm tra giới hạn tần suất 5 request / 10 phút từ cùng IP."""
        req = MagicMock()
        req.client.host = "192.168.1.100"
        req.headers = {}

        # 5 allowed calls
        for _ in range(5):
            check_guest_rate_limit(req, limit=5, window_seconds=600)

        # 6th call must trigger HTTP 429
        with self.assertRaises(HTTPException) as ctx:
            check_guest_rate_limit(req, limit=5, window_seconds=600)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("quá số lần cho phép", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
