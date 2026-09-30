"""Isolated tests for the US08 transactional outbox and SMTP worker."""
import os
import smtplib
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database
from app import email_outbox
from app.notifications import create_notification


class FakeSMTP:
    created = []

    def __init__(self, *args, **kwargs):
        self.messages = []
        self.created.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def starttls(self, **kwargs):
        pass

    def login(self, username, password):
        pass

    def send_message(self, message):
        self.messages.append(message)


class US08OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us08-", ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "outbox.sqlite3"
        self.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        self.path_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.backend_patch.start()
        self.path_patch.start()
        self.env_patch = patch.dict(os.environ, {
            "SMTP_HOST": "smtp.test.invalid", "SMTP_PORT": "587",
            "SMTP_USERNAME": "mailer", "SMTP_PASSWORD": "test-secret",
            "SMTP_FROM": "internships@test.invalid", "SMTP_USE_SSL": "false",
            "SMTP_USE_STARTTLS": "false", "SMTP_TIMEOUT_SECONDS": "1",
        })
        self.env_patch.start()
        with sqlite3.connect(self.db_path) as db:
            db.execute("""CREATE TABLE EMAIL_OUTBOX (
                id INTEGER PRIMARY KEY AUTOINCREMENT, recipient_email TEXT NOT NULL,
                subject TEXT NOT NULL, body TEXT NOT NULL, template_type TEXT NOT NULL,
                reference_type TEXT, reference_id TEXT, deduplication_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'PENDING', retry_count INTEGER NOT NULL DEFAULT 0,
                max_retry INTEGER NOT NULL DEFAULT 5, last_error TEXT, next_retry_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, sent_at DATETIME,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("""CREATE TABLE THONG_BAO (
                ma_thong_bao INTEGER PRIMARY KEY AUTOINCREMENT, ma_nguoi_dung INTEGER,
                tieu_de TEXT, noi_dung TEXT, kenh TEXT, loai TEXT, reference_type TEXT,
                reference_id TEXT, da_doc INTEGER DEFAULT 0, thoi_gian_gui DATETIME DEFAULT CURRENT_TIMESTAMP,
                thoi_gian_doc DATETIME)""")

    def tearDown(self):
        self.env_patch.stop()
        self.path_patch.stop()
        self.backend_patch.stop()
        self.temp_dir.cleanup()

    def enqueue(self, key="event-1", retry_count=0, max_retry=5):
        with sqlite3.connect(self.db_path) as db:
            db.execute("""INSERT INTO EMAIL_OUTBOX
                (recipient_email, subject, body, template_type, deduplication_key,
                 retry_count, max_retry) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("student@test.invalid", "Review result", "Approved", "approval_result", key,
                 retry_count, max_retry))

    def outbox_row(self):
        with sqlite3.connect(self.db_path) as db:
            return db.execute("SELECT status, retry_count, last_error, sent_at FROM EMAIL_OUTBOX").fetchone()

    def test_smtp_success_marks_sent(self):
        self.enqueue()
        with patch.object(email_outbox.smtplib, "SMTP", FakeSMTP):
            self.assertTrue(email_outbox.process_one_email())
        status, attempts, error, sent_at = self.outbox_row()
        self.assertEqual((status, attempts, error), ("SENT", 0, None))
        self.assertIsNotNone(sent_at)

    def test_temporary_smtp_disconnect_schedules_retry(self):
        self.enqueue()
        with patch.object(email_outbox.smtplib, "SMTP", side_effect=OSError("connection lost")):
            self.assertTrue(email_outbox.process_one_email())
        status, attempts, error, _ = self.outbox_row()
        self.assertEqual((status, attempts), ("RETRY", 1))
        self.assertIn("connection lost", error)

    def test_retry_limit_marks_failed_and_redacts_password(self):
        self.enqueue(retry_count=4, max_retry=5)
        failure = smtplib.SMTPAuthenticationError(535, b"denied test-secret")
        with patch.object(email_outbox.smtplib, "SMTP", side_effect=failure):
            self.assertTrue(email_outbox.process_one_email())
        status, attempts, error, _ = self.outbox_row()
        self.assertEqual((status, attempts), ("FAILED", 5))
        self.assertNotIn("test-secret", error)

    def test_worker_does_not_send_sent_item_again(self):
        self.enqueue()
        FakeSMTP.created.clear()
        with patch.object(email_outbox.smtplib, "SMTP", FakeSMTP):
            self.assertTrue(email_outbox.process_one_email())
            self.assertFalse(email_outbox.process_one_email())
        self.assertEqual(len(FakeSMTP.created), 1)

    def test_stale_processing_claim_is_retried(self):
        self.enqueue()
        db = sqlite3.connect(self.db_path)
        try:
            db.execute("UPDATE EMAIL_OUTBOX SET status='PROCESSING', updated_at='2000-01-01 00:00:00'")
            db.commit()
        finally:
            db.close()
        with patch.object(email_outbox.smtplib, "SMTP", FakeSMTP):
            self.assertTrue(email_outbox.process_one_email())
        status, attempts, error, _ = self.outbox_row()
        self.assertEqual((status, attempts, error), ("SENT", 1, None))

    def test_duplicate_event_key_creates_only_one_email(self):
        db = database.get_db_connection()
        try:
            create_notification(db, 7, "Approved", "Your application was approved",
                                email_recipient="student@test.invalid",
                                email_deduplication_key="us08:application:7:approved")
            create_notification(db, 7, "Approved", "Your application was approved",
                                email_recipient="student@test.invalid",
                                email_deduplication_key="us08:application:7:approved")
            db.commit()
        finally:
            db.close()
        with sqlite3.connect(self.db_path) as db:
            notifications = db.execute("SELECT COUNT(*) FROM THONG_BAO").fetchone()[0]
            emails = db.execute("SELECT COUNT(*) FROM EMAIL_OUTBOX").fetchone()[0]
        self.assertEqual((notifications, emails), (2, 1))

    def test_notification_and_outbox_roll_back_together(self):
        db = database.get_db_connection()
        try:
            create_notification(db, 7, "Approved", "Your application was approved",
                                email_recipient="student@test.invalid",
                                email_deduplication_key="us08:application:7:approved")
            db.rollback()
        finally:
            db.close()
        with sqlite3.connect(self.db_path) as db:
            notifications = db.execute("SELECT COUNT(*) FROM THONG_BAO").fetchone()[0]
            emails = db.execute("SELECT COUNT(*) FROM EMAIL_OUTBOX").fetchone()[0]
        self.assertEqual((notifications, emails), (0, 0))

    def test_only_one_worker_claims_an_email(self):
        self.enqueue()
        sending = threading.Event()
        release = threading.Event()
        second_result = []

        class BlockingSMTP(FakeSMTP):
            def send_message(self, message):
                sending.set()
                release.wait()

        with patch.object(email_outbox.smtplib, "SMTP", BlockingSMTP):
            first = threading.Thread(target=email_outbox.process_one_email)
            first.start()
            self.assertTrue(sending.wait(1))
            self.assertEqual(self.outbox_row()[0], "PROCESSING")
            second = threading.Thread(target=lambda: second_result.append(email_outbox.process_one_email()))
            second.start()
            second.join(1)
            release.set()
            first.join(2)
            second.join(2)
        self.assertEqual(second_result, [False])
        self.assertEqual(self.outbox_row()[0], "SENT")


if __name__ == "__main__":
    unittest.main()
