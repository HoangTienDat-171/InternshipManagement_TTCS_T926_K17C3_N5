"""Automated tests for email deduplication, content fingerprinting, and rate-limiting locks."""
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app import database
from app.email_deduplication import (
    DuplicateEmailSuppressedError,
    check_and_acquire_dedup_lock,
    compute_email_dedup_hash,
)
from app.email_service import enqueue_email


class EmailDeduplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-dedup-test-", ignore_cleanup_errors=True)
        cls.db_path = Path(cls.temp_dir.name) / "dedup_test.sqlite3"
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
        self.db.execute("DELETE FROM EMAIL_DEDUP_LOCKS")
        self.db.execute("DELETE FROM EMAIL_ATTACHMENTS")
        self.db.execute("DELETE FROM EMAIL_OUTBOX")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_fingerprint_deterministic_and_normalized(self):
        """Hash is identical for same content regardless of whitespace or HTML casing."""
        hash1 = compute_email_dedup_hash(
            recipient_email="tts1@example.com",
            subject="Thông báo thực tập",
            body_text="Chào bạn, vui lòng nộp báo cáo tuần.",
        )
        hash2 = compute_email_dedup_hash(
            recipient_email="  TTS1@EXAMPLE.COM  ",
            subject="Thông báo thực tập",
            body_text="  Chào bạn,   vui lòng nộp báo cáo tuần.  ",
        )
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)

    def test_sending_unique_emails_passes(self):
        """Distinct emails to the same recipient are both successfully enqueued."""
        id1 = enqueue_email(
            db=self.db,
            recipient_email="tts1@example.com",
            subject="Thư chào mừng",
            body_text="Chào mừng bạn đến với chương trình.",
        )
        id2 = enqueue_email(
            db=self.db,
            recipient_email="tts1@example.com",
            subject="Lịch phỏng vấn",
            body_text="Lịch phỏng vấn của bạn là 9h sáng mai.",
        )
        self.db.commit()
        self.assertIsNotNone(id1)
        self.assertIsNotNone(id2)
        self.assertNotEqual(id1, id2)

    def test_sending_identical_email_within_cooldown_rejected(self):
        """Test nội dung giống nhau gửi cùng người nhận: gửi lại trong cooldown window bị chặn."""
        recipient = "tts1@example.com"
        subject = "Kết quả xét duyệt hồ sơ"
        body = "Hồ sơ của bạn đã được duyệt thành công."

        # First send -> passes
        id1 = enqueue_email(
            db=self.db,
            recipient_email=recipient,
            subject=subject,
            body_text=body,
        )
        self.db.commit()
        self.assertIsNotNone(id1)

        # Second send within cooldown window -> suppressed with DuplicateEmailSuppressedError
        with self.assertRaises(DuplicateEmailSuppressedError) as ctx:
            enqueue_email(
                db=self.db,
                recipient_email=recipient,
                subject=subject,
                body_text=body,
            )
        self.assertIn("DUPLICATE_EMAIL_SUPPRESSED", str(ctx.exception))
        self.assertEqual(ctx.exception.recipient, recipient)

        # Verify only 1 record is persisted in EMAIL_OUTBOX
        count = self.db.execute("SELECT COUNT(*) AS total FROM EMAIL_OUTBOX").fetchone()["total"]
        self.assertEqual(count, 1)

    def test_identical_content_to_different_recipients_allowed(self):
        """Test nội dung giống nhau gửi khác người nhận: cả hai người đều nhận được bình thường."""
        subject = "Thông báo chung: Khai giảng đợt thực tập"
        body = "Kính mời tất cả thực tập sinh tham gia buổi gặp mặt sáng thứ Hai."

        id1 = enqueue_email(
            db=self.db,
            recipient_email="tts1@example.com",
            subject=subject,
            body_text=body,
        )
        id2 = enqueue_email(
            db=self.db,
            recipient_email="tts2@example.com",
            subject=subject,
            body_text=body,
        )
        self.db.commit()

        self.assertIsNotNone(id1)
        self.assertIsNotNone(id2)
        self.assertNotEqual(id1, id2)
        count = self.db.execute("SELECT COUNT(*) AS total FROM EMAIL_OUTBOX").fetchone()["total"]
        self.assertEqual(count, 2)

    def test_identical_email_allowed_after_cooldown_expires(self):
        """Test sau khi hết thời gian cooldown: hệ thống cho phép gửi lại bình thường."""
        recipient = "tts1@example.com"
        subject = "Nhắc nhở nộp báo cáo"
        body = "Vui lòng nộp báo cáo trước 17h."

        # Send with 1 second window
        with patch.dict(os.environ, {"EMAIL_DEDUP_WINDOW_SECONDS": "1"}):
            id1 = enqueue_email(
                db=self.db,
                recipient_email=recipient,
                subject=subject,
                body_text=body,
            )
            self.db.commit()
            self.assertIsNotNone(id1)

            # Manually expire the lock timestamp in DB to simulate cooldown expiration
            self.db.execute(
                """UPDATE EMAIL_DEDUP_LOCKS
                   SET expires_at = '2020-01-01 00:00:00'
                   WHERE recipient_email = ?""",
                (recipient,),
            )
            self.db.execute(
                """UPDATE EMAIL_OUTBOX
                   SET created_at = '2020-01-01 00:00:00'
                   WHERE recipient_email = ?""",
                (recipient,),
            )
            self.db.commit()

            # Resend after expiry -> allowed!
            id2 = enqueue_email(
                db=self.db,
                recipient_email=recipient,
                subject=subject,
                body_text=body,
            )
            self.db.commit()
            self.assertIsNotNone(id2)
            self.assertNotEqual(id1, id2)

    def test_expired_lock_race_suppresses_request_that_loses_refresh(self):
        recipient = "expired-race@example.com"
        dedup_hash = "b" * 64
        self.db.execute(
            """INSERT INTO EMAIL_DEDUP_LOCKS
               (recipient_email, dedup_hash, expires_at, last_outbox_id)
               VALUES (?, ?, '2020-01-01 00:00:00', 23)""",
            (recipient, dedup_hash),
        )
        self.db.commit()

        class InterleavedDB:
            def execute(inner_self, statement, params=()):
                if "UPDATE EMAIL_DEDUP_LOCKS" in statement and "expires_at <= ?" in statement:
                    self.db.execute(
                        """UPDATE EMAIL_DEDUP_LOCKS SET expires_at='2999-01-01 00:00:00'
                           WHERE recipient_email=? AND dedup_hash=?""",
                        (recipient, dedup_hash),
                    )
                return self.db.execute(statement, params)

        allowed, status_msg, original_id = check_and_acquire_dedup_lock(
            InterleavedDB(), recipient, dedup_hash,
        )

        self.assertFalse(allowed)
        self.assertEqual(status_msg, "DUPLICATE_EMAIL_SUPPRESSED")
        self.assertEqual(original_id, 23)

    def test_concurrent_requests_race_condition_only_one_succeeds(self):
        """Race condition test: Multiple concurrent threads attempt identical send -> only 1 succeeds."""
        recipient = "tts_concurrent@example.com"
        subject = "Quyết định tiếp nhận"
        body = "Chúc mừng bạn đã trúng tuyển chương trình thực tập."
        worker_count = 6

        successes = []
        suppressed = []

        def worker_send():
            # Each worker uses its own DB connection to simulate real concurrent requests
            conn = database.get_db_connection()
            try:
                outbox_id = enqueue_email(
                    db=conn,
                    recipient_email=recipient,
                    subject=subject,
                    body_text=body,
                )
                conn.commit()
                return "SUCCESS", outbox_id
            except DuplicateEmailSuppressedError as exc:
                conn.rollback()
                return "SUPPRESSED", str(exc)
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(worker_send) for _ in range(worker_count)]
            for f in futures:
                res, info = f.result()
                if res == "SUCCESS":
                    successes.append(info)
                else:
                    suppressed.append(info)

        # EXACTLY 1 succeeds, all others are suppressed
        self.assertEqual(len(successes), 1, f"Expected exactly 1 success, got {len(successes)}")
        self.assertEqual(len(suppressed), worker_count - 1)

        # Check database records
        outbox_count = self.db.execute(
            "SELECT COUNT(*) AS total FROM EMAIL_OUTBOX WHERE recipient_email = ?",
            (recipient,),
        ).fetchone()["total"]
        self.assertEqual(outbox_count, 1)

    def test_force_send_override_bypasses_cooldown(self):
        """Admin force_send=True flag overrides deduplication block."""
        recipient = "tts_admin@example.com"
        subject = "Khẩn cấp: Yêu cầu bổ sung thông tin"
        body = "Vui lòng cập nhật CCCD ngay."

        id1 = enqueue_email(
            db=self.db,
            recipient_email=recipient,
            subject=subject,
            body_text=body,
        )
        self.db.commit()
        self.assertIsNotNone(id1)

        # Without force_send -> rejected
        with self.assertRaises(DuplicateEmailSuppressedError):
            enqueue_email(
                db=self.db,
                recipient_email=recipient,
                subject=subject,
                body_text=body,
                force_send=False,
            )

        # With force_send=True -> allowed!
        id2 = enqueue_email(
            db=self.db,
            recipient_email=recipient,
            subject=subject,
            body_text=body,
            force_send=True,
        )
        self.db.commit()
        self.assertIsNotNone(id2)
        self.assertNotEqual(id1, id2)

    def test_worker_suppresses_duplicate_outbox_item_without_smtp(self):
        """Worker protection: An outbox item duplicate of an already sent email is suppressed without calling SMTP."""
        from app import email_outbox
        from unittest.mock import MagicMock

        recipient = "worker_test@example.com"
        subject = "Thông báo tiến độ"
        body = "Vui lòng cập nhật trạng thái nhiệm vụ."
        dedup_hash = compute_email_dedup_hash(recipient, subject, body)

        # 1. First email is already SENT
        self.db.execute(
            """INSERT INTO EMAIL_OUTBOX
               (recipient_email, subject, body, template_type, deduplication_key,
                dedup_hash, status, sent_at)
               VALUES (?, ?, ?, 'test', 'k1', ?, 'SENT', CURRENT_TIMESTAMP)""",
            (recipient, subject, body, dedup_hash),
        )

        # 2. Second email is PENDING (e.g. queued by accident or duplicate event)
        self.db.execute(
            """INSERT INTO EMAIL_OUTBOX
               (recipient_email, subject, body, template_type, deduplication_key,
                dedup_hash, status)
               VALUES (?, ?, ?, 'test', 'k2', ?, 'PENDING')""",
            (recipient, subject, body, dedup_hash),
        )
        self.db.commit()

        mock_smtp = MagicMock()
        with patch.dict(os.environ, {"SMTP_HOST": "smtp.test", "SMTP_FROM": "bot@test.org"}), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            claimed = email_outbox.process_one_email()
            self.assertTrue(claimed)

            # SMTP send_message must NOT have been called!
            mock_smtp.send_message.assert_not_called()

        # Check that the duplicate outbox item was marked FAILED with DUPLICATE_EMAIL_SUPPRESSED
        second_item = self.db.execute(
            "SELECT status, last_error FROM EMAIL_OUTBOX WHERE deduplication_key = 'k2'"
        ).fetchone()
        self.assertEqual(second_item["status"], "FAILED")
        self.assertIn("DUPLICATE_EMAIL_SUPPRESSED", second_item["last_error"])


if __name__ == "__main__":
    unittest.main()
