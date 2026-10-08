from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import database
from app.routes import support_request_routes
from app.schemas import SupportRequestCreate, SupportRequestResolve, SupportRequestReject
from app.support_request_service import SupportRequestService


def fake_request(user=None, headers=None, json_body=None):
    req = SimpleNamespace(
        state=SimpleNamespace(current_user=user),
        headers=headers or {},
    )
    async def _json():
        return json_body
    req.json = _json
    return req


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
        import random
        self.conn = database.get_db_connection()
        self.service = SupportRequestService(self.conn)

        uid = uuid.uuid4().hex[:6]
        # Tạo người dùng mẫu với email và số điện thoại duy nhất tránh vi phạm unique constraint
        self.intern1_id = self._insert_user("TTS Nguyễn Văn A", f"tts.a.{uid}@test.vn", "ThucTapSinh")
        self.intern2_id = self._insert_user("TTS Trần Thị B", f"tts.b.{uid}@test.vn", "ThucTapSinh")
        self.hr_id = self._insert_user("HR Lê Thu C", f"hr.c.{uid}@test.vn", "HR")
        self.admin_id = self._insert_user("Admin Hoàng D", f"admin.d.{uid}@test.vn", "Admin")
        self.mentor_id = self._insert_user("Mentor Vũ E", f"mentor.e.{uid}@test.vn", "Mentor")

        # Tạo hồ sơ thực tập cho TTS 1
        cursor = self.conn.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet)
            VALUES (?, 'Công nghệ thông tin', 'DaDuyet')
        """, (self.intern1_id,))
        self.profile1_id = cursor.lastrowid
        self.conn.commit()

        self.users = {
            "intern1": {"ma_nguoi_dung": self.intern1_id, "vai_tro": "ThucTapSinh", "ho_ten": "TTS Nguyễn Văn A"},
            "intern2": {"ma_nguoi_dung": self.intern2_id, "vai_tro": "ThucTapSinh", "ho_ten": "TTS Trần Thị B"},
            "hr": {"ma_nguoi_dung": self.hr_id, "vai_tro": "HR", "ho_ten": "HR Lê Thu C"},
            "admin": {"ma_nguoi_dung": self.admin_id, "vai_tro": "Admin", "ho_ten": "Admin Hoàng D"},
            "mentor": {"ma_nguoi_dung": self.mentor_id, "vai_tro": "Mentor", "ho_ten": "Mentor Vũ E"},
        }

    def tearDown(self):
        try:
            self.conn.execute("DELETE FROM YEU_CAU_HO_TRO_TEP")
            self.conn.execute("DELETE FROM YEU_CAU_HO_TRO")
            self.conn.execute("DELETE FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung IN (?, ?)", (self.intern1_id, self.intern2_id))
            self.conn.execute("DELETE FROM NGUOI_DUNG WHERE ma_nguoi_dung IN (?, ?, ?, ?, ?)", (self.intern1_id, self.intern2_id, self.hr_id, self.admin_id, self.mentor_id))
            self.conn.commit()
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

    # -------------------------------------------------------------------------
    # US27 — TTS TẠO VÀ XEM YÊU CẦU
    # -------------------------------------------------------------------------

    def test_intern_create_valid_request(self):
        """TTS tạo yêu cầu hỗ trợ hợp lệ, mặc định PENDING"""
        payload = {
            "loai_yeu_cau": "CERTIFICATE",
            "noi_dung": "Em cần cấp giấy chứng nhận thực tập để nộp về trường đại học.",
            "ma_ho_so": self.profile1_id,
        }
        req = self.service.create_request(self.intern1_id, payload)
        self.assertIsNotNone(req["id"])
        self.assertEqual(req["trang_thai"], "PENDING")
        self.assertEqual(req["loai_yeu_cau"], "CERTIFICATE")
        self.assertEqual(req["noi_dung"], payload["noi_dung"])
        self.assertEqual(req["ma_nguoi_dung"], self.intern1_id)
        self.assertIsNone(req["phan_hoi_hr"])
        self.assertIsNone(req["nguoi_xu_ly"])

    def test_intern_create_empty_content_rejected(self):
        """TTS tạo nội dung rỗng hoặc toàn dấu cách bị từ chối 422"""
        with self.assertRaises(HTTPException) as cm:
            self.service.create_request(self.intern1_id, {
                "loai_yeu_cau": "DOCUMENT",
                "noi_dung": "   ",
            })
        self.assertEqual(cm.exception.status_code, 422)

    def test_intern_create_invalid_type_rejected(self):
        """Loại yêu cầu không thuộc danh mục hợp lệ bị từ chối 422"""
        with self.assertRaises(HTTPException) as cm:
            self.service.create_request(self.intern1_id, {
                "loai_yeu_cau": "UNKNOWN_TYPE",
                "noi_dung": "Nội dung hợp lệ",
            })
        self.assertEqual(cm.exception.status_code, 422)

    def test_intern_cannot_spoof_owner_status_or_handler(self):
        """Không cho phép gán đè owner, status hay handler qua payload"""
        payload = {
            "loai_yeu_cau": "OTHER",
            "noi_dung": "Yêu cầu cần kiểm tra",
            "trang_thai": "RESOLVED",
            "ma_nguoi_dung": self.intern2_id,
            "nguoi_xu_ly": self.hr_id,
            "phan_hoi_hr": "HR phản hồi giả mạo",
        }
        # Gọi trực tiếp qua service với intern1_id
        req = self.service.create_request(self.intern1_id, payload)
        self.assertEqual(req["ma_nguoi_dung"], self.intern1_id)
        self.assertEqual(req["trang_thai"], "PENDING")
        self.assertIsNone(req["nguoi_xu_ly"])
        self.assertIsNone(req["phan_hoi_hr"])

    def test_intern_cannot_use_other_intern_profile(self):
        """TTS không được chọn ma_ho_so của người khác"""
        # Tạo hồ sơ cho intern 2
        cursor = self.conn.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, chuyen_nganh, trang_thai_xet_duyet)
            VALUES (?, 'An toàn thông tin', 'DaDuyet')
        """, (self.intern2_id,))
        profile2_id = cursor.lastrowid
        self.conn.commit()

        # Intern 1 cố tình gửi ma_ho_so của intern 2
        with self.assertRaises(HTTPException) as cm:
            self.service.create_request(self.intern1_id, {
                "loai_yeu_cau": "CERTIFICATE",
                "noi_dung": "Xin giấy chứng nhận",
                "ma_ho_so": profile2_id,
            })
        self.assertEqual(cm.exception.status_code, 403)

    def test_intern_list_own_requests_isolation(self):
        """TTS chỉ xem được danh sách yêu cầu của chính mình, không thấy của TTS khác"""
        self.service.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Tài liệu A"})
        self.service.create_request(self.intern1_id, {"loai_yeu_cau": "OTHER", "noi_dung": "Hỗ trợ A2"})
        self.service.create_request(self.intern2_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Chứng nhận B"})

        list1 = self.service.list_my_requests(self.intern1_id)
        self.assertEqual(list1["total"], 2)
        self.assertTrue(all(item["ma_nguoi_dung"] == self.intern1_id for item in list1["items"]))

        list2 = self.service.list_my_requests(self.intern2_id)
        self.assertEqual(list2["total"], 1)
        self.assertEqual(list2["items"][0]["ma_nguoi_dung"], self.intern2_id)

    def test_intern_cannot_view_other_intern_request_detail_idor(self):
        """Chống IDOR: TTS không xem được chi tiết yêu cầu của TTS khác"""
        req_b = self.service.create_request(self.intern2_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Đơn của B"})

        with self.assertRaises(HTTPException) as cm:
            self.service.get_my_request_detail(self.intern1_id, req_b["id"])
        self.assertEqual(cm.exception.status_code, 403)

    # -------------------------------------------------------------------------
    # US28 — HR / ADMIN XỬ LÝ VÀ PHẢN HỒI
    # -------------------------------------------------------------------------

    def test_hr_and_admin_can_list_and_filter(self):
        """HR/Admin xem danh sách toàn bộ và lọc theo trạng thái / loại"""
        req1 = self.service.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Yêu cầu 1"})
        req2 = self.service.create_request(self.intern2_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Yêu cầu 2"})
        self.service.resolve_request(self.hr_id, req1["id"], "Đã hoàn thành cấp chứng nhận.")

        all_res = self.service.list_all_requests()
        self.assertGreaterEqual(all_res["total"], 2)

        # Lọc trạng thái PENDING
        pending_res = self.service.list_all_requests(status_filter="PENDING")
        self.assertEqual(pending_res["total"], 1)
        self.assertEqual(pending_res["items"][0]["id"], req2["id"])

        # Lọc loại CERTIFICATE
        cert_res = self.service.list_all_requests(type_filter="CERTIFICATE")
        self.assertEqual(cert_res["total"], 1)
        self.assertEqual(cert_res["items"][0]["id"], req1["id"])

    def test_mentor_has_no_access_to_hr_endpoints(self):
        """Mentor không có quyền truy cập các endpoint quản lý yêu cầu hỗ trợ"""
        req = self.service.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Yêu cầu"})

        mentor_req = fake_request(user=self.users["mentor"])
        with self.assertRaises(HTTPException) as cm:
            support_request_routes.list_support_requests_hr(mentor_req, db=self.conn)
        self.assertEqual(cm.exception.status_code, 403)

        with self.assertRaises(HTTPException) as cm:
            support_request_routes.get_support_request_detail_hr(req["id"], mentor_req, db=self.conn)
        self.assertEqual(cm.exception.status_code, 403)

    def test_hr_resolve_pending_request_success(self):
        """HR giải quyết yêu cầu PENDING, lưu phản hồi, actor và audit thời gian"""
        req = self.service.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Xin chứng nhận"})
        resolved = self.service.resolve_request(self.hr_id, req["id"], "Giấy chứng nhận đã được gửi về email.")

        self.assertEqual(resolved["trang_thai"], "RESOLVED")
        self.assertEqual(resolved["phan_hoi_hr"], "Giấy chứng nhận đã được gửi về email.")
        self.assertEqual(resolved["nguoi_xu_ly"], self.hr_id)
        self.assertIsNotNone(resolved["thoi_gian_xu_ly"])

        # Kiểm tra notification đã được ghi nhận cho intern
        notif = self.conn.execute("SELECT * FROM THONG_BAO WHERE ma_nguoi_dung = ?", (self.intern1_id,)).fetchone()
        self.assertIsNotNone(notif)
        self.assertIn("giải quyết", notif["tieu_de"])

    def test_hr_reject_pending_request_with_reason_success(self):
        """HR từ chối yêu cầu PENDING có lý do rõ ràng"""
        req = self.service.create_request(self.intern1_id, {"loai_yeu_cau": "OTHER", "noi_dung": "Yêu cầu không phù hợp"})
        rejected = self.service.reject_request(self.hr_id, req["id"], "Kỳ thực tập chưa kết thúc, không thể cấp giấy chứng nhận sớm.")

        self.assertEqual(rejected["trang_thai"], "REJECTED")
        self.assertEqual(rejected["phan_hoi_hr"], "Kỳ thực tập chưa kết thúc, không thể cấp giấy chứng nhận sớm.")
        self.assertEqual(rejected["nguoi_xu_ly"], self.hr_id)
        self.assertIsNotNone(resolved_time := rejected["thoi_gian_xu_ly"])

    def test_hr_reject_without_reason_rejected(self):
        """Từ chối thiếu lý do bị từ chối 400"""
        req = self.service.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Cần tài liệu"})
        with self.assertRaises(HTTPException) as cm:
            self.service.reject_request(self.hr_id, req["id"], "   ")
        self.assertEqual(cm.exception.status_code, 400)

    def test_cannot_reprocess_terminal_request(self):
        """Không được giải quyết hoặc từ chối lại yêu cầu đã kết thúc (RESOLVED/REJECTED)"""
        req = self.service.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Chứng nhận"})
        self.service.resolve_request(self.hr_id, req["id"], "Đã cấp.")

        # Thử resolve lại lần nữa
        with self.assertRaises(HTTPException) as cm:
            self.service.resolve_request(self.hr_id, req["id"], "Cấp lại lần 2")
        self.assertEqual(cm.exception.status_code, 409)

        # Thử reject yêu cầu đã RESOLVED
        with self.assertRaises(HTTPException) as cm:
            self.service.reject_request(self.hr_id, req["id"], "Từ chối sau khi đã cấp")
        self.assertEqual(cm.exception.status_code, 409)

    def test_concurrent_resolve_reject_race_condition(self):
        """Chống tranh chấp khi 2 HR xử lý đồng thời: chỉ 1 bên thành công, 1 bên nhận 409 Conflict"""
        req = self.service.create_request(self.intern1_id, {"loai_yeu_cau": "DOCUMENT", "noi_dung": "Tài liệu đồng thời"})

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

    def test_intern_views_hr_response_read_only(self):
        """TTS thấy nội dung phản hồi của HR khi xem chi tiết"""
        req = self.service.create_request(self.intern1_id, {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Cần hỗ trợ"})
        self.service.resolve_request(self.hr_id, req["id"], "Phản hồi chính thức từ phòng nhân sự.")

        detail = self.service.get_my_request_detail(self.intern1_id, req["id"])
        self.assertEqual(detail["trang_thai"], "RESOLVED")
        self.assertEqual(detail["phan_hoi_hr"], "Phản hồi chính thức từ phòng nhân sự.")
        self.assertEqual(detail["handler_name"], "HR Lê Thu C")

    def test_attachment_download_authorization(self):
        """Quyền tải tệp đính kèm: TTS sở hữu và HR tải được; TTS khác và Mentor bị 403"""
        attachments = [{
            "storage_key": "12345678901234567890123456789012.pdf",
            "original_filename": "chung_nhan.pdf",
            "mime_type": "application/pdf",
            "file_size": 1024,
        }]
        req = self.service.create_request(
            self.intern1_id,
            {"loai_yeu_cau": "CERTIFICATE", "noi_dung": "Kèm file"},
            attachments=attachments,
        )
        file_id = req["attachments"][0]["id"]

        # 1. TTS sở hữu tải được
        att1 = self.service.get_attachment(req["id"], file_id, self.users["intern1"])
        self.assertEqual(att1["original_filename"], "chung_nhan.pdf")

        # 2. HR tải được
        att_hr = self.service.get_attachment(req["id"], file_id, self.users["hr"])
        self.assertEqual(att_hr["original_filename"], "chung_nhan.pdf")

        # 3. TTS khác bị từ chối 403
        with self.assertRaises(HTTPException) as cm:
            self.service.get_attachment(req["id"], file_id, self.users["intern2"])
        self.assertEqual(cm.exception.status_code, 403)

        # 4. Mentor bị từ chối 403
        with self.assertRaises(HTTPException) as cm:
            self.service.get_attachment(req["id"], file_id, self.users["mentor"])
        self.assertEqual(cm.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
