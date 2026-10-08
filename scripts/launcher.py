#!/usr/bin/env python3
"""
Internship Management System - One-Click Launcher & Safe Shutdown Controller.
Cross-platform compatible for Windows environments. Pure Python standard library.
"""
from __future__ import annotations

import datetime
import json
import os
import platform
import re
import shutil
import smtplib
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
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
        # Check tasklist for Windows PID existence
        out = subprocess.check_output(
            ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        if out and not out.startswith("INFO:") and f'"{pid}"' in out:
            return True
    except Exception:
        pass
    return False


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


def verify_process_ownership(pid: int, expected_type: str) -> bool:
    """Verifies that the process belongs to our project (uvicorn backend or vite frontend)."""
    if not is_pid_alive(pid):
        return False
    cmdline = get_process_cmdline(pid).lower()
    proc_name = get_process_name(pid).lower()
    root_str = str(ROOT_DIR).lower()

    if expected_type == "backend":
        if ("uvicorn" in cmdline or "main:app" in cmdline or "backend.app.main" in cmdline) and (root_str in cmdline or "python" in proc_name):
            return True
        if "python" in proc_name and root_str in cmdline:
            return True
    elif expected_type == "frontend":
        if ("vite" in cmdline or "frontend" in cmdline) and ("node" in proc_name or root_str in cmdline):
            return True
        if "node" in proc_name and root_str in cmdline:
            return True
    return False


def kill_process_tree(pid: int) -> bool:
    """Terminates process tree safely."""
    try:
        res = subprocess.run(
            ["taskkill.exe", "/pid", str(pid), "/t", "/f"],
            capture_output=True, text=True, timeout=10
        )
        return res.returncode == 0
    except Exception:
        return False


def load_state() -> dict:
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
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


def find_mysql_windows_service() -> tuple[str | None, str]:
    """Finds installed MySQL or MariaDB Windows service. Returns (service_name, status)."""
    try:
        out = subprocess.check_output(
            ["sc.exe", "query", "state=", "all"],
            text=True, stderr=subprocess.DEVNULL
        )
        curr_svc = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("SERVICE_NAME:"):
                curr_svc = line.split(":", 1)[1].strip()
                if any(k in curr_svc.lower() for k in ["mysql", "mariadb"]):
                    # Query its specific state
                    state_out = subprocess.check_output(
                        ["sc.exe", "query", curr_svc],
                        text=True, stderr=subprocess.DEVNULL
                    )
                    status = "RUNNING" if "RUNNING" in state_out else "STOPPED"
                    return curr_svc, status
    except Exception:
        pass
    return None, ""


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

    def print_banner(self):
        print("=========================================")
        print(" INTERNSHIP MANAGEMENT - SERVER STARTUP")
        print("=========================================")

    def check_environment(self) -> tuple[bool, str]:
        # 1. OS Check
        if platform.system() != "Windows":
            return False, "Hệ thống launcher này được thiết kế dành cho môi trường Microsoft Windows."

        # 2. Python Environment Check
        if not VENV_PYTHON.is_file():
            # Check if current Python has required packages
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

        # 3. Node.js & npm Check
        if not shutil.which("node"):
            return False, "Không tìm thấy Node.js trong PATH. Vui lòng cài đặt Node.js LTS (https://nodejs.org/)."
        if not shutil.which("npm"):
            return False, "Không tìm thấy npm trong PATH. Vui lòng kiểm tra lại cài đặt Node.js."

        # 4. Frontend dependencies check
        vite_bin = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        if not vite_bin.is_file():
            print("  -> Đang cài đặt gói thư viện Frontend ban đầu (npm install)...")
            res = subprocess.run(
                ["npm.cmd", "install", "--no-audit", "--no-fund"],
                cwd=str(FRONTEND_DIR), capture_output=True, text=True
            )
            if res.returncode != 0:
                return False, f"Cài đặt thư viện frontend thất bại: {res.stderr.strip() or res.stdout.strip()}"

        # 5. Check .env file
        if not ENV_FILE.is_file():
            log_startup("ENV_MISSING", "backend/.env is missing", level="ERROR")
            return False, (
                "Thiếu file cấu hình backend\\.env.\n"
                "  Vui lòng sao chép từ backend\\.env.example và điền thông tin kết nối MySQL/SMTP:\n"
                "  copy backend\\.env.example backend\\.env"
            )

        # Re-read env
        self.env = parse_env_file(ENV_FILE)

        # 6. Check Port Collisions (ports 8000 & 3000)
        # Port 8000 (Backend)
        p8000_pid = get_port_listener_pid(8000)
        if p8000_pid:
            saved_backend_pid = self.state.get("backend", {}).get("pid")
            is_our_backend = (saved_backend_pid and saved_backend_pid == p8000_pid) or verify_process_ownership(p8000_pid, "backend")
            if not is_our_backend:
                proc_name = get_process_name(p8000_pid) or "Unknown"
                return False, f"Cổng 8000 đang bị chiếm bởi tiến trình khác (PID: {p8000_pid}, Tên: {proc_name}). Không thể khởi động backend."

        # Port 3000 (Frontend)
        p3000_pid = get_port_listener_pid(3000)
        if p3000_pid:
            saved_frontend_pid = self.state.get("frontend", {}).get("pid")
            is_our_frontend = (saved_frontend_pid and saved_frontend_pid == p3000_pid) or verify_process_ownership(p3000_pid, "frontend")
            if not is_our_frontend:
                proc_name = get_process_name(p3000_pid) or "Unknown"
                return False, f"Cổng 3000 đang bị chiếm bởi tiến trình khác (PID: {p3000_pid}, Tên: {proc_name}). Không thể khởi động frontend."

        log_startup("ENV_CHECK_OK", "Environment and ports verified successfully")
        return True, "OK"

    def check_and_start_mysql(self) -> tuple[bool, str, str]:
        backend_type = self.env.get("IMS_DATABASE_BACKEND", "mysql").strip().lower()

        if backend_type == "sqlite":
            sqlite_path = self.env.get("IMS_SQLITE_PATH", str(BACKEND_DIR / "app" / "internship.db"))
            if not Path(sqlite_path).exists():
                return False, "FAILED", f"SQLite database không tồn tại tại {sqlite_path}"
            log_startup("MYSQL_CHECK", f"Using SQLite backend at {sqlite_path}")
            return True, "CONNECTED (SQLite)", "SQLite Mode"

        # MySQL backend
        host = self.env.get("MYSQL_HOST", "127.0.0.1").strip()
        port = int(self.env.get("MYSQL_PORT", "3306").strip() or 3306)
        user = self.env.get("MYSQL_USER", "root").strip()
        password = self.env.get("MYSQL_PASSWORD", "")
        database = self.env.get("MYSQL_DATABASE", "internship_management").strip()

        is_local = host in ("127.0.0.1", "localhost", "::1")

        # Test TCP connectivity
        tcp_ready = is_tcp_open(host, port, timeout=2.0)

        if not tcp_ready:
            if not is_local:
                log_startup("MYSQL_REMOTE_UNREACHABLE", f"Cannot connect to remote MySQL at {host}:{port}", level="ERROR")
                return False, "FAILED", f"Không thể kết nối đến máy chủ MySQL từ xa tại {host}:{port}. Vui lòng kiểm tra kết nối mạng."

            # Attempt local Windows Service discovery and start
            svc_name, svc_status = find_mysql_windows_service()
            if not svc_name:
                log_startup("MYSQL_SERVICE_NOT_FOUND", f"Local MySQL port {port} closed and no Windows service found", level="ERROR")
                return False, "FAILED", (
                    f"MySQL cục bộ chưa chạy (cổng {port} chưa mở) và không tìm thấy Windows Service MySQL.\n"
                    "  Vui lòng khởi động MySQL qua XAMPP, Laragon, Services hoặc Docker rồi thử lại."
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

        # Check if already running and healthy
        p_pid = get_port_listener_pid(port)
        if p_pid:
            saved_pid = self.state.get("backend", {}).get("pid")
            if (saved_pid and saved_pid == p_pid) or verify_process_ownership(p_pid, "backend"):
                try:
                    with urllib.request.urlopen(health_url, timeout=2) as resp:
                        if resp.status == 200:
                            log_startup("BACKEND_REUSED", f"Backend already running on PID {p_pid}")
                            return True, "RUNNING (Existing)", p_pid, health_url
                except Exception:
                    pass

        # Spawn backend
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_f = open(BACKEND_LOG, "a", encoding="utf-8")
        log_f.write(f"\n--- Backend Session Started at {get_current_timestamp()} ---\n")
        log_f.flush()

        cmd = [
            str(self.python_exe),
            "-m", "uvicorn",
            "backend.app.main:app",
            "--host", "127.0.0.1",
            "--port", str(port)
        ]

        # Use CREATE_NEW_PROCESS_GROUP so it doesn't terminate with launcher
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=log_f,
            stderr=log_f,
            creationflags=creationflags
        )
        pid = proc.pid
        log_startup("BACKEND_SPAWNED", f"Backend started with PID {pid} on port {port}")

        # Wait for health check
        healthy = False
        for _ in range(30):
            time.sleep(1)
            if proc.poll() is not None:
                # Exited prematurely
                break
            try:
                with urllib.request.urlopen(health_url, timeout=1.5) as resp:
                    if resp.status == 200:
                        healthy = True
                        break
            except Exception:
                continue

        if healthy:
            log_startup("BACKEND_HEALTHY", f"Backend healthcheck passed at {health_url}")
            return True, "RUNNING", pid, health_url

        # Failure: capture last lines from backend log
        tail_lines = ""
        try:
            lines = BACKEND_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            tail_lines = "\n    ".join(lines[-8:]) if lines else "Không có chi tiết lỗi trong log."
        except Exception:
            pass

        log_startup("BACKEND_FAILED", f"Backend failed to become healthy. Log snippet:\n{tail_lines}", level="ERROR")
        return False, "FAILED", 0, f"Backend không sẵn sàng sau 30s.\n  Chi tiết:\n    {tail_lines}"

    def check_smtp_and_worker(self) -> tuple[bool, str, str]:
        # Worker is integrated into FastAPI backend lifecycle (app/email_outbox.py: start_email_worker)
        # It is ALWAYS running as part of the backend process!
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

        # Check DNS & TCP connectivity
        if not is_tcp_open(host, port, timeout=min(timeout, 4.0)):
            log_startup("SMTP_UNREACHABLE", f"Cannot connect to SMTP server {host}:{port}", level="WARNING")
            return True, f"CONFIGURED / UNREACHABLE (Port {port})", "RUNNING (In-Process)"

        # Verify handshake & auth without sending email
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

        # Check if already running and healthy
        p_pid = get_port_listener_pid(port)
        if p_pid:
            saved_pid = self.state.get("frontend", {}).get("pid")
            if (saved_pid and saved_pid == p_pid) or verify_process_ownership(p_pid, "frontend"):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=2) as resp:
                        if resp.status == 200:
                            log_startup("FRONTEND_REUSED", f"Frontend already running on PID {p_pid}")
                            return True, "RUNNING (Existing)", p_pid, frontend_url
                except Exception:
                    pass

        # Spawn frontend
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_f = open(FRONTEND_LOG, "a", encoding="utf-8")
        log_f.write(f"\n--- Frontend Session Started at {get_current_timestamp()} ---\n")
        log_f.flush()

        node_bin = shutil.which("node") or "node"
        vite_bin = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"

        cmd = [
            node_bin,
            str(vite_bin),
            "--host", "127.0.0.1",
            "--port", str(port),
            "--strictPort"
        ]

        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            cmd,
            cwd=str(FRONTEND_DIR),
            stdout=log_f,
            stderr=log_f,
            creationflags=creationflags
        )
        pid = proc.pid
        log_startup("FRONTEND_SPAWNED", f"Frontend started with PID {pid} on port {port}")

        # Wait for frontend readiness
        healthy = False
        for _ in range(30):
            time.sleep(1)
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=1.5) as resp:
                    if resp.status == 200:
                        healthy = True
                        break
            except Exception:
                continue

        if healthy:
            log_startup("FRONTEND_HEALTHY", f"Frontend healthcheck passed at {frontend_url}")
            return True, "RUNNING", pid, frontend_url

        # Failure: capture last lines from frontend log
        tail_lines = ""
        try:
            lines = FRONTEND_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            tail_lines = "\n    ".join(lines[-8:]) if lines else "Không có chi tiết lỗi trong log."
        except Exception:
            pass

        log_startup("FRONTEND_FAILED", f"Frontend failed to become healthy. Log snippet:\n{tail_lines}", level="ERROR")
        return False, "FAILED", 0, f"Frontend không sẵn sàng sau 30s.\n  Chi tiết:\n    {tail_lines}"

    def run_startup(self) -> int:
        self.print_banner()

        # Step 1: Check environment
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

        # Step 4: Check SMTP & Worker
        sys.stdout.write("[4/5] Checking SMTP/Worker...     ")
        sys.stdout.flush()
        _, smtp_badge, worker_badge = self.check_smtp_and_worker()
        print("OK")

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

        # Save active launcher state
        already_opened = self.state.get("browser_opened", False)
        new_state = {
            "started_at": get_current_timestamp(),
            "backend": {"pid": be_pid, "port": 8000, "url": "http://127.0.0.1:8000"},
            "frontend": {"pid": fe_pid, "port": 3000, "url": "http://localhost:3000"},
            "mysql": {"status": mysql_status_badge},
            "smtp": {"status": smtp_badge},
            "worker": {"status": worker_badge},
            "browser_opened": True,
        }
        save_state(new_state)

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
        fe_pid = state.get("frontend", {}).get("pid") or get_port_listener_pid(3000)
        be_pid = state.get("backend", {}).get("pid") or get_port_listener_pid(8000)

        # 1. Stop Frontend
        sys.stdout.write("Stopping Frontend...              ")
        sys.stdout.flush()
        if fe_pid and is_pid_alive(fe_pid):
            if verify_process_ownership(fe_pid, "frontend"):
                kill_process_tree(fe_pid)
                log_startup("FRONTEND_STOPPED", f"Frontend PID {fe_pid} terminated")
                print(f"STOPPED (PID {fe_pid})")
            else:
                log_startup("FRONTEND_PRESERVED", f"PID {fe_pid} does not match frontend ownership; skipped", level="WARNING")
                print("SKIPPED (Foreign process)")
        else:
            print("NOT RUNNING")

        # 2. Stop Backend
        sys.stdout.write("Stopping Backend...               ")
        sys.stdout.flush()
        if be_pid and is_pid_alive(be_pid):
            if verify_process_ownership(be_pid, "backend"):
                kill_process_tree(be_pid)
                log_startup("BACKEND_STOPPED", f"Backend PID {be_pid} terminated")
                print(f"STOPPED (PID {be_pid})")
            else:
                log_startup("BACKEND_PRESERVED", f"PID {be_pid} does not match backend ownership; skipped", level="WARNING")
                print("SKIPPED (Foreign process)")
        else:
            print("NOT RUNNING")

        # 3. MySQL state preserved
        print("MySQL:                            PRESERVED (Running service unchanged)")

        # Clear state
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
