"""Unit tests for the one-click launcher and safe shutdown system."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.launcher import (
    Launcher,
    parse_env_file,
    sanitize_text,
    get_port_listener_pid,
    is_tcp_open,
)


class LauncherUnitTests(unittest.TestCase):
    def test_sanitize_text_masks_passwords_and_tokens(self):
        sample = "MYSQL_PASSWORD=superSecret123 SMTP_PASSWORD=my_email_pass token=abc123xyz"
        masked = sanitize_text(sample)
        self.assertNotIn("superSecret123", masked)
        self.assertNotIn("my_email_pass", masked)
        self.assertNotIn("abc123xyz", masked)
        self.assertIn("******", masked)

    def test_parse_env_file(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
            f.write("# Sample env\nKEY1=value1\nKEY2='quoted_value'\nKEY3=\"double_quoted\"\n\n")
            f_path = Path(f.name)
        try:
            parsed = parse_env_file(f_path)
            self.assertEqual(parsed.get("KEY1"), "value1")
            self.assertEqual(parsed.get("KEY2"), "quoted_value")
            self.assertEqual(parsed.get("KEY3"), "double_quoted")
        finally:
            f_path.unlink(missing_ok=True)

    def test_missing_env_file_fails_cleanly(self):
        launcher = Launcher()
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_env = Path(tmp_dir) / "nonexistent.env"
            with patch("scripts.launcher.ENV_FILE", fake_env):
                ok, msg = launcher.check_environment()
                self.assertFalse(ok)
                self.assertIn("Thiếu file cấu hình backend\\.env", msg)

    def test_sqlite_backend_initialization(self):
        launcher = Launcher()
        launcher.env = {
            "IMS_DATABASE_BACKEND": "sqlite",
            "IMS_SQLITE_PATH": str(Path(__file__).resolve().parent.parent / "app" / "internship.db")
        }
        ok, badge, detail = launcher.check_and_start_mysql()
        self.assertTrue(ok)
        self.assertEqual(badge, "CONNECTED (SQLite)")

    def test_unconfigured_smtp_handled_safely(self):
        launcher = Launcher()
        launcher.env = {
            "SMTP_HOST": "",
            "SMTP_USERNAME": ""
        }
        ok, smtp_badge, worker_badge = launcher.check_smtp_and_worker()
        self.assertTrue(ok)
        self.assertEqual(smtp_badge, "NOT CONFIGURED")
        self.assertIn("Idle", worker_badge)


if __name__ == "__main__":
    unittest.main()
