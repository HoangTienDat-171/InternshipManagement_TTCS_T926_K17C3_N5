"""Tests for forgot password and temporary password generation."""
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app import database
from app.account_credentials import create_temporary_password
from app.database import hash_password, verify_password
from app.routes.auth_routes import forgot_password
from app.schemas import ForgotPasswordRequest


class ForgotPasswordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-forgot-pw-", ignore_cleanup_errors=True)
        cls.db_path = Path(cls.temp_dir.name) / "forgot_pw.sqlite3"
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
        self.db.execute("DELETE FROM EMAIL_OUTBOX")
        self.db.execute("DELETE FROM THONG_BAO")
        self.db.execute("DELETE FROM ACTIVE_SESSIONS")
        self.db.execute("DELETE FROM FAILED_LOGIN_ATTEMPTS")
        self.request = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_create_temporary_password_length_and_structure(self):
        """Mật khẩu tạm thời luôn có độ dài 8 ký tự và chứa đủ chữ hoa, thường, số."""
        for _ in range(50):
            pw = create_temporary_password()
            self.assertEqual(len(pw), 8)
            self.assertTrue(any(c.isdigit() for c in pw), f"Must contain digit: {pw}")
            self.assertTrue(any(c.islower() for c in pw), f"Must contain lowercase: {pw}")
            self.assertTrue(any(c.isupper() for c in pw), f"Must contain uppercase: {pw}")
            # Ensure no ambiguous characters
            for bad_char in ("0", "O", "1", "l", "I"):
                self.assertNotIn(bad_char, pw, f"Should not contain ambiguous char '{bad_char}': {pw}")

    def test_forgot_password_invalid_and_unknown_email(self):
        with self.assertRaises(HTTPException) as ctx:
            forgot_password(ForgotPasswordRequest(email="invalid_email_str"), self.request, self.db)
        self.assertEqual(ctx.exception.status_code, 400)

        result = forgot_password(ForgotPasswordRequest(email="nonexistent@internship.vn"), self.request, self.db)
        self.assertTrue(result["message"])
        self.assertNotIn("email", result)

    def test_forgot_password_locked_and_pending_accounts(self):
        self.db.execute("""
            INSERT OR REPLACE INTO NGUOI_DUNG
                (ma_nguoi_dung, ho_ten, email, mat_khau, vai_tro, trang_thai, must_change_password)
            VALUES
                (991, 'Pending Intern', 'pending.intern@example.test', 'hash', 'ThucTapSinh', 'ChoDuyet', 0),
                (992, 'Locked Intern', 'locked.intern@example.test', 'hash', 'ThucTapSinh', 'Khoa', 0)
        """)
        self.db.commit()

        results = [
            forgot_password(ForgotPasswordRequest(email=email), self.request, self.db)
            for email in ("pending.intern@example.test", "locked.intern@example.test")
        ]
        self.assertEqual(results[0], results[1])
        self.assertNotIn("email", results[0])
        accounts = self.db.execute("""
            SELECT trang_thai, must_change_password FROM NGUOI_DUNG
            WHERE ma_nguoi_dung IN (991, 992) ORDER BY ma_nguoi_dung
        """).fetchall()
        self.assertEqual([(row["trang_thai"], row["must_change_password"]) for row in accounts], [("ChoDuyet", 0), ("Khoa", 0)])

    def test_forgot_password_success_workflow(self):
        initial_hash = hash_password("OldPassword123")
        self.db.execute("""
            INSERT OR REPLACE INTO NGUOI_DUNG
                (ma_nguoi_dung, ho_ten, email, mat_khau, vai_tro, trang_thai, must_change_password)
            VALUES
                (993, 'Active Intern', 'active.intern@example.test', ?, 'ThucTapSinh', 'HoatDong', 0)
        """, (initial_hash,))
        # Also create a session and failed login attempt
        self.db.execute("""
            INSERT OR REPLACE INTO ACTIVE_SESSIONS (ma_nguoi_dung, session_id, token_hash)
            VALUES (993, 'active-session-id', 'some-hash')
        """)
        self.db.execute("""
            INSERT OR REPLACE INTO FAILED_LOGIN_ATTEMPTS (email, failed_count)
            VALUES ('active.intern@example.test', 3)
        """)
        self.db.commit()

        # Call forgot password; the public response does not reveal account details.
        result = forgot_password(ForgotPasswordRequest(email="active.intern@example.test"), self.request, self.db)
        self.assertTrue(result["message"])
        self.assertNotIn("email", result)

        # Verify user state in DB
        user_row = self.db.execute(
            "SELECT mat_khau, must_change_password FROM NGUOI_DUNG WHERE ma_nguoi_dung=993"
        ).fetchone()
        self.assertEqual(user_row["must_change_password"], 1)
        self.assertNotEqual(user_row["mat_khau"], initial_hash)

        # Active session & failed login attempts should be wiped
        active_sess = self.db.execute("SELECT * FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung=993").fetchone()
        self.assertIsNone(active_sess)
        failed_attempts = self.db.execute("SELECT * FROM FAILED_LOGIN_ATTEMPTS WHERE email='active.intern@example.test'").fetchone()
        self.assertIsNone(failed_attempts)

        # Check EMAIL_OUTBOX
        email_row = self.db.execute(
            "SELECT subject, body, recipient_email FROM EMAIL_OUTBOX WHERE recipient_email='active.intern@example.test'"
        ).fetchone()
        self.assertIsNotNone(email_row)
        self.assertIn("[IMS Portal]", email_row["subject"])

        match = re.search(r"Mật khẩu tạm thời:\s*([^\s]+)", email_row["body"])
        self.assertIsNotNone(match)
        temp_pw = match.group(1).strip()
        self.assertEqual(len(temp_pw), 8)

        # Temporary password must correctly verify against the stored hash
        self.assertTrue(verify_password(temp_pw, user_row["mat_khau"]))


if __name__ == "__main__":
    unittest.main()
