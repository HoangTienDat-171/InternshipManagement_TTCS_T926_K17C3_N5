#!/usr/bin/env python3
"""
Internship Management System - One-Click Launcher & Safe Shutdown Controller.
Cross-platform compatible for Windows environments. Pure Python standard library.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import smtplib
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
import uuid
from pathlib import Path

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
LOGS_DIR = ROOT_DIR / "logs"
ENV_FILE = BACKEND_DIR / ".env"
ENV_EXAMPLE_FILE = BACKEND_DIR / ".env.example"
VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
STATE_FILE = LOGS_DIR / "launcher_state.json"
STARTUP_LOG = LOGS_DIR / "startup.log"
BACKEND_LOG = LOGS_DIR / "backend.log"
FRONTEND_LOG = LOGS_DIR / "frontend.log"


def get_current_timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize_text(text: str) -> str:
    """Mask sensitive fields like passwords, secrets, and auth tokens."""
    if not text:
        return ""
    text = re.sub(r"(?i)(password|secret|token|mat_khau)\s*=\s*[^\s,;]+", r"\1=******", text)
    text = re.sub(r"(?i)(['\"](?:password|secret|token)['\"]\s*:\s*['\"])[^'\"]+(['\"])", r"\1******\2", text)
    return text


def log_startup(event: str, details: str = "", level: str = "INFO"):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        sanitized_details = sanitize_text(details)
        log_line = f"[{get_current_timestamp()}] [{level.upper()}] [{event}] {sanitized_details}\n"
        with open(STARTUP_LOG, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass


def parse_env_file(path: Path) -> dict[str, str]:
    env_vars: dict[str, str] = {}
    if not path.is_file():
        return env_vars
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            env_vars[key] = val
    except Exception as exc:
        log_startup("ENV_READ_ERROR", str(exc), level="ERROR")
    return env_vars


def is_tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def get_port_listener_pid(port: int) -> int | None:
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            text=True, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            line = line.strip()
            if "LISTENING" in line and f":{port}" in line:
                parts = line.split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}"):
                    try:
                        return int(parts[-1])
                    except ValueError:
                        continue
    except Exception:
        pass
    return None


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        if out and not out.startswith("INFO:") and f'"{pid}"' in out:
            return True
    except Exception:
        pass
    return False


def get_process_creation_time(pid: int) -> int | None:
    """
    Retrieves process creation time on Windows as an exact FILETIME uint64 integer.
    Uses ctypes for speed, with PowerShell CIM fallback.
    """
    if pid <= 0:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        PROCESS_QUERY_INFORMATION = 0x0400
        h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_proc:
            h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if h_proc:
            try:
                creation_time = wintypes.FILETIME()
                exit_time = wintypes.FILETIME()
                kernel_time = wintypes.FILETIME()
                user_time = wintypes.FILETIME()
                if ctypes.windll.kernel32.GetProcessTimes(
                    h_proc,
                    ctypes.byref(creation_time),
                    ctypes.byref(exit_time),
                    ctypes.byref(kernel_time),
                    ctypes.byref(user_time),
                ):
                    ft_u64 = (creation_time.dwHighDateTime << 32) | creation_time.dwLowDateTime
                    return ft_u64
            finally:
                ctypes.windll.kernel32.CloseHandle(h_proc)
    except Exception:
        pass

    try:
        cmd = [
            "powershell.exe", "-NoProfile", "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CreationDate.ToFileTime()"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip().isdigit():
            return int(res.stdout.strip())
    except Exception:
        pass
    return None


def get_process_cmdline(pid: int) -> str:
    try:
        cmd = [
            "powershell.exe", "-NoProfile", "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def get_process_name(pid: int) -> str:
    try:
        out = subprocess.check_output(
            ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        if out and not out.startswith("INFO:"):
            parts = [p.strip('"') for p in out.split('","')]
            if parts:
                return parts[0].strip('"')
    except Exception:
        pass
    return ""


OWNERSHIP_VERSION = 2


def _root_fingerprint() -> str:
    normalized_root = os.path.normcase(str(ROOT_DIR.resolve())).casefold()
    return hashlib.sha256(normalized_root.encode("utf-8")).hexdigest()


def _has_valid_launcher_state(pid: int, expected_type: str, saved_proc_info: dict | None) -> tuple[bool, str]:
    if not isinstance(saved_proc_info, dict):
        return False, "Không có metadata sở hữu của launcher"
    if saved_proc_info.get("managed") is not True:
        return False, "State không xác nhận tiến trình do launcher quản lý"
    if saved_proc_info.get("ownership_version") != OWNERSHIP_VERSION:
        return False, "State launcher cũ hoặc không hợp lệ"
    if saved_proc_info.get("process_type") != expected_type:
        return False, "Loại tiến trình trong state không khớp"
    if saved_proc_info.get("pid") != pid:
        return False, "PID không khớp state launcher"
    if saved_proc_info.get("root_fingerprint") != _root_fingerprint():
        return False, "State thuộc thư mục dự án khác"
    token = saved_proc_info.get("owner_token")
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
        return False, "State thiếu token sở hữu hợp lệ"
    creation_time = saved_proc_info.get("creation_time")
    if isinstance(creation_time, bool) or not isinstance(creation_time, int) or creation_time <= 0:
        return False, "State thiếu creation time hợp lệ"
    return True, "OK"


def verify_process_ownership(pid: int, expected_type: str, saved_proc_info: dict | None = None) -> tuple[bool, str]:
    """
    Verifies process identity and ownership strictly:
    1. Checks if PID is active.
    2. Validates process creation time against saved state to detect PID reuse.
    3. Verifies process executable and command line belong strictly to our project root.
    """
    if pid <= 0:
        return False, "PID không hợp lệ"
    state_ok, state_reason = _has_valid_launcher_state(pid, expected_type, saved_proc_info)
    if not state_ok:
        return False, state_reason
    if not is_pid_alive(pid):
        return False, f"Tiến trình PID {pid} không còn hoạt động"

    curr_ctime = get_process_creation_time(pid)
    if curr_ctime is None:
        return False, f"Không đọc được creation time của PID {pid}"
    if curr_ctime != saved_proc_info["creation_time"]:
        return False, f"PID {pid} đã bị hệ điều hành tái sử dụng (creation time không khớp)"

    cmdline = get_process_cmdline(pid).lower()
    proc_name = get_process_name(pid).lower()
    if not cmdline or not proc_name:
        return False, f"Không đọc đủ process identity cho PID {pid}"
    token_marker = f"ims_launcher_owner={saved_proc_info['owner_token']}"
    root_marker = f"ims_launcher_root={_root_fingerprint()}"
    if token_marker not in cmdline or root_marker not in cmdline:
        return False, f"PID {pid} không mang identity token do launcher này tạo"

    if expected_type == "backend":
        is_python = Path(proc_name).name in ("python.exe", "pythonw.exe")
        if is_python and "uvicorn.run" in cmdline and "backend.app.main:app" in cmdline:
            return True, "Xác minh thành công backend của dự án"
        return False, f"Tiến trình PID {pid} không thuộc backend của dự án này"

    elif expected_type == "frontend":
        is_node = Path(proc_name).name == "node.exe"
        if is_node and "createserver" in cmdline and "import('vite')" in cmdline and "strictport" in cmdline:
            return True, "Xác minh thành công frontend của dự án"
        return False, f"Tiến trình PID {pid} không thuộc frontend của dự án này"

    return False, f"Loại tiến trình không xác định: {expected_type}"


def _terminate_exact_windows_process(pid: int, expected_creation_time: int) -> tuple[bool, str]:
    """Terminate one verified process using a stable Windows handle, never its PID tree."""
    if platform.system() != "Windows":
        return False, "Chỉ hỗ trợ dừng process bằng Windows process handle"
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        get_process_times = kernel32.GetProcessTimes
        get_process_times.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        get_process_times.restype = wintypes.BOOL
        terminate_process = kernel32.TerminateProcess
        terminate_process.argtypes = [wintypes.HANDLE, wintypes.UINT]
        terminate_process.restype = wintypes.BOOL
        wait_for_single_object = kernel32.WaitForSingleObject
        wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        wait_for_single_object.restype = wintypes.DWORD
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        process_terminate = 0x0001
        process_query_limited_information = 0x1000
        synchronize = 0x00100000
        handle = open_process(
            process_terminate | process_query_limited_information | synchronize,
            False,
            pid,
        )
        if not handle:
            return False, f"OpenProcess thất bại (Windows error {ctypes.get_last_error()})"
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not get_process_times(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return False, "Không đọc được creation time từ process handle"
            actual_creation_time = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            if actual_creation_time != expected_creation_time:
                return False, "PID đã đổi process trước khi mở handle; process được giữ nguyên"
            if not terminate_process(handle, 1):
                return False, f"TerminateProcess thất bại (Windows error {ctypes.get_last_error()})"
            if wait_for_single_object(handle, 5000) != 0:
                return False, "Process chưa kết thúc sau khi gửi yêu cầu dừng"
            return True, "Đã dừng đúng process đã xác minh"
        finally:
            close_handle(handle)
    except Exception as exc:
        return False, f"Không thể dừng process an toàn: {exc}"


def terminate_owned_process(pid: int, expected_type: str, saved_proc_info: dict | None = None) -> tuple[bool, str]:
    """
    Terminates only the exact process safely when ownership is strictly verified.
    Refuses to stop foreign/unverified processes and never terminates descendants.
    """
    is_owned, reason = verify_process_ownership(pid, expected_type, saved_proc_info)
    if not is_owned:
        log_startup(f"{expected_type.upper()}_PRESERVED", f"Từ chối kill PID {pid}: {reason}", level="WARNING")
        return False, reason

    try:
        terminated, detail = _terminate_exact_windows_process(pid, saved_proc_info["creation_time"])
        if terminated:
            log_startup(f"{expected_type.upper()}_STOPPED", f"Đã dừng tiến trình PID {pid}")
            return True, detail
        return False, detail
    except Exception as exc:
        return False, str(exc)


def load_state() -> dict:
    if STATE_FILE.is_file():
        try:
            loaded = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            pass
    return {}


def save_state(state: dict):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as exc:
        log_startup("STATE_SAVE_ERROR", str(exc), level="ERROR")


def clear_state():
    try:
        if STATE_FILE.is_file():
            STATE_FILE.unlink()
    except Exception:
        pass


def _mysql_service_configured_port(service_command: str) -> int | None:
    port_match = re.search(r"--port(?:=|\s+)(\d+)\b", service_command, flags=re.IGNORECASE)
    if port_match:
        return int(port_match.group(1))

    defaults_match = re.search(
        r"--defaults-file(?:=|\s+)\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s]+))",
        service_command,
        flags=re.IGNORECASE,
    )
    if not defaults_match:
        return None
    defaults_path = next((part for part in defaults_match.groups() if part), "")
    path = Path(defaults_path)
    if not path.is_absolute():
        return None
    try:
        in_mysql_section = False
        configured_ports = set()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("!"):
                return None
            section_match = re.fullmatch(r"\[([^]]+)\]", line)
            if section_match:
                in_mysql_section = section_match.group(1).strip().casefold() == "mysqld"
            elif in_mysql_section:
                port_value = re.fullmatch(r"port\s*=\s*(\d+)\s*", line, flags=re.IGNORECASE)
                if port_value:
                    configured_ports.add(int(port_value.group(1)))
        if len(configured_ports) == 1:
            return configured_ports.pop()
    except OSError:
        return None
    return None


def find_matching_mysql_service(
    configured_service: str = "", expected_port: int = 3306
) -> tuple[str | None, str, list[str]]:
    """Validate one explicitly configured local MySQL service and its listening port."""
    if not configured_service.strip():
        return None, "CONFIGURE_REQUIRED", []
    try:
        qc_out = subprocess.check_output(
            ["sc.exe", "qc", configured_service], text=True, stderr=subprocess.DEVNULL
        )
        binary_line = next(
            (line.split(":", 1)[1].strip() for line in qc_out.splitlines()
             if "BINARY_PATH_NAME" in line.upper() and ":" in line),
            "",
        )
        executable_match = re.match(
            r'^\s*"([^\"]+\.exe)"|^\s*(.+?\.exe)(?:\s|$)',
            binary_line,
            flags=re.IGNORECASE,
        )
        executable = next((part for part in executable_match.groups() if part), "") if executable_match else ""
        if Path(executable).name.casefold() not in ("mysqld.exe", "mariadbd.exe"):
            return None, "NOT_MYSQL", [configured_service]
        actual_port = _mysql_service_configured_port(binary_line)
        if actual_port is None:
            return None, "PORT_UNVERIFIED", [configured_service]
        if actual_port != expected_port:
            return None, "PORT_MISMATCH", [configured_service]
        state_out = subprocess.check_output(
            ["sc.exe", "query", configured_service], text=True, stderr=subprocess.DEVNULL
        )
        status = "RUNNING" if re.search(r"STATE\s*:\s*\d+\s+RUNNING", state_out, re.IGNORECASE) else "STOPPED"
        return configured_service, status, [configured_service]
    except Exception:
        return None, "NOT_FOUND_OR_UNVERIFIED", []


def get_windows_service_pid(service_name: str) -> int | None:
    try:
        output = subprocess.check_output(
            ["sc.exe", "queryex", service_name], text=True, stderr=subprocess.DEVNULL
        )
        match = re.search(r"\bPID\s*:\s*(\d+)\b", output, re.IGNORECASE)
        pid = int(match.group(1)) if match else 0
        return pid or None
    except Exception:
        return None


def start_windows_service(svc_name: str) -> tuple[bool, str]:
    """Attempts to start Windows service. Returns (success, error_reason)."""
    try:
        res = subprocess.run(
            ["net.exe", "start", svc_name],
            capture_output=True, text=True, timeout=20
        )
        if res.returncode == 0:
            return True, ""
        err = res.stderr.strip() or res.stdout.strip()
        if "5" in err or "access is denied" in err.lower() or "quyen" in err.lower():
            return False, f"Không có quyền Administrator để khởi động service '{svc_name}'."
        return False, err
    except Exception as exc:
        return False, str(exc)


class Launcher:
    def __init__(self):
        self.state = load_state()
        self.env = parse_env_file(ENV_FILE)
        self.python_exe = VENV_PYTHON if VENV_PYTHON.is_file() else Path(sys.executable)
        self.managed_processes: dict[str, dict] = {}

    def _make_process_state(self, pid: int, process_type: str, owner_token: str, port: int, url: str) -> dict | None:
        creation_time = get_process_creation_time(pid)
        if creation_time is None:
            return None
        return {
            "managed": True,
            "ownership_version": OWNERSHIP_VERSION,
            "process_type": process_type,
            "pid": pid,
            "creation_time": creation_time,
            "owner_token": owner_token,
            "root_fingerprint": _root_fingerprint(),
            "port": port,
            "url": url,
        }

    def _persist_managed_processes(self):
        state = {
            "state_version": OWNERSHIP_VERSION,
            "started_at": get_current_timestamp(),
            "mysql": self.state.get("mysql", {}),
            "smtp": self.state.get("smtp", {}),
            "worker": self.state.get("worker", {}),
            "browser_opened": self.state.get("browser_opened", False),
        }
        state.update(self.managed_processes)
        save_state(state)
        self.state = state

    @staticmethod
    def _stop_spawned_child(proc) -> None:
        """Stop only the direct child represented by our Popen handle."""
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        except Exception:
            pass

    @staticmethod
    def _backend_is_healthy(url: str) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status != 200:
                    return False
                payload = json.loads(response.read().decode("utf-8"))
                return (
                    payload.get("system") == "Hệ thống Quản lý Thực tập sinh"
                    and payload.get("status") == "Online"
                )
        except Exception:
            return False

    @staticmethod
    def _frontend_is_healthy(url: str) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status != 200:
                    return False
                document = response.read().decode("utf-8", errors="replace").lower()
                return 'id="root"' in document and "/src/main.jsx" in document
        except Exception:
            return False

    def print_banner(self):
        print("=========================================")
        print(" INTERNSHIP MANAGEMENT - SERVER STARTUP")
        print("=========================================")

    def check_environment(self) -> tuple[bool, str]:
        # 1. OS Check
        if platform.system() != "Windows":
            return False, "Hệ thống launcher này được thiết kế dành cho môi trường Microsoft Windows."

        # 2. Check .env file (Bắt buộc kiểm tra cấu hình TRƯỚC TIÊN)
        if not ENV_FILE.is_file():
            log_startup("ENV_MISSING", "backend/.env is missing", level="ERROR")
            return False, (
                "Thiếu file cấu hình backend\\.env.\n"
                "  Vui lòng sao chép từ backend\\.env.example và điền thông tin kết nối MySQL/SMTP:\n"
                "  copy backend\\.env.example backend\\.env"
            )

        # Parse env file
        self.env = parse_env_file(ENV_FILE)

        # 3. Node.js & npm Check in PATH
        if not shutil.which("node"):
            return False, "Không tìm thấy Node.js trong PATH. Vui lòng cài đặt Node.js LTS (https://nodejs.org/)."
        if not shutil.which("npm"):
            return False, "Không tìm thấy npm trong PATH. Vui lòng kiểm tra lại cài đặt Node.js."

        # 4. Python Environment Check
        if not VENV_PYTHON.is_file():
            try:
                import fastapi  # noqa: F401
                import uvicorn  # noqa: F401
                import pymysql  # noqa: F401
                import cryptography  # noqa: F401
                import bcrypt  # noqa: F401
            except ImportError:
                return False, (
                    "Thiếu virtual environment tại backend\\.venv\\Scripts\\python.exe.\n"
                    "  Vui lòng tạo venv: python -m venv backend\\.venv\n"
                    "  Và cài đặt: backend\\.venv\\Scripts\\python.exe -m pip install -r backend\\requirements.txt"
                )

        # 5. Frontend dependencies check
        vite_bin = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        if not vite_bin.is_file():
            allow_install = "--install" in sys.argv or "--setup" in sys.argv
            if allow_install:
                print("  -> Đang cài đặt gói thư viện Frontend ban đầu (npm install)...")
                res = subprocess.run(
                    ["npm.cmd", "install", "--no-audit", "--no-fund"],
                    cwd=str(FRONTEND_DIR), capture_output=True, text=True
                )
                if res.returncode != 0:
                    return False, f"Cài đặt thư viện frontend thất bại: {res.stderr.strip() or res.stdout.strip()}"
            else:
                return False, (
                    "Thư viện frontend chưa được cài đặt (thiếu frontend\\node_modules).\n"
                    "  Vui lòng chạy: cd frontend && npm install\n"
                    "  Hoặc chạy launcher với cờ '--install' để tự động cài đặt."
                )

        # Port ownership/health is checked immediately before each service starts.
        # External healthy services may be reused but are never added to shutdown state.
        log_startup("ENV_CHECK_OK", "Environment and dependencies verified successfully")
        return True, "OK"

    def check_and_start_mysql(self) -> tuple[bool, str, str]:
        backend_type = self.env.get("IMS_DATABASE_BACKEND", "mysql").strip().lower()

        if backend_type == "sqlite":
            sqlite_path = Path(self.env.get("IMS_SQLITE_PATH", str(BACKEND_DIR / "app" / "internship.db"))).resolve()
            if not sqlite_path.is_file():
                return False, "FAILED", f"SQLite database không tồn tại tại {sqlite_path}"
            try:
                uri = f"{sqlite_path.as_uri()}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=5)
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
                conn.close()
                log_startup("SQLITE_CHECK", f"Verified SQLite connection at {sqlite_path}")
                return True, "CONNECTED (SQLite)", f"SQLite Mode ({sqlite_path.name})"
            except Exception as exc:
                log_startup("SQLITE_CONNECT_ERROR", str(exc), level="ERROR")
                return False, "FAILED", f"Không thể kết nối đến cơ sở dữ liệu SQLite tại {sqlite_path}: {exc}"

        # MySQL backend
        host = self.env.get("MYSQL_HOST", "127.0.0.1").strip()
        port = int(self.env.get("MYSQL_PORT", "3306").strip() or 3306)
        user = self.env.get("MYSQL_USER", "root").strip()
        password = self.env.get("MYSQL_PASSWORD", "")
        database = self.env.get("MYSQL_DATABASE", "internship_management").strip()

        is_local = host in ("127.0.0.1", "localhost", "::1")
        tcp_ready = is_tcp_open(host, port, timeout=2.0)

        if not tcp_ready:
            if not is_local:
                log_startup("MYSQL_REMOTE_UNREACHABLE", f"Cannot connect to remote MySQL at {host}:{port}", level="ERROR")
                return False, "FAILED", f"Không thể kết nối đến máy chủ MySQL từ xa tại {host}:{port}. Vui lòng kiểm tra kết nối mạng."

            cfg_svc = self.env.get("MYSQL_SERVICE_NAME", "").strip()
            svc_name, svc_status, candidates = find_matching_mysql_service(cfg_svc, port)

            if not svc_name:
                status_help = {
                    "CONFIGURE_REQUIRED": "Chưa cấu hình MYSQL_SERVICE_NAME.",
                    "NOT_MYSQL": "Service được cấu hình không chạy mysqld.exe hoặc mariadbd.exe.",
                    "PORT_UNVERIFIED": "Không xác minh được port từ cấu hình service.",
                    "PORT_MISMATCH": f"Port trong service không khớp MYSQL_PORT={port}.",
                }.get(svc_status, "Không tìm thấy hoặc không xác minh được service đã cấu hình.")
                log_startup("MYSQL_SERVICE_NOT_VERIFIED", f"{status_help} candidates={candidates}", level="ERROR")
                return False, "FAILED", (
                    f"MySQL cục bộ chưa chạy trên cổng {port}. {status_help}\n"
                    "  Hãy cấu hình MYSQL_SERVICE_NAME đúng service và bảo đảm service khai báo --port "
                    f"{port} hoặc --defaults-file có [mysqld] port={port}; nếu dùng XAMPP/Laragon/Docker, hãy khởi động thủ công."
                )

            # Service found, attempt to start
            print(f"  -> Đang khởi động Windows Service '{svc_name}'...")
            log_startup("MYSQL_SERVICE_START_ATTEMPT", f"Starting service {svc_name}")
            started, err_msg = start_windows_service(svc_name)
            if not started:
                log_startup("MYSQL_SERVICE_START_FAILED", f"Service {svc_name} start failed: {err_msg}", level="ERROR")
                return False, "FAILED", (
                    f"Không thể khởi động service '{svc_name}': {err_msg}\n"
                    "  Vui lòng mở Services (services.msc) để khởi động MySQL thủ công hoặc chạy launcher với quyền Administrator."
                )

            # Wait for MySQL TCP readiness
            for _ in range(15):
                time.sleep(1)
                if is_tcp_open(host, port, timeout=1.0):
                    tcp_ready = True
                    break

            if not tcp_ready:
                return False, "FAILED", f"Đã khởi động service '{svc_name}' nhưng cổng MySQL {port} chưa sẵn sàng sau 15 giây."
            service_pid = get_windows_service_pid(svc_name)
            listener_pid = get_port_listener_pid(port)
            if not service_pid or listener_pid != service_pid:
                return False, "FAILED", (
                    f"Service '{svc_name}' đã mở cổng {port}, nhưng không xác minh được listener thuộc PID của service "
                    f"(service PID={service_pid}, listener PID={listener_pid}). Service được giữ nguyên."
                )

        # Verify database connection read-only (SELECT 1)
        try:
            import pymysql
            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                charset="utf8mb4",
                connect_timeout=5,
                autocommit=False
            )
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.close()
            log_startup("MYSQL_CONNECTED", f"Connected to MySQL database '{database}' on {host}:{port}")
            return True, "CONNECTED", f"MySQL on {host}:{port}"
        except Exception as exc:
            code = getattr(exc, "args", [None])[0] if hasattr(exc, "args") else None
            msg = str(exc)
            if code == 1049:
                detail = f"Database '{database}' không tồn tại trong MySQL. Vui lòng tạo cơ sở dữ liệu '{database}' trước khi khởi động."
            elif code in (1045, 1698):
                detail = f"Xác thực MySQL thất bại cho user '{user}'. Vui lòng kiểm tra lại MYSQL_PASSWORD trong backend\\.env."
            else:
                detail = f"Lỗi kết nối cơ sở dữ liệu MySQL: {msg}"
            log_startup("MYSQL_CONNECT_ERROR", detail, level="ERROR")
            return False, "FAILED", detail

    def start_backend(self) -> tuple[bool, str, int, str]:
        port = 8000
        health_url = f"http://127.0.0.1:{port}/"

        p_pid = get_port_listener_pid(port)
        if p_pid:
            saved_be = self.state.get("backend", {})
            is_our_backend, _ = verify_process_ownership(p_pid, "backend", saved_be)
            if is_our_backend:
                if self._backend_is_healthy(health_url):
                    self.managed_processes["backend"] = saved_be
                    log_startup("BACKEND_REUSED", f"Managed backend already running on PID {p_pid}")
                    return True, "RUNNING (Existing)", p_pid, health_url
                return False, "FAILED", 0, f"Backend launcher-owned PID {p_pid} chiếm cổng nhưng health check không đạt."
            if self._backend_is_healthy(health_url):
                log_startup("BACKEND_EXTERNAL", f"Healthy external backend on port {port}; it will not be managed or stopped")
                return True, "RUNNING (External)", 0, health_url
            proc_name = get_process_name(p_pid) or "Unknown"
            return False, "FAILED", 0, f"Cổng 8000 đang bị chiếm bởi process không xác minh được (PID {p_pid}, {proc_name}); giữ nguyên process."

        # Spawn backend
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        owner_token = uuid.uuid4().hex
        identity = f"IMS_LAUNCHER_OWNER={owner_token};IMS_LAUNCHER_ROOT={_root_fingerprint()}"
        launch_code = (
            f"__ims_identity__={identity!r}; "
            "import uvicorn; "
            "uvicorn.run('backend.app.main:app', host='127.0.0.1', port=8000)"
        )
        cmd = [
            str(self.python_exe),
            "-c", launch_code,
        ]

        with open(BACKEND_LOG, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n--- Backend Session Started at {get_current_timestamp()} ---\n")
            log_f.flush()
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                stdout=log_f,
                stderr=log_f,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        pid = proc.pid
        log_startup("BACKEND_SPAWNED", f"Backend started with PID {pid} on port {port}")
        process_state = self._make_process_state(pid, "backend", owner_token, port, health_url)
        if process_state is None:
            self._stop_spawned_child(proc)
            return False, "FAILED", 0, f"Không đọc được creation time của backend PID {pid}; process mới tạo đã được dừng an toàn."

        # Wait for health check
        healthy = False
        for _ in range(30):
            time.sleep(1)
            if proc.poll() is not None:
                break
            if get_port_listener_pid(port) == pid and self._backend_is_healthy(health_url):
                healthy = True
                break

        if healthy:
            self.managed_processes["backend"] = process_state
            log_startup("BACKEND_HEALTHY", f"Backend healthcheck passed at {health_url}")
            return True, "RUNNING", pid, health_url

        tail_lines = ""
        try:
            lines = BACKEND_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            tail_lines = "\n    ".join(lines[-8:]) if lines else "Không có chi tiết lỗi trong log."
        except Exception:
            pass

        log_startup("BACKEND_FAILED", f"Backend failed to become healthy. Log snippet:\n{tail_lines}", level="ERROR")
        self._stop_spawned_child(proc)
        return False, "FAILED", 0, f"Backend không sẵn sàng sau 30s.\n  Chi tiết:\n    {tail_lines}"

    def check_smtp_and_worker(self) -> tuple[bool, str, str]:
        host = self.env.get("SMTP_HOST", "").strip()
        port = int(self.env.get("SMTP_PORT", "587").strip() or 587)
        user = self.env.get("SMTP_USERNAME", "").strip()
        password = self.env.get("SMTP_PASSWORD", "")
        sender = self.env.get("SMTP_FROM", "").strip() or user
        use_ssl = self.env.get("SMTP_USE_SSL", "false").strip().lower() in ("1", "true", "yes")
        use_starttls = self.env.get("SMTP_USE_STARTTLS", "true").strip().lower() in ("1", "true", "yes")
        timeout = max(1.0, float(self.env.get("SMTP_TIMEOUT_SECONDS", "10").strip() or 10))

        if not host or not sender:
            log_startup("SMTP_CHECK", "SMTP is not configured. Email worker running in idle mode.")
            return True, "NOT CONFIGURED", "RUNNING (Idle - In-Process)"

        if not is_tcp_open(host, port, timeout=min(timeout, 4.0)):
            log_startup("SMTP_UNREACHABLE", f"Cannot connect to SMTP server {host}:{port}", level="WARNING")
            return True, f"CONFIGURED / UNREACHABLE (Port {port})", "RUNNING (In-Process)"

        smtp_status = "CONFIGURED / CONNECTIVITY OK"
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=timeout)
            else:
                server = smtplib.SMTP(host, port, timeout=timeout)
                if use_starttls:
                    server.starttls(context=ssl.create_default_context())

            if user and password:
                try:
                    server.login(user, password)
                    smtp_status = "CONFIGURED / AUTHENTICATED"
                except smtplib.SMTPAuthenticationError:
                    smtp_status = "CONFIGURED / AUTH FAILED"
                except Exception:
                    smtp_status = "CONFIGURED / CONNECTIVITY OK"
            server.quit()
        except Exception as exc:
            smtp_status = f"CONFIGURED / CONNECTIVITY OK (Handshake notice: {type(exc).__name__})"

        log_startup("SMTP_STATUS", f"SMTP Status: {smtp_status}")
        return True, smtp_status, "RUNNING (In-Process)"

    def start_frontend(self) -> tuple[bool, str, int, str]:
        port = 3000
        frontend_url = f"http://localhost:{port}"

        p_pid = get_port_listener_pid(port)
        if p_pid:
            saved_fe = self.state.get("frontend", {})
            is_our_frontend, _ = verify_process_ownership(p_pid, "frontend", saved_fe)
            if is_our_frontend:
                if self._frontend_is_healthy(f"http://127.0.0.1:{port}"):
                    self.managed_processes["frontend"] = saved_fe
                    log_startup("FRONTEND_REUSED", f"Managed frontend already running on PID {p_pid}")
                    return True, "RUNNING (Existing)", p_pid, frontend_url
                return False, "FAILED", 0, f"Frontend launcher-owned PID {p_pid} chiếm cổng nhưng health check không đạt."
            if self._frontend_is_healthy(f"http://127.0.0.1:{port}"):
                log_startup("FRONTEND_EXTERNAL", f"Healthy external frontend on port {port}; it will not be managed or stopped")
                return True, "RUNNING (External)", 0, frontend_url
            proc_name = get_process_name(p_pid) or "Unknown"
            return False, "FAILED", 0, f"Cổng 3000 đang bị chiếm bởi process không xác minh được (PID {p_pid}, {proc_name}); giữ nguyên process."

        # Spawn frontend
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        node_bin = shutil.which("node") or "node"
        owner_token = uuid.uuid4().hex
        identity = f"IMS_LAUNCHER_OWNER={owner_token};IMS_LAUNCHER_ROOT={_root_fingerprint()}"
        launch_code = (
            f"const __ims_identity__={json.dumps(identity)}; "
            "import('vite').then(({createServer})=>createServer({server:{host:'127.0.0.1',port:3000,strictPort:true}}).then(server=>server.listen()))"
        )
        cmd = [
            node_bin,
            "-e", launch_code,
        ]

        with open(FRONTEND_LOG, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n--- Frontend Session Started at {get_current_timestamp()} ---\n")
            log_f.flush()
            proc = subprocess.Popen(
                cmd,
                cwd=str(FRONTEND_DIR),
                stdout=log_f,
                stderr=log_f,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        pid = proc.pid
        log_startup("FRONTEND_SPAWNED", f"Frontend started with PID {pid} on port {port}")
        process_state = self._make_process_state(pid, "frontend", owner_token, port, frontend_url)
        if process_state is None:
            self._stop_spawned_child(proc)
            return False, "FAILED", 0, f"Không đọc được creation time của frontend PID {pid}; process mới tạo đã được dừng an toàn."

        # Wait for frontend readiness
        healthy = False
        for _ in range(30):
            time.sleep(1)
            if proc.poll() is not None:
                break
            if get_port_listener_pid(port) == pid and self._frontend_is_healthy(f"http://127.0.0.1:{port}"):
                healthy = True
                break

        if healthy:
            self.managed_processes["frontend"] = process_state
            log_startup("FRONTEND_HEALTHY", f"Frontend healthcheck passed at {frontend_url}")
            return True, "RUNNING", pid, frontend_url

        tail_lines = ""
        try:
            lines = FRONTEND_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            tail_lines = "\n    ".join(lines[-8:]) if lines else "Không có chi tiết lỗi trong log."
        except Exception:
            pass

        log_startup("FRONTEND_FAILED", f"Frontend failed to become healthy. Log snippet:\n{tail_lines}", level="ERROR")
        self._stop_spawned_child(proc)
        return False, "FAILED", 0, f"Frontend không sẵn sàng sau 30s.\n  Chi tiết:\n    {tail_lines}"

    def run_startup(self) -> int:
        self.print_banner()

        # Step 1: Check environment (.env precheck & dependencies)
        sys.stdout.write("[1/5] Checking environment...     ")
        sys.stdout.flush()
        env_ok, env_msg = self.check_environment()
        if not env_ok:
            print("FAILED")
            print("=========================================")
            print(" ERROR: ENVIRONMENT CHECK FAILED")
            print("=========================================")
            print(env_msg)
            print(f"Log: {STARTUP_LOG}")
            print("=========================================")
            return 1
        print("OK")

        # Step 2: Check / Start MySQL
        sys.stdout.write("[2/5] Starting MySQL...           ")
        sys.stdout.flush()
        mysql_ok, mysql_status_badge, mysql_detail = self.check_and_start_mysql()
        if not mysql_ok:
            print("FAILED")
            print("=========================================")
            print(" ERROR: DATABASE INITIALIZATION FAILED")
            print("=========================================")
            print(mysql_detail)
            print(f"Log: {STARTUP_LOG}")
            print("=========================================")
            return 1
        print("OK")
        self.state["mysql"] = {"status": mysql_status_badge}

        # Step 3: Start Backend
        sys.stdout.write("[3/5] Starting Backend...         ")
        sys.stdout.flush()
        be_ok, be_badge, be_pid, be_info = self.start_backend()
        if not be_ok:
            print("FAILED")
            print("=========================================")
            print(" ERROR: BACKEND STARTUP FAILED")
            print("=========================================")
            print(be_info)
            print(f"Log: {BACKEND_LOG}")
            print("=========================================")
            return 1
        print("OK")
        self._persist_managed_processes()

        # Step 4: Check SMTP & Worker
        sys.stdout.write("[4/5] Checking SMTP/Worker...     ")
        sys.stdout.flush()
        _, smtp_badge, worker_badge = self.check_smtp_and_worker()
        print("OK")
        self.state["smtp"] = {"status": smtp_badge}
        self.state["worker"] = {"status": worker_badge}

        # Step 5: Start Frontend
        sys.stdout.write("[5/5] Starting Frontend...        ")
        sys.stdout.flush()
        fe_ok, fe_badge, fe_pid, fe_info = self.start_frontend()
        if not fe_ok:
            print("FAILED")
            print("=========================================")
            print(" ERROR: FRONTEND STARTUP FAILED")
            print("=========================================")
            print(fe_info)
            print(f"Log: {FRONTEND_LOG}")
            print("=========================================")
            return 1
        print("OK")

        # Persist only processes created and verified by this launcher. External services
        # return PID 0 and are deliberately absent from the managed shutdown state.
        already_opened = self.state.get("browser_opened", False)
        new_state = {
            "state_version": OWNERSHIP_VERSION,
            "started_at": get_current_timestamp(),
            "mysql": {"status": mysql_status_badge},
            "smtp": {"status": smtp_badge},
            "worker": {"status": worker_badge},
            "browser_opened": True,
        }
        new_state.update(self.managed_processes)
        save_state(new_state)
        self.state = new_state

        # Print final formatted system status
        print("=========================================")
        print(" SYSTEM STATUS")
        print("=========================================")
        print(f"MySQL:        {mysql_status_badge}")
        print(f"Backend:      {be_badge}")
        print(f"Frontend:     {fe_badge}")
        print(f"SMTP:         {smtp_badge}")
        print(f"Email Worker: {worker_badge}")
        print("Backend:   http://127.0.0.1:8000")
        print("Frontend:  http://localhost:3000")
        print("SYSTEM READY")
        print("=========================================")

        # Auto-open browser once
        if not already_opened:
            try:
                webbrowser.open("http://localhost:3000")
                log_startup("BROWSER_OPENED", "Opened browser at http://localhost:3000")
            except Exception:
                pass

        log_startup("SYSTEM_READY", "All services started and verified healthy")
        return 0

    def run_shutdown(self) -> int:
        print("=========================================")
        print(" INTERNSHIP MANAGEMENT - SERVER SHUTDOWN")
        print("=========================================")

        state = load_state()
        fe_info = state.get("frontend")
        be_info = state.get("backend")
        pending_stop = False

        # 1. Stop Frontend
        sys.stdout.write("Stopping Frontend...              ")
        sys.stdout.flush()
        if isinstance(fe_info, dict) and isinstance(fe_info.get("pid"), int) and not isinstance(fe_info.get("pid"), bool) and fe_info["pid"] > 0:
            fe_pid = fe_info["pid"]
            if is_pid_alive(fe_pid):
                ok, reason = terminate_owned_process(fe_pid, "frontend", fe_info)
                if ok:
                    print(f"STOPPED (PID {fe_pid})")
                else:
                    print(f"SKIPPED ({reason})")
                    pending_stop = True
            else:
                print("NOT RUNNING")
        else:
            print("NOT RUNNING (Không có tiến trình trong launcher state)")

        # 2. Stop Backend
        sys.stdout.write("Stopping Backend...               ")
        sys.stdout.flush()
        if isinstance(be_info, dict) and isinstance(be_info.get("pid"), int) and not isinstance(be_info.get("pid"), bool) and be_info["pid"] > 0:
            be_pid = be_info["pid"]
            if is_pid_alive(be_pid):
                ok, reason = terminate_owned_process(be_pid, "backend", be_info)
                if ok:
                    print(f"STOPPED (PID {be_pid})")
                else:
                    print(f"SKIPPED ({reason})")
                    pending_stop = True
            else:
                print("NOT RUNNING")
        else:
            print("NOT RUNNING (Không có tiến trình trong launcher state)")

        # 3. MySQL state preserved
        print("MySQL:                            PRESERVED (Dịch vụ MySQL dùng chung không bị tắt)")

        if pending_stop:
            log_startup("SHUTDOWN_INCOMPLETE", "Unverified or unresponsive process state retained", level="WARNING")
            print("Launcher state retained so ownership can be checked again; unverified processes were preserved.")
            print("=========================================")
            print(" SHUTDOWN FINISHED - PROCESSES PRESERVED")
            print("=========================================")
        else:
            clear_state()
            log_startup("SHUTDOWN_COMPLETED", "All managed services stopped safely")
            print("=========================================")
            print(" ALL MANAGED SERVICES STOPPED SAFELY")
            print("=========================================")
        return 0


def main():
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "start"
    launcher = Launcher()

    if action in ("start", "run"):
        code = launcher.run_startup()
        sys.exit(code)
    elif action in ("stop", "shutdown", "down"):
        code = launcher.run_shutdown()
        sys.exit(code)
    else:
        print(f"Cách dùng: {Path(sys.argv[0]).name} [start|stop]")
        sys.exit(1)


if __name__ == "__main__":
    main()
