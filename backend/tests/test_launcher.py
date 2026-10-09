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
    OWNERSHIP_VERSION,
    _root_fingerprint,
    clear_state,
    find_matching_mysql_service,
    get_process_creation_time,
    is_pid_alive,
    is_tcp_open,
    load_state,
    parse_env_file,
    sanitize_text,
    save_state,
    terminate_owned_process,
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

    @staticmethod
    def owned_state(pid, process_type, creation_time=133000000000000000, token="a" * 32):
        return {
            "managed": True,
            "ownership_version": OWNERSHIP_VERSION,
            "process_type": process_type,
            "pid": pid,
            "creation_time": creation_time,
            "owner_token": token,
            "root_fingerprint": _root_fingerprint(),
            "port": 8000 if process_type == "backend" else 3000,
            "url": "http://127.0.0.1:8000" if process_type == "backend" else "http://localhost:3000",
        }

    @staticmethod
    def owned_cmdline(process_type, token="a" * 32):
        marker = f"IMS_LAUNCHER_OWNER={token};IMS_LAUNCHER_ROOT={_root_fingerprint()}"
        if process_type == "backend":
            return f"python.exe -c __ims_identity__='{marker}'; import uvicorn; uvicorn.run('backend.app.main:app')"
        return f"node.exe -e const __ims_identity__='{marker}'; import('vite').then(({{createServer}})=>strictPort:true)"

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
        mock_cmdline.return_value = self.owned_cmdline("backend")
        saved_info = self.owned_state(5000, "backend")
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
        mock_cmdline.return_value = self.owned_cmdline("frontend")
        saved_info = self.owned_state(6000, "frontend")
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

        saved_info = self.owned_state(7000, "backend")
        ok, reason = verify_process_ownership(7000, "backend", saved_info)
        self.assertFalse(ok)
        self.assertIn("identity token", reason)

        # An unowned process cannot reach the Windows termination handle.
        with patch("scripts.launcher._terminate_exact_windows_process") as mock_terminate:
            killed, k_reason = terminate_owned_process(7000, "backend", saved_info)
            self.assertFalse(killed)
            mock_terminate.assert_not_called()

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.get_process_creation_time", return_value=133000000000000000.0)
    @patch("scripts.launcher.get_process_cmdline")
    @patch("scripts.launcher.get_process_name", return_value="node.exe")
    def test_ownership_invalid_foreign_frontend_rejected(self, mock_name, mock_cmdline, mock_ctime, mock_alive):
        """Tiến trình Vite của dự án khác không được nhận quyền sở hữu và không được kill"""
        mock_cmdline.return_value = 'node.exe D:\\AnotherRepo\\node_modules\\vite\\bin\\vite.js'

        saved_info = self.owned_state(8000, "frontend")
        ok, reason = verify_process_ownership(8000, "frontend", saved_info)
        self.assertFalse(ok)
        self.assertIn("identity token", reason)

        # An unowned process cannot reach the Windows termination handle.
        with patch("scripts.launcher._terminate_exact_windows_process") as mock_terminate:
            killed, k_reason = terminate_owned_process(8000, "frontend", saved_info)
            self.assertFalse(killed)
            mock_terminate.assert_not_called()

    # -------------------------------------------------------------------------
    # 3. PID Reuse & Stale State Tests
    # -------------------------------------------------------------------------

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.get_process_creation_time", return_value=134999999999999999.0)  # Different time!
    def test_pid_reuse_detected_and_rejected(self, mock_ctime, mock_alive):
        """Hệ điều hành tái sử dụng PID cho tiến trình mới -> phát hiện sai lệch creation time và từ chối kill"""
        saved_info = self.owned_state(1234, "backend")
        ok, reason = verify_process_ownership(1234, "backend", saved_info)
        self.assertFalse(ok)
        self.assertIn("tái sử dụng", reason)

        with patch("scripts.launcher._terminate_exact_windows_process") as mock_terminate:
            killed, _ = terminate_owned_process(1234, "backend", saved_info)
            self.assertFalse(killed)
            mock_terminate.assert_not_called()

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.get_process_creation_time", return_value=None)
    def test_missing_creation_time_fails_closed(self, mock_ctime, mock_alive):
        state = self.owned_state(1235, "backend")
        ok, reason = verify_process_ownership(1235, "backend", state)
        self.assertFalse(ok)
        self.assertIn("Không đọc được creation time", reason)

    def test_state_without_creation_time_fails_before_process_inspection(self):
        state = self.owned_state(1236, "backend")
        state.pop("creation_time")
        with patch("scripts.launcher.is_pid_alive") as alive, patch(
            "scripts.launcher.get_process_creation_time"
        ) as process_time:
            ok, reason = verify_process_ownership(1236, "backend", state)
        self.assertFalse(ok)
        self.assertIn("State thiếu creation time", reason)
        alive.assert_not_called()
        process_time.assert_not_called()

    def test_manual_lookalike_without_launcher_state_is_not_owned(self):
        with patch("scripts.launcher.is_pid_alive", return_value=True), patch(
            "scripts.launcher.get_process_creation_time", return_value=133000000000000000
        ), patch("scripts.launcher.get_process_cmdline", return_value=self.owned_cmdline("backend")), patch(
            "scripts.launcher.get_process_name", return_value="python.exe"
        ):
            ok, reason = verify_process_ownership(5001, "backend", None)
        self.assertFalse(ok)
        self.assertIn("metadata sở hữu", reason)

    @patch("scripts.launcher.platform.system", return_value="Windows")
    def test_exact_handle_recheck_refuses_pid_reuse_before_termination(self, mock_system):
        import ctypes
        from ctypes import wintypes
        from scripts import launcher as launcher_module

        fake_kernel = MagicMock()
        fake_kernel.OpenProcess.return_value = ctypes.c_void_p(77)

        def set_current_creation_time(handle, creation_ptr, exit_ptr, kernel_ptr, user_ptr):
            creation = ctypes.cast(creation_ptr, ctypes.POINTER(wintypes.FILETIME)).contents
            creation.dwHighDateTime = 0
            creation.dwLowDateTime = 999
            return 1

        fake_kernel.GetProcessTimes.side_effect = set_current_creation_time
        with patch("ctypes.WinDLL", return_value=fake_kernel):
            stopped, detail = launcher_module._terminate_exact_windows_process(77, 123)

        self.assertFalse(stopped)
        self.assertIn("đổi process", detail)
        fake_kernel.TerminateProcess.assert_not_called()
        fake_kernel.CloseHandle.assert_called_once()

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

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.verify_process_ownership", return_value=(False, "creation time unavailable"))
    def test_shutdown_retains_state_when_live_process_cannot_be_verified(self, mock_verify, mock_alive):
        save_state({"backend": self.owned_state(7654, "backend")})
        launcher = Launcher()
        with patch("scripts.launcher._terminate_exact_windows_process") as mock_terminate:
            self.assertEqual(launcher.run_shutdown(), 0)
        mock_terminate.assert_not_called()
        self.assertTrue(self.state_file.exists())

    # -------------------------------------------------------------------------
    # 4. Port Collision & Double Startup Tests
    # -------------------------------------------------------------------------

    @patch("scripts.launcher.get_port_listener_pid", return_value=4444)
    @patch("scripts.launcher.verify_process_ownership", return_value=(False, "Foreign process"))
    @patch.object(Launcher, "_backend_is_healthy", return_value=False)
    @patch("scripts.launcher.get_process_name", return_value="alien_app.exe")
    def test_port_occupied_by_unrelated_process_fails_cleanly(
        self, mock_name, mock_health, mock_verify, mock_port
    ):
        """Port conflict fails closed without spawning over or terminating a foreign process."""
        launcher = Launcher()
        ok, badge, pid, msg = launcher.start_backend()
        self.assertFalse(ok)
        self.assertEqual(pid, 0)
        self.assertIn("Cổng 8000 đang bị chiếm", msg)

    @patch("scripts.launcher.get_port_listener_pid", return_value=4445)
    @patch("scripts.launcher.verify_process_ownership", return_value=(False, "No launcher state"))
    @patch.object(Launcher, "_backend_is_healthy", return_value=True)
    def test_healthy_external_backend_is_reused_but_not_managed(self, mock_health, mock_verify, mock_port):
        launcher = Launcher()
        ok, badge, pid, url = launcher.start_backend()
        self.assertTrue(ok)
        self.assertEqual(badge, "RUNNING (External)")
        self.assertEqual(pid, 0)
        self.assertNotIn("backend", launcher.managed_processes)

    @patch("scripts.launcher.get_port_listener_pid", return_value=4446)
    @patch("scripts.launcher.verify_process_ownership", return_value=(False, "No launcher state"))
    @patch.object(Launcher, "_frontend_is_healthy", return_value=True)
    def test_healthy_external_frontend_is_reused_but_not_managed(self, mock_health, mock_verify, mock_port):
        launcher = Launcher()
        ok, badge, pid, url = launcher.start_frontend()
        self.assertTrue(ok)
        self.assertEqual(badge, "RUNNING (External)")
        self.assertEqual(pid, 0)
        self.assertNotIn("frontend", launcher.managed_processes)

    @patch("scripts.launcher.get_port_listener_pid", return_value=3333)
    @patch("scripts.launcher.verify_process_ownership", return_value=(True, "Verified backend"))
    @patch("urllib.request.urlopen")
    def test_double_startup_reuses_healthy_backend(self, mock_urlopen, mock_verify, mock_port):
        """Khởi động lần 2 khi backend đã chạy và healthy -> tái sử dụng PID, không tạo trùng tiến trình"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        launcher = Launcher()
        launcher.state = {"backend": self.owned_state(3333, "backend")}
        with patch.object(Launcher, "_backend_is_healthy", return_value=True):
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

    def test_mysql_service_requires_explicit_configuration(self):
        """Không dò theo tên, kể cả khi máy chỉ có duy nhất một service MySQL."""
        svc, status, candidates = find_matching_mysql_service(configured_service="")
        self.assertIsNone(svc)
        self.assertEqual(status, "CONFIGURE_REQUIRED")
        self.assertEqual(candidates, [])

    @patch("subprocess.check_output")
    def test_mysql_explicit_service_must_match_executable_and_port(self, mock_output):
        """Chỉ service được cấu hình chính xác, chạy mysqld và khai báo đúng port mới được chọn."""
        mock_output.side_effect = [
            "[SC] QueryServiceConfig SUCCESS\n        BINARY_PATH_NAME   : \"C:\\MySQL\\bin\\mysqld.exe\" --port=3306\n",
            "SERVICE_NAME: MySQL80\n        STATE              : 4  RUNNING\n",
        ]
        svc, status, candidates = find_matching_mysql_service(configured_service="MySQL80", expected_port=3306)
        self.assertEqual(svc, "MySQL80")
        self.assertEqual(status, "RUNNING")
        self.assertEqual(candidates, ["MySQL80"])

    @patch("subprocess.check_output")
    def test_mysql_service_port_mismatch_is_rejected(self, mock_output):
        mock_output.return_value = (
            "[SC] QueryServiceConfig SUCCESS\n"
            "        BINARY_PATH_NAME   : \"C:\\MySQL\\bin\\mysqld.exe\" --port=3307\n"
        )
        svc, status, _ = find_matching_mysql_service("MySQL80", expected_port=3306)
        self.assertIsNone(svc)
        self.assertEqual(status, "PORT_MISMATCH")

    @patch("subprocess.check_output")
    def test_mysql_configured_service_with_non_mysql_executable_is_rejected(self, mock_output):
        mock_output.return_value = (
            "[SC] QueryServiceConfig SUCCESS\n"
            "        BINARY_PATH_NAME   : \"C:\\Other\\service.exe\" --port=3306\n"
        )
        svc, status, _ = find_matching_mysql_service("SomeService", expected_port=3306)
        self.assertIsNone(svc)
        self.assertEqual(status, "NOT_MYSQL")

    def test_mysql_service_port_can_be_read_from_defaults_file(self):
        ini = Path(self.tmp_dir.name) / "my.ini"
        ini.write_text("[client]\nport=3307\n[mysqld]\nport=3306\n", encoding="utf-8")
        command = f'"C:\\MySQL\\bin\\mysqld.exe" --defaults-file="{ini}"'
        from scripts.launcher import _mysql_service_configured_port
        self.assertEqual(_mysql_service_configured_port(command), 3306)

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

    def test_mysql_connected_port_does_not_start_a_windows_service(self):
        launcher = Launcher()
        launcher.env = {
            "IMS_DATABASE_BACKEND": "mysql",
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_PORT": "3306",
            "MYSQL_USER": "test",
            "MYSQL_PASSWORD": "test",
            "MYSQL_DATABASE": "test_db",
        }
        fake_mysql = MagicMock()
        fake_connection = MagicMock()
        fake_mysql.connect.return_value = fake_connection
        with patch.dict(sys.modules, {"pymysql": fake_mysql}), patch(
            "scripts.launcher.is_tcp_open", return_value=True
        ), patch("scripts.launcher.find_matching_mysql_service") as find_service, patch(
            "scripts.launcher.start_windows_service"
        ) as start_service:
            ok, badge, detail = launcher.check_and_start_mysql()
        self.assertTrue(ok)
        self.assertEqual(badge, "CONNECTED")
        find_service.assert_not_called()
        start_service.assert_not_called()

    @patch("scripts.launcher.time.sleep")
    @patch("scripts.launcher.get_port_listener_pid", return_value=202)
    @patch("scripts.launcher.get_windows_service_pid", return_value=101)
    @patch("scripts.launcher.start_windows_service", return_value=(True, ""))
    @patch("scripts.launcher.find_matching_mysql_service", return_value=("MySQL80", "STOPPED", ["MySQL80"]))
    @patch("scripts.launcher.is_tcp_open", side_effect=[False, True])
    def test_started_mysql_service_must_own_the_configured_port(
        self, mock_tcp, mock_find, mock_start, mock_service_pid, mock_listener_pid, mock_sleep
    ):
        launcher = Launcher()
        launcher.env = {
            "IMS_DATABASE_BACKEND": "mysql",
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_PORT": "3306",
            "MYSQL_SERVICE_NAME": "MySQL80",
            "MYSQL_USER": "test",
            "MYSQL_PASSWORD": "test",
            "MYSQL_DATABASE": "test_db",
        }
        fake_mysql = MagicMock()
        with patch.dict(sys.modules, {"pymysql": fake_mysql}):
            ok, badge, detail = launcher.check_and_start_mysql()
        self.assertFalse(ok)
        self.assertIn("listener PID=202", detail)
        fake_mysql.connect.assert_not_called()

    # -------------------------------------------------------------------------
    # 8. Safe Shutdown Tests
    # -------------------------------------------------------------------------

    @patch("scripts.launcher.is_pid_alive", return_value=True)
    @patch("scripts.launcher.verify_process_ownership", return_value=(True, "Verified ownership"))
    @patch("scripts.launcher._terminate_exact_windows_process", return_value=(True, "stopped exact process"))
    def test_safe_shutdown_terminates_only_verified_processes(self, mock_terminate, mock_verify, mock_alive):
        """Shutdown terminates only the verified process handles, never taskkill PID trees."""
        active_state = {
            "state_version": OWNERSHIP_VERSION,
            "backend": self.owned_state(1111, "backend"),
            "frontend": self.owned_state(2222, "frontend", token="b" * 32),
        }
        save_state(active_state)

        launcher = Launcher()
        code = launcher.run_shutdown()
        self.assertEqual(code, 0)

        self.assertEqual(mock_terminate.call_count, 2)
        self.assertEqual(mock_terminate.call_args_list[0].args, (2222, active_state["frontend"]["creation_time"]))
        self.assertEqual(mock_terminate.call_args_list[1].args, (1111, active_state["backend"]["creation_time"]))
        # MySQL dịch vụ dùng chung không bị dừng
        self.assertFalse(self.state_file.exists())


if __name__ == "__main__":
    unittest.main()
