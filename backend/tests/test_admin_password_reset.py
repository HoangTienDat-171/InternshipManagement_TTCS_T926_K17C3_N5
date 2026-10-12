"""Focused security and workflow tests for administrator password resets."""
import asyncio
import os
import re
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import BackgroundTasks, HTTPException

from app import database
from app import email_service
from app.main import app
from app.routes import auth_routes
from app.schemas import PasswordChange, UserLogin
from app.security import get_session_user, token_digest


class AdminPasswordResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-admin-password-reset-", ignore_cleanup_errors=True)
        cls.db_path = Path(cls.temp_dir.name) / "admin_password_reset.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(auth_routes.get_db, None)
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()
        self.admin_id = 94001
        self.target_id = 94002
        self.old_password = "TargetOldPassword123"
        self.old_token = "old-target-session-token"
        self.old_hash = database.hash_password(self.old_password)

        self.db.execute("DELETE FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung IN (?, ?)", (self.admin_id, self.target_id))
        self.db.execute("DELETE FROM ADMIN_PASSWORD_RESET_AUDIT WHERE actor_user_id IN (?, ?) OR target_user_id IN (?, ?)",
                        (self.admin_id, self.target_id, self.admin_id, self.target_id))
        self.db.execute("DELETE FROM THONG_BAO WHERE ma_nguoi_dung IN (?, ?)", (self.admin_id, self.target_id))
        self.db.execute("DELETE FROM FAILED_LOGIN_ATTEMPTS WHERE email IN (?, ?)",
                        ("reset.admin@example.test", "reset.target@example.test"))
        self.db.execute("DELETE FROM NGUOI_DUNG WHERE ma_nguoi_dung IN (?, ?)", (self.admin_id, self.target_id))
        self.db.execute(
            """INSERT INTO NGUOI_DUNG
               (ma_nguoi_dung, ho_ten, email, mat_khau, vai_tro, trang_thai, must_change_password)
               VALUES (?, 'Reset Admin', 'reset.admin@example.test', ?, 'Admin', 'HoatDong', 0)""",
            (self.admin_id, database.hash_password("AdminPassword123")),
        )
        self.db.execute(
            """INSERT INTO NGUOI_DUNG
               (ma_nguoi_dung, ho_ten, email, mat_khau, vai_tro, trang_thai, must_change_password)
               VALUES (?, 'Reset Target', 'reset.target@example.test', ?, 'ThucTapSinh', 'HoatDong', 0)""",
            (self.target_id, self.old_hash),
        )
        self.db.execute(
            """INSERT INTO ACTIVE_SESSIONS (ma_nguoi_dung, token_hash, session_id)
               VALUES (?, ?, 'old-target-session-id')""",
            (self.target_id, token_digest(self.old_token)),
        )
        self.db.commit()
        self.admin = {"ma_nguoi_dung": self.admin_id, "vai_tro": "Admin"}

    def tearDown(self):
        self.db.close()

    @staticmethod
    def request_for(user):
        return SimpleNamespace(
            state=SimpleNamespace(current_user=user),
            client=SimpleNamespace(host="127.0.0.1"),
        )

    def reset_target(self, send_mock):
        response = auth_routes.reset_temporary_password(
            self.target_id,
            self.request_for(self.admin),
            BackgroundTasks(),
            self.db,
        )
        email_body = send_mock.call_args.kwargs["body_text"]
        match = re.search(r"(?m)^Mật khẩu tạm thời:\s*(\S+)$", email_body)
        self.assertIsNotNone(match)
        return response, email_body, match.group(1)

    def test_admin_reset_sends_temporary_secret_without_storing_it_and_revokes_old_session(self):
        with patch.object(auth_routes, "send_email_direct", return_value=True) as send_email:
            response, body, temporary_password = self.reset_target(send_email)

        self.assertEqual(send_email.call_args.kwargs["recipient"], "reset.target@example.test")
        self.assertEqual(send_email.call_args.kwargs["subject"], "IMS Portal — Mật khẩu tạm thời cho tài khoản của bạn")
        self.assertEqual(len(temporary_password), 16)
        self.assertNotIn(temporary_password, str(response))
        self.assertEqual(response["expires_in_minutes"], 30)

        row = self.db.execute(
            """SELECT mat_khau, must_change_password, temporary_password_expires_at,
                      temporary_password_consumed_at, trang_thai
               FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?""",
            (self.target_id,),
        ).fetchone()
        self.assertNotEqual(row["mat_khau"], self.old_hash)
        self.assertTrue(database.verify_password(temporary_password, row["mat_khau"]))
        self.assertFalse(database.verify_password(self.old_password, row["mat_khau"]))
        self.assertEqual((row["must_change_password"], row["trang_thai"]), (1, "HoatDong"))
        expiry = datetime.fromisoformat(row["temporary_password_expires_at"])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.assertGreater(expiry, now)
        self.assertLessEqual(expiry - now, timedelta(minutes=31))
        self.assertIsNone(row["temporary_password_consumed_at"])
        self.assertIsNone(self.db.execute("SELECT 1 FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung = ?", (self.target_id,)).fetchone())
        self.assertIsNone(get_session_user(self.old_token))

        audit = self.db.execute(
            "SELECT actor_user_id, target_user_id, outcome FROM ADMIN_PASSWORD_RESET_AUDIT ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(tuple(audit), (self.admin_id, self.target_id, "SMTP_ACCEPTED"))
        outbox_text = " ".join(str(value) for row in self.db.execute("SELECT subject, body FROM EMAIL_OUTBOX").fetchall() for value in row)
        self.assertNotIn(temporary_password, outbox_text)
        security_log_text = " ".join(
            str(value)
            for row in self.db.execute("SELECT email, ip_address, thong_tin FROM NHAT_KY_DANG_NHAP").fetchall()
            for value in row
        )
        self.assertNotIn(temporary_password, security_log_text)
        self.assertIn("30 phút", body)

    def test_non_admin_self_target_and_missing_target_are_rejected(self):
        with patch.object(auth_routes, "send_email_direct", return_value=True) as send_email:
            for role in ("HR", "Mentor", "ThucTapSinh"):
                with self.subTest(role=role), self.assertRaises(HTTPException) as ctx:
                    auth_routes.reset_temporary_password(
                        self.target_id,
                        self.request_for({"ma_nguoi_dung": 500, "vai_tro": role}),
                        BackgroundTasks(),
                        self.db,
                    )
                self.assertEqual(ctx.exception.status_code, 403)

            with self.assertRaises(HTTPException) as missing:
                auth_routes.reset_temporary_password(999999, self.request_for(self.admin), BackgroundTasks(), self.db)
            self.assertEqual(missing.exception.status_code, 404)

            with self.assertRaises(HTTPException) as self_reset:
                auth_routes.reset_temporary_password(self.admin_id, self.request_for(self.admin), BackgroundTasks(), self.db)
            self.assertEqual(self_reset.exception.status_code, 400)

        send_email.assert_not_called()
        admin_row = self.db.execute("SELECT mat_khau, trang_thai FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?", (self.admin_id,)).fetchone()
        self.assertTrue(database.verify_password("AdminPassword123", admin_row["mat_khau"]))
        self.assertEqual(admin_row["trang_thai"], "HoatDong")

    def test_invalid_email_and_locked_account_are_not_activated(self):
        self.db.execute("UPDATE NGUOI_DUNG SET email='not-an-email' WHERE ma_nguoi_dung = ?", (self.target_id,))
        self.db.commit()
        with patch.object(auth_routes, "send_email_direct") as send_email:
            with self.assertRaises(HTTPException) as invalid_email:
                auth_routes.reset_temporary_password(self.target_id, self.request_for(self.admin), BackgroundTasks(), self.db)
            self.assertEqual(invalid_email.exception.status_code, 409)

            self.db.execute("UPDATE NGUOI_DUNG SET email='reset.target@example.test', trang_thai='Khoa' WHERE ma_nguoi_dung = ?", (self.target_id,))
            self.db.commit()
            with self.assertRaises(HTTPException) as locked:
                auth_routes.reset_temporary_password(self.target_id, self.request_for(self.admin), BackgroundTasks(), self.db)
            self.assertEqual(locked.exception.status_code, 409)

        send_email.assert_not_called()
        row = self.db.execute("SELECT trang_thai, must_change_password, mat_khau FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?", (self.target_id,)).fetchone()
        self.assertEqual((row["trang_thai"], row["must_change_password"], row["mat_khau"]), ("Khoa", 0, self.old_hash))

    def test_smtp_failure_preserves_password_and_session_and_audits_only_failure(self):
        failure = RuntimeError("test SMTP unavailable")
        with patch.object(auth_routes, "send_email_direct", side_effect=failure) as send_email:
            with self.assertRaises(HTTPException) as ctx:
                auth_routes.reset_temporary_password(self.target_id, self.request_for(self.admin), BackgroundTasks(), self.db)
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertNotIn("password", str(ctx.exception.detail).lower())
        send_email.assert_called_once()

        row = self.db.execute(
            """SELECT mat_khau, must_change_password, temporary_password_expires_at,
                      temporary_password_consumed_at, trang_thai
               FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?""",
            (self.target_id,),
        ).fetchone()
        self.assertEqual((row["mat_khau"], row["must_change_password"], row["trang_thai"]), (self.old_hash, 0, "HoatDong"))
        self.assertIsNone(row["temporary_password_expires_at"])
        self.assertIsNone(row["temporary_password_consumed_at"])
        self.assertIsNotNone(self.db.execute("SELECT 1 FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung = ?", (self.target_id,)).fetchone())
        audit = self.db.execute("SELECT outcome FROM ADMIN_PASSWORD_RESET_AUDIT ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(audit["outcome"], "SMTP_FAILED")
        with patch.object(auth_routes, "send_email_direct", return_value=True) as retry_email:
            with self.assertRaises(HTTPException) as rate_limited:
                auth_routes.reset_temporary_password(self.target_id, self.request_for(self.admin), BackgroundTasks(), self.db)
        self.assertEqual(rate_limited.exception.status_code, 429)
        retry_email.assert_not_called()

    def test_cooldown_blocks_duplicate_send(self):
        with patch.object(auth_routes, "send_email_direct", return_value=True) as send_email:
            self.reset_target(send_email)
            with self.assertRaises(HTTPException) as ctx:
                auth_routes.reset_temporary_password(self.target_id, self.request_for(self.admin), BackgroundTasks(), self.db)
        self.assertEqual(ctx.exception.status_code, 429)
        send_email.assert_called_once()

    def test_temp_password_is_single_use_forced_to_change_and_invalid_after_change(self):
        with patch.object(auth_routes, "send_email_direct", return_value=True) as send_email:
            _, _, temporary_password = self.reset_target(send_email)

        login_request = self.request_for({})
        login_request.client.host = "127.0.0.1"
        login_result = auth_routes.login(
            UserLogin(email="reset.target@example.test", mat_khau=temporary_password),
            login_request,
            BackgroundTasks(),
            self.db,
        )
        self.assertTrue(login_result["user"]["must_change_password"])
        user_after_login = self.db.execute(
            "SELECT temporary_password_consumed_at FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?", (self.target_id,)
        ).fetchone()
        self.assertIsNotNone(user_after_login["temporary_password_consumed_at"])

        with self.assertRaises(HTTPException) as second_use:
            auth_routes.login(
                UserLogin(email="reset.target@example.test", mat_khau=temporary_password),
                login_request,
                BackgroundTasks(),
                self.db,
            )
        self.assertEqual(second_use.exception.status_code, 401)

        session_user = get_session_user(login_result["token"])
        change_request = self.request_for(session_user)
        with self.assertRaises(HTTPException) as same_password:
            auth_routes.change_password(
                self.target_id,
                PasswordChange(mat_khau_hien_tai=temporary_password, mat_khau_moi=temporary_password),
                change_request,
                self.db,
            )
        self.assertEqual(same_password.exception.status_code, 400)

        new_password = "ChangedPassword456"
        changed = auth_routes.change_password(
            self.target_id,
            PasswordChange(mat_khau_hien_tai=temporary_password, mat_khau_moi=new_password),
            change_request,
            self.db,
        )
        self.assertFalse(changed["must_change_password"])
        row = self.db.execute(
            """SELECT mat_khau, must_change_password, temporary_password_expires_at,
                      temporary_password_consumed_at FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?""",
            (self.target_id,),
        ).fetchone()
        self.assertTrue(database.verify_password(new_password, row["mat_khau"]))
        self.assertEqual(row["must_change_password"], 0)
        self.assertIsNone(row["temporary_password_expires_at"])
        self.assertIsNone(row["temporary_password_consumed_at"])
        with self.assertRaises(HTTPException) as old_temp:
            auth_routes.login(
                UserLogin(email="reset.target@example.test", mat_khau=temporary_password),
                login_request,
                BackgroundTasks(),
                self.db,
            )
        self.assertEqual(old_temp.exception.status_code, 401)

    def test_expired_temporary_password_is_rejected_at_login(self):
        with patch.object(auth_routes, "send_email_direct", return_value=True) as send_email:
            _, _, temporary_password = self.reset_target(send_email)
        expired_at = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)).isoformat(sep=" ")
        self.db.execute(
            "UPDATE NGUOI_DUNG SET temporary_password_expires_at = ? WHERE ma_nguoi_dung = ?",
            (expired_at, self.target_id),
        )
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            auth_routes.login(
                UserLogin(email="reset.target@example.test", mat_khau=temporary_password),
                self.request_for({}),
                BackgroundTasks(),
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIsNone(self.db.execute("SELECT 1 FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung = ?", (self.target_id,)).fetchone())
        target = self.db.execute("SELECT trang_thai, must_change_password FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?", (self.target_id,)).fetchone()
        self.assertEqual((target["trang_thai"], target["must_change_password"]), ("HoatDong", 1))

    def test_password_change_required_blocks_direct_business_api_until_password_is_changed(self):
        with patch.object(auth_routes, "send_email_direct", return_value=True) as send_email:
            _, _, temporary_password = self.reset_target(send_email)
        login = auth_routes.login(
            UserLogin(email="reset.target@example.test", mat_khau=temporary_password),
            self.request_for({}),
            BackgroundTasks(),
            self.db,
        )
        token = login["token"]

        def override_db():
            conn = database.get_db_connection()
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[auth_routes.get_db] = override_db

        async def request_api():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                headers = {"Authorization": f"Bearer {token}"}
                blocked = await client.get("/api/auth/users", headers=headers)
                wrong_password_path = await client.put(
                    f"/api/auth/users/{self.admin_id}/password",
                    headers=headers,
                    json={"mat_khau_hien_tai": temporary_password, "mat_khau_moi": "NewPassword789"},
                )
                allowed_me = await client.get("/api/auth/me", headers=headers)
                changed = await client.put(
                    f"/api/auth/users/{self.target_id}/password",
                    headers=headers,
                    json={"mat_khau_hien_tai": temporary_password, "mat_khau_moi": "NewPassword789"},
                )
                after_change = await client.get("/api/auth/users", headers=headers)
                return blocked, wrong_password_path, allowed_me, changed, after_change

        try:
            blocked, wrong_password_path, allowed_me, changed, after_change = asyncio.run(request_api())
        finally:
            app.dependency_overrides.pop(auth_routes.get_db, None)

        self.assertEqual((blocked.status_code, blocked.json().get("code")), (403, "PASSWORD_CHANGE_REQUIRED"))
        self.assertEqual((wrong_password_path.status_code, wrong_password_path.json().get("code")), (403, "PASSWORD_CHANGE_REQUIRED"))
        self.assertEqual(allowed_me.status_code, 200)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(after_change.status_code, 403)
        self.assertNotEqual(after_change.json().get("code"), "PASSWORD_CHANGE_REQUIRED")

    def test_smtp_recipient_rejection_is_not_reported_as_accepted(self):
        class RefusingSMTP:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def send_message(self, message):
                return {"reset.target@example.test": (550, b"mailbox unavailable")}

        smtp_config = {
            "SMTP_HOST": "smtp.test.invalid",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "",
            "SMTP_PASSWORD": "",
            "SMTP_FROM": "mailer@test.invalid",
            "SMTP_USE_SSL": "false",
            "SMTP_USE_STARTTLS": "false",
            "SMTP_TIMEOUT_SECONDS": "1",
        }
        with patch.dict(os.environ, smtp_config), patch.object(email_service.smtplib, "SMTP", RefusingSMTP):
            with self.assertRaises(email_service.smtplib.SMTPRecipientsRefused):
                email_service.send_email_direct(
                    "reset.target@example.test",
                    "Test reset",
                    "temporary password should remain in memory only",
                )


if __name__ == "__main__":
    unittest.main()
