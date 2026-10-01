"""Isolated regression tests for mailbox RBAC, threads and delivery."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import database
from app.mailbox_content import sanitize_html
from app.mailbox_repository import message_recipients, unread_count
from app.mailbox_service import (
    get_message_detail, list_mailbox_messages, reply_to_message,
    search_recipients, send_message,
)
from app.schemas import MailboxMessageCreate, MailboxReplyCreate


class MailboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-mailbox-", ignore_cleanup_errors=True)
        cls.db_path = Path(cls.temp_dir.name) / "mailbox.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()
        self.db.execute("DELETE FROM INTERNAL_MESSAGE_RECIPIENTS")
        self.db.execute("DELETE FROM INTERNAL_MESSAGES")
        self.db.execute("DELETE FROM INTERNAL_MESSAGE_THREADS")
        self.db.execute("DELETE FROM EMAIL_OUTBOX")
        self.db.execute("DELETE FROM THONG_BAO")
        self.db.execute("DELETE FROM PHAN_CONG_MENTOR_TTS")
        self.users = {}
        for email in (
            "admin@internship.vn", "hr@internship.vn", "mentor@internship.vn",
            "tuan.lm@internship.vn", "lananh.hoang@internship.vn",
        ):
            row = self.db.execute("""
                SELECT ma_nguoi_dung, ho_ten, email, vai_tro, trang_thai, ma_phong_ban
                FROM NGUOI_DUNG WHERE email=?
            """, (email,)).fetchone()
            self.users[email] = dict(row)
        profile = self.db.execute("SELECT ma_ho_so FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung=?", (
            self.users["tuan.lm@internship.vn"]["ma_nguoi_dung"],
        )).fetchone()
        self.db.execute("""
            INSERT INTO PHAN_CONG_MENTOR_TTS
                (ma_nguoi_dung_mentor, ma_ho_so, ma_nguoi_phan_cong)
            VALUES (?, ?, ?)
        """, (
            self.users["mentor@internship.vn"]["ma_nguoi_dung"], profile["ma_ho_so"],
            self.users["admin@internship.vn"]["ma_nguoi_dung"],
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    @staticmethod
    def payload(receiver_ids, **overrides):
        values = {
            "receiverIds": receiver_ids, "groupKeys": [], "category": "THONG_BAO_CHUNG",
            "subject": "Thông báo lịch", "contentHtml": "<p>Lịch họp mới.</p>",
            "sendEmail": False,
        }
        values.update(overrides)
        return MailboxMessageCreate(**values)

    def test_hr_sends_one_message_and_intern_can_read_it(self):
        intern = self.users["tuan.lm@internship.vn"]
        result = send_message(self.db, self.users["hr@internship.vn"], self.payload([intern["ma_nguoi_dung"]]))
        detail = get_message_detail(self.db, result["messageIds"][0], intern["ma_nguoi_dung"])
        self.assertEqual(detail["subject"], "Thông báo lịch")
        self.assertEqual(unread_count(self.db, intern["ma_nguoi_dung"]), 0)

    def test_intern_cannot_read_another_intern_message(self):
        intern = self.users["tuan.lm@internship.vn"]
        other = self.users["lananh.hoang@internship.vn"]
        result = send_message(self.db, self.users["hr@internship.vn"], self.payload([intern["ma_nguoi_dung"]]))
        with self.assertRaises(HTTPException) as caught:
            get_message_detail(self.db, result["messageIds"][0], other["ma_nguoi_dung"])
        self.assertEqual(caught.exception.status_code, 404)

    def test_bulk_message_creates_one_message_with_many_recipients(self):
        ids = [
            self.users["tuan.lm@internship.vn"]["ma_nguoi_dung"],
            self.users["lananh.hoang@internship.vn"]["ma_nguoi_dung"],
        ]
        result = send_message(self.db, self.users["hr@internship.vn"], self.payload(ids))
        recipients = message_recipients(self.db, result["messageIds"][0])
        self.assertEqual((result["sentCount"], len(result["messageIds"]), len(recipients)), (2, 1, 2))

    def test_reply_stays_in_the_same_thread(self):
        intern = self.users["tuan.lm@internship.vn"]
        sent = send_message(self.db, self.users["hr@internship.vn"], self.payload([intern["ma_nguoi_dung"]]))
        original = get_message_detail(self.db, sent["messageIds"][0], intern["ma_nguoi_dung"])
        reply = reply_to_message(
            self.db, intern, sent["messageIds"][0],
            MailboxReplyCreate(contentHtml="<p>Em đã nhận được.</p>"),
        )
        self.assertEqual(reply["threadId"], original["thread_id"])
        self.assertEqual(len(get_message_detail(self.db, reply["messageId"], intern["ma_nguoi_dung"])["thread"]), 2)

    def test_unread_count_changes_after_opening(self):
        intern = self.users["tuan.lm@internship.vn"]
        sent = send_message(self.db, self.users["hr@internship.vn"], self.payload([intern["ma_nguoi_dung"]]))
        self.assertEqual(unread_count(self.db, intern["ma_nguoi_dung"]), 1)
        get_message_detail(self.db, sent["messageIds"][0], intern["ma_nguoi_dung"])
        self.assertEqual(unread_count(self.db, intern["ma_nguoi_dung"]), 0)

    def test_invalid_or_forbidden_recipient_is_rejected(self):
        intern = self.users["tuan.lm@internship.vn"]
        other = self.users["lananh.hoang@internship.vn"]
        with self.assertRaises(HTTPException) as caught:
            send_message(self.db, intern, self.payload([other["ma_nguoi_dung"]], category="XIN_HO_TRO"))
        self.assertEqual(caught.exception.status_code, 403)

    def test_mentor_can_only_find_assigned_intern(self):
        results = search_recipients(self.db, self.users["mentor@internship.vn"], "internship.vn")
        emails = {row["email"] for row in results}
        self.assertIn("tuan.lm@internship.vn", emails)
        self.assertNotIn("lananh.hoang@internship.vn", emails)

    def test_send_email_creates_idempotent_outbox_item(self):
        intern = self.users["tuan.lm@internship.vn"]
        result = send_message(
            self.db, self.users["hr@internship.vn"],
            self.payload([intern["ma_nguoi_dung"]], sendEmail=True),
        )
        message_id = result["messageIds"][0]
        rows = self.db.execute("""
            SELECT deduplication_key, status FROM EMAIL_OUTBOX
            WHERE reference_type='internal_message' AND reference_id=?
        """, (str(message_id),)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "PENDING")
        self.assertEqual(rows[0]["deduplication_key"], f"mailbox:{message_id}:{intern['ma_nguoi_dung']}")

    def test_search_filter_and_pagination_are_server_side(self):
        intern = self.users["tuan.lm@internship.vn"]
        hr = self.users["hr@internship.vn"]
        for index in range(3):
            send_message(self.db, hr, self.payload(
                [intern["ma_nguoi_dung"]], subject=f"Báo cáo tuần {index}",
                category="XIN_HO_TRO" if index == 2 else "THONG_BAO_CHUNG",
            ))
        page = list_mailbox_messages(
            self.db, intern["ma_nguoi_dung"], "inbox", 1, 1,
            "unread", "XIN_HO_TRO", "Báo cáo",
        )
        self.assertEqual((page["totalItems"], page["totalPages"], len(page["items"])), (1, 1, 1))

    def test_dangerous_html_is_removed(self):
        sanitized = sanitize_html(
            '<p onclick="steal()">Xin chào<script>alert(1)</script>'
            '<a href="javascript:alert(1)">link</a><strong>an toàn</strong></p>'
        )
        self.assertNotIn("script", sanitized)
        self.assertNotIn("onclick", sanitized)
        self.assertNotIn("javascript:", sanitized)
        self.assertIn("<strong>an toàn</strong>", sanitized)

    def test_template_bulk_personalizes_each_recipient(self):
        interns = [self.users["tuan.lm@internship.vn"], self.users["lananh.hoang@internship.vn"]]
        template_id = self.db.execute("""
            SELECT id FROM EMAIL_TEMPLATES WHERE template_code='MAU_BO_SUNG_HO_SO'
        """).fetchone()["id"]
        result = send_message(self.db, self.users["hr@internship.vn"], self.payload(
            [user["ma_nguoi_dung"] for user in interns], templateId=template_id,
        ))
        bodies = [row["content_html"] for row in self.db.execute("""
            SELECT content_html FROM INTERNAL_MESSAGES ORDER BY id
        """).fetchall()]
        self.assertEqual(len(result["messageIds"]), 2)
        self.assertIn(interns[0]["ho_ten"], bodies[0])
        self.assertIn(interns[1]["ho_ten"], bodies[1])

    def test_duplicate_mailbox_message_within_cooldown_is_rejected(self):
        intern = self.users["tuan.lm@internship.vn"]
        hr = self.users["hr@internship.vn"]
        payload = self.payload([intern["ma_nguoi_dung"]], subject="Yêu cầu hỗ trợ", contentHtml="<p>Cần hỗ trợ thiết bị</p>")
        send_message(self.db, hr, payload)
        self.db.commit()

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            send_message(self.db, hr, payload)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("DUPLICATE_EMAIL_SUPPRESSED", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
