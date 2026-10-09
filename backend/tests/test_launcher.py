"""
Unit tests for the one-click launcher and safe shutdown system.
Covers process ownership verification, PID reuse safety, stale state handling,
port collision protection, .env prechecks, SQLite/MySQL connectivity, and safe shutdown.
"""
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unittest.mock import MagicMock, patch

from scripts.launcher import (
    Launcher,
    clear_state,
    find_matching_mysql_service,
    get_process_creation_time,
    is_pid_alive,
    is_tcp_open,
    kill_process_tree,
    load_state,
    parse_env_file,
    sanitize_text,
    save_state,
    verify_process_ownership,
)


class LauncherUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="ims-launcher-test-")
        self.logs_dir = Path(self.tmp_dir.name) / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.logs_dir / "launcher_state.json"

        self.patch_logs = patch("scripts.launcher.LOGS_DIR", self.logs_dir)
        self.patch_state = patch("scripts.launcher.STATE_FILE", self.state_file)
        self.patch_logs.start()
        self.patch_state.start()

    def tearDown(self):
        self.patch_logs.stop()
        self.patch_state.stop()
        self.tmp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Basic utility tests
    # -------------------------------------------------------------------------

    def test_sanitize_text_masks_passwords_and_tokens(self):
        sample = "MYSQL_PASSWORD=superSecret123 SMTP_PASSWORD=my_email_pass token=abc123xyz"
        masked = sanitize_text(sample)
        self.assertNotIn("superSecret123", masked)
        self.assertNotIn("my_email_pass", masked)
        self.assertNotIn("abc123xyz", masked)
        self.assertIn("******", masked)

    def test_parse_env_file(self):
        env_file = Path(self.tmp_dir.name) / ".env"
        env_file.write_text("KEY1=value1\nKEY2='quoted_value'\nKEY3=\"double_quoted\"\n# Comment\n", encoding="utf-8")
        parsed = parse_env_file(env_file)
        self.assertEqual(parsed.get("KEY1"), "value1")
        self.assertEqual(parsed.get("KEY2"), "quoted_value")
        self.assertEqual(parsed.get("KEY3"), "double_quoted")

    # -------------------------------------------------------------------------
    # 2. Process Ownership Verification Tests
    # -------------------------------------------------------------------------

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.get_process_creation_time", return_value=133000000000000000.0)
    @patch("scripts.launcher.get_process_cmdline")
    @patch("scripts.launcher.get_process_name", return_value="python.exe")
    def test_ownership_valid_backend(self, mock_name, mock_cmdline, mock_ctime, mock_alive):
        """Backend sở hữu hợp lệ: tiến trình đang sống, creation_time khớp, cmdline thuộc dự án và uvicorn"""
        from scripts.launcher import ROOT_DIR
        mock_cmdline.return_value = f'python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 cwd={ROOT_DIR}'

        saved_info = {"pid": 5000, "creation_time": 133000000000000000.0}
        ok, reason = verify_process_ownership(5000, "backend", saved_info)
        self.assertTrue(ok)
        self.assertIn("Xác minh thành công", reason)

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.get_process_creation_time", return_value=133000000000000000.0)
    @patch("scripts.launcher.get_process_cmdline")
    @patch("scripts.launcher.get_process_name", return_value="node.exe")
    def test_ownership_valid_frontend(self, mock_name, mock_cmdline, mock_ctime, mock_alive):
        """Frontend sở hữu hợp lệ: node.exe chạy vite trong thư mục frontend của dự án"""
        from scripts.launcher import FRONTEND_DIR
        mock_cmdline.return_value = f'node.exe {FRONTEND_DIR}\\node_modules\\vite\\bin\\vite.js --port 3000'

        saved_info = {"pid": 6000, "creation_time": 133000000000000000.0}
        ok, reason = verify_process_ownership(6000, "frontend", saved_info)
        self.assertTrue(ok)
        self.assertIn("Xác minh thành công", reason)

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.get_process_creation_time", return_value=133000000000000000.0)
    @patch("scripts.launcher.get_process_cmdline")
    @patch("scripts.launcher.get_process_name", return_value="python.exe")
    def test_ownership_invalid_foreign_backend_rejected(self, mock_name, mock_cmdline, mock_ctime, mock_alive):
        """Tiến trình uvicorn của dự án khác không được nhận quyền sở hữu và không được kill"""
        mock_cmdline.return_value = 'python.exe -m uvicorn other_project.main:app --host 127.0.0.1 --port 8000 C:\\OtherApp'

        saved_info = {"pid": 7000, "creation_time": 133000000000000000.0}
        ok, reason = verify_process_ownership(7000, "backend", saved_info)
        self.assertFalse(ok)
        self.assertIn("không thuộc backend của dự án này", reason)

        # Kiểm tra kill_process_tree từ chối dừng
        with patch("subprocess.run") as mock_run:
            killed, k_reason = kill_process_tree(7000, "backend", saved_info)
            self.assertFalse(killed)
            mock_run.assert_not_called()

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.get_process_creation_time", return_value=133000000000000000.0)
    @patch("scripts.launcher.get_process_cmdline")
    @patch("scripts.launcher.get_process_name", return_value="node.exe")
    def test_ownership_invalid_foreign_frontend_rejected(self, mock_name, mock_cmdline, mock_ctime, mock_alive):
        """Tiến trình Vite của dự án khác không được nhận quyền sở hữu và không được kill"""
        mock_cmdline.return_value = 'node.exe D:\\AnotherRepo\\node_modules\\vite\\bin\\vite.js'

        saved_info = {"pid": 8000, "creation_time": 133000000000000000.0}
        ok, reason = verify_process_ownership(8000, "frontend", saved_info)
        self.assertFalse(ok)
        self.assertIn("không thuộc frontend của dự án này", reason)

        # Kiểm tra kill_process_tree từ chối dừng
        with patch("subprocess.run") as mock_run:
            killed, k_reason = kill_process_tree(8000, "frontend", saved_info)
            self.assertFalse(killed)
            mock_run.assert_not_called()

    # -------------------------------------------------------------------------
    # 3. PID Reuse & Stale State Tests
    # -------------------------------------------------------------------------

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.get_process_creation_time", return_value=134999999999999999.0)  # Different time!
    def test_pid_reuse_detected_and_rejected(self, mock_ctime, mock_alive):
        """Hệ điều hành tái sử dụng PID cho tiến trình mới -> phát hiện sai lệch creation time và từ chối kill"""
        saved_info = {"pid": 1234, "creation_time": 133000000000000000.0}
        ok, reason = verify_process_ownership(1234, "backend", saved_info)
        self.assertFalse(ok)
        self.assertIn("tái sử dụng", reason)

        with patch("subprocess.run") as mock_run:
            killed, _ = kill_process_tree(1234, "backend", saved_info)
            self.assertFalse(killed)
            mock_run.assert_not_called()

    @patch("scripts.launcher.is_pid_alive", return_value=False)
    def test_stale_state_file_safely_ignored_on_shutdown(self, mock_alive):
        """State file cũ chứa PID của tiến trình đã thoát -> shutdown bỏ qua an toàn và xóa state"""
        stale_state = {
            "backend": {"pid": 9999, "creation_time": 12345.0},
            "frontend": {"pid": 8888, "creation_time": 67890.0},
        }
        save_state(stale_state)

        launcher = Launcher()
        with patch("subprocess.run") as mock_run:
            code = launcher.run_shutdown()
            self.assertEqual(code, 0)
            mock_run.assert_not_called()

        # State file phải được xóa sạch sau shutdown
        self.assertFalse(self.state_file.exists())

    # -------------------------------------------------------------------------
    # 4. Port Collision & Double Startup Tests
    # -------------------------------------------------------------------------

    @patch("scripts.launcher.platform.system", return_value="Windows")
    @patch("scripts.launcher.ENV_FILE")
    @patch("scripts.launcher.shutil.which", return_value="dummy_path")
    @patch("scripts.launcher.VENV_PYTHON")
    @patch("scripts.launcher.get_port_listener_pid", return_value=4444)
    @patch("scripts.launcher.verify_process_ownership", return_value=(False, "Foreign process"))
    @patch("scripts.launcher.get_process_name", return_value="alien_app.exe")
    def test_port_occupied_by_unrelated_process_fails_cleanly(
        self, mock_name, mock_verify, mock_port, mock_venv, mock_which, mock_env, mock_sys
    ):
        """Cổng 8000 bị chiếm bởi tiến trình lạ -> báo lỗi rõ ràng, không kill tiến trình lạ"""
        mock_env.is_file.return_value = True
        mock_venv.is_file.return_value = True
        with patch.object(Path, "is_file", return_value=True):
            launcher = Launcher()
            launcher.env = {"MYSQL_HOST": "127.0.0.1"}
            ok, msg = launcher.check_environment()
            self.assertFalse(ok)
            self.assertIn("Cổng 8000 đang bị chiếm bởi tiến trình khác", msg)
            self.assertIn("alien_app.exe", msg)

    @patch("scripts.launcher.get_port_listener_pid", return_value=3333)
    @patch("scripts.launcher.verify_process_ownership", return_value=(True, "Verified backend"))
    @patch("urllib.request.urlopen")
    def test_double_startup_reuses_healthy_backend(self, mock_urlopen, mock_verify, mock_port):
        """Khởi động lần 2 khi backend đã chạy và healthy -> tái sử dụng PID, không tạo trùng tiến trình"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        launcher = Launcher()
        launcher.state = {"backend": {"pid": 3333}}

        with patch("subprocess.Popen") as mock_popen:
            ok, badge, pid, url = launcher.start_backend()
            self.assertTrue(ok)
            self.assertEqual(badge, "RUNNING (Existing)")
            self.assertEqual(pid, 3333)
            mock_popen.assert_not_called()

    # -------------------------------------------------------------------------
    # 5. Environment & Dependencies Precheck Tests
    # -------------------------------------------------------------------------

    @patch("scripts.launcher.platform.system", return_value="Windows")
    def test_missing_env_fails_before_checking_or_installing_npm(self, mock_sys):
        """Thiếu backend/.env -> báo lỗi ngay lập tức, không chạy npm install"""
        fake_env = Path(self.tmp_dir.name) / ".env.nonexistent"
        with patch("scripts.launcher.ENV_FILE", fake_env):
            with patch("subprocess.run") as mock_run:
                launcher = Launcher()
                ok, msg = launcher.check_environment()
                self.assertFalse(ok)
                self.assertIn("Thiếu file cấu hình backend\\.env", msg)
                mock_run.assert_not_called()

    @patch("scripts.launcher.platform.system", return_value="Windows")
    @patch("scripts.launcher.ENV_FILE")
    @patch("scripts.launcher.shutil.which", return_value="dummy_path")
    @patch("scripts.launcher.VENV_PYTHON")
    @patch("scripts.launcher.FRONTEND_DIR")
    def test_missing_frontend_dependencies_notifies_user_without_auto_install(
        self, mock_fe_dir, mock_venv, mock_which, mock_env, mock_sys
    ):
        """Thiếu node_modules frontend -> thông báo người dùng, không tự tiện npm install trừ khi có --install"""
        mock_env.is_file.return_value = True
        mock_venv.is_file.return_value = True
        (mock_fe_dir / "node_modules" / "vite" / "bin" / "vite.js").is_file.return_value = False

        launcher = Launcher()
        launcher.env = {}

        with patch("sys.argv", ["launcher.py", "start"]):
            with patch("subprocess.run") as mock_run:
                ok, msg = launcher.check_environment()
                self.assertFalse(ok)
                self.assertIn("Thư viện frontend chưa được cài đặt", msg)
                self.assertIn("npm install", msg)
                mock_run.assert_not_called()

    # -------------------------------------------------------------------------
    # 6. SQLite Connectivity Tests
    # -------------------------------------------------------------------------

    def test_sqlite_connection_success_read_only(self):
        """SQLite kết nối thành công với query SELECT 1 ở chế độ read-only"""
        db_path = Path(self.tmp_dir.name) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INT);")
        conn.commit()
        conn.close()

        launcher = Launcher()
        launcher.env = {
            "IMS_DATABASE_BACKEND": "sqlite",
            "IMS_SQLITE_PATH": str(db_path),
        }
        ok, badge, detail = launcher.check_and_start_mysql()
        self.assertTrue(ok)
        self.assertEqual(badge, "CONNECTED (SQLite)")

    def test_sqlite_connection_failure_nonexistent_or_corrupt(self):
        """SQLite không tồn tại file -> FAILED và không tự ý tạo database mới"""
        nonexistent = Path(self.tmp_dir.name) / "nonexistent.db"

        launcher = Launcher()
        launcher.env = {
            "IMS_DATABASE_BACKEND": "sqlite",
            "IMS_SQLITE_PATH": str(nonexistent),
        }
        ok, badge, detail = launcher.check_and_start_mysql()
        self.assertFalse(ok)
        self.assertEqual(badge, "FAILED")
        self.assertFalse(nonexistent.exists(), "Không được tự ý tạo database mới")

    # -------------------------------------------------------------------------
    # 7. MySQL Service Selection & Remote Connectivity
    # -------------------------------------------------------------------------

    @patch("subprocess.check_output")
    def test_mysql_multiple_services_requires_configuration(self, mock_output):
        """Phát hiện nhiều dịch vụ MySQL cục bộ -> không đoán bừa, yêu cầu cấu hình MYSQL_SERVICE_NAME"""
        # Giả lập sc.exe trả về cả MySQL80 và MariaDB đang dừng
        mock_output.side_effect = [
            "SERVICE_NAME: MySQL80\nSERVICE_NAME: MariaDB\n",
            "STATE: STOPPED\n",
            "STATE: STOPPED\n",
        ]
        svc, status, candidates = find_matching_mysql_service(configured_service="")
        self.assertIsNone(svc)
        self.assertEqual(status, "MULTIPLE")
        self.assertEqual(candidates, ["MySQL80", "MariaDB"])

    @patch("subprocess.check_output")
    def test_mysql_single_service_discovered(self, mock_output):
        """Phát hiện duy nhất một dịch vụ MySQL -> chọn dịch vụ đó"""
        mock_output.side_effect = [
            "SERVICE_NAME: MySQL80\n",
            "STATE: RUNNING\n",
        ]
        svc, status, candidates = find_matching_mysql_service(configured_service="")
        self.assertEqual(svc, "MySQL80")
        self.assertEqual(status, "RUNNING")

    @patch("scripts.launcher.is_tcp_open", return_value=False)
    def test_mysql_remote_host_skips_windows_service_discovery(self, mock_tcp):
        """MySQL remote không thể kết nối -> báo lỗi mạng từ xa, không tìm Windows Service"""
        launcher = Launcher()
        launcher.env = {
            "IMS_DATABASE_BACKEND": "mysql",
            "MYSQL_HOST": "10.0.0.99",
            "MYSQL_PORT": "3306",
        }
        with patch("scripts.launcher.find_matching_mysql_service") as mock_find_svc:
            ok, badge, detail = launcher.check_and_start_mysql()
            self.assertFalse(ok)
            self.assertIn("máy chủ MySQL từ xa", detail)
            mock_find_svc.assert_not_called()

    # -------------------------------------------------------------------------
    # 8. Safe Shutdown Tests
    # -------------------------------------------------------------------------

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.verify_process_ownership", return_value=(True, "Verified ownership"))
    @patch("subprocess.run")
    def test_safe_shutdown_terminates_only_verified_processes(self, mock_run, mock_verify, mock_alive):
        """Shutdown chỉ gọi taskkill đối với tiến trình thuộc quyền sở hữu của launcher"""
        mock_run.return_value = MagicMock(returncode=0)

        active_state = {
            "backend": {"pid": 1111, "creation_time": 12345.0},
            "frontend": {"pid": 2222, "creation_time": 67890.0},
        }
        save_state(active_state)

        launcher = Launcher()
        code = launcher.run_shutdown()
        self.assertEqual(code, 0)

        # Đã gọi taskkill đúng 2 lần (cho backend và frontend)
        self.assertEqual(mock_run.call_count, 2)
        # MySQL dịch vụ dùng chung không bị dừng
        self.assertFalse(self.state_file.exists())


if __name__ == "__main__":
    unittest.main()
