#!/usr/bin/env python3
"""
Internship Management System - One-Click Launcher & Safe Shutdown Controller.
Cross-platform compatible for Windows environments. Pure Python standard library.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
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
CONFIG_ROOT_DIR = Path(os.environ.get("IMS_CONFIG_ROOT", str(ROOT_DIR))).expanduser().resolve()
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
LOGS_DIR = ROOT_DIR / "logs"
ENV_FILE = CONFIG_ROOT_DIR / "backend" / ".env"
ENV_EXAMPLE_FILE = BACKEND_DIR / ".env.example"
VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
STATE_FILE = LOGS_DIR / "launcher_state.json"
STARTUP_LOG = LOGS_DIR / "startup.log"
BACKEND_LOG = LOGS_DIR / "backend.log"
FRONTEND_LOG = LOGS_DIR / "frontend.log"
STARTUP_LOCK_FILE = ROOT_DIR / ".launcher" / "startup.lock"


def get_current_timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize_text(text: str) -> str:
    """Mask sensitive fields like passwords, secrets, and auth tokens."""
    if not text:
        return ""
    sensitive_name = r"password|secret|token|api[_-]?key|credential|mat_khau"
    text = re.sub(rf"(?i)({sensitive_name})\s*=\s*[^\s,;]+", r"\1=******", text)
    text = re.sub(rf"(?i)(['\"](?:{sensitive_name})['\"]\s*:\s*['\"])[^'\"]+(['\"])", r"\1******\2", text)
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


def acquire_startup_lock(timeout_seconds: int = 120):
    """Serialize launcher start/stop operations so duplicate clicks cannot race."""
    STARTUP_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_file = STARTUP_LOCK_FILE.open("a+b")
    lock_file.seek(0, os.SEEK_END)
    if lock_file.tell() == 0:
        lock_file.write(b"\0")
        lock_file.flush()

    deadline = time.monotonic() + timeout_seconds
    waiting = False
    while True:
        try:
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_file, None
        except OSError:
            if not waiting:
                print("Một launcher khác đang xử lý hệ thống; đang đợi lượt...")
                waiting = True
            if time.monotonic() >= deadline:
                lock_file.close()
                return None, "Đã chờ 120 giây nhưng launcher khác vẫn chưa hoàn tất."
            time.sleep(0.25)


def release_startup_lock(lock_file) -> None:
    try:
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception as exc:
        log_startup("LIFECYCLE_LOCK_RELEASE_FAILED", sanitize_text(str(exc)), level="ERROR")
    finally:
        lock_file.close()


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


def get_remote_process_details(pid: int) -> dict | None:
    """Read a same-user Windows process' current directory and environment block."""
    if platform.system() != "Windows" or pid <= 0:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessBasicInformation(ctypes.Structure):
            _fields_ = [
                ("reserved1", ctypes.c_void_p),
                ("peb_address", ctypes.c_void_p),
                ("reserved2", ctypes.c_void_p),
                ("reserved3", ctypes.c_void_p),
                ("process_id", ctypes.c_void_p),
                ("parent_process_id", ctypes.c_void_p),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        read_process_memory = kernel32.ReadProcessMemory
        read_process_memory.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        read_process_memory.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        query_process = ntdll.NtQueryInformationProcess
        query_process.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(ProcessBasicInformation),
            wintypes.ULONG,
            ctypes.POINTER(wintypes.ULONG),
        ]
        query_process.restype = ctypes.c_long

        handle = open_process(0x0410, False, pid)  # QUERY_INFORMATION | VM_READ
        if not handle:
            return None

        def read_memory(address: int, size: int) -> bytes | None:
            buffer = ctypes.create_string_buffer(size)
            bytes_read = ctypes.c_size_t()
            ok = read_process_memory(
                handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(bytes_read)
            )
            if not ok or bytes_read.value <= 0:
                return None
            return buffer.raw[: bytes_read.value]

        try:
            info = ProcessBasicInformation()
            returned = wintypes.ULONG()
            status = query_process(
                handle,
                0,
                ctypes.byref(info),
                ctypes.sizeof(info),
                ctypes.byref(returned),
            )
            if status != 0 or not info.peb_address:
                return None

            pointer_size = ctypes.sizeof(ctypes.c_void_p)
            peb = read_memory(int(info.peb_address), 0x80)
            if not peb:
                return None
            params_offset = 0x20 if pointer_size == 8 else 0x10
            params_address = int.from_bytes(peb[params_offset : params_offset + pointer_size], "little")
            params = read_memory(params_address, 0x200)
            if not params:
                return None

            cwd_struct_offset = 0x38 if pointer_size == 8 else 0x24
            cwd_length = int.from_bytes(params[cwd_struct_offset : cwd_struct_offset + 2], "little")
            cwd_buffer_offset = cwd_struct_offset + (8 if pointer_size == 8 else 4)
            cwd_address = int.from_bytes(
                params[cwd_buffer_offset : cwd_buffer_offset + pointer_size], "little"
            )
            cwd_bytes = read_memory(cwd_address, cwd_length) if cwd_address and cwd_length else b""
            cwd = cwd_bytes.decode("utf-16-le", errors="replace") if cwd_bytes else ""

            environment_offset = 0x80 if pointer_size == 8 else 0x48
            environment_address = int.from_bytes(
                params[environment_offset : environment_offset + pointer_size], "little"
            )
            environment_bytes = read_memory(environment_address, 0x20000) if environment_address else None
            if not environment_bytes:
                return None
            environment_text = environment_bytes.decode("utf-16-le", errors="replace")
            environment = {}
            for entry in environment_text.split("\x00"):
                key, separator, value = entry.partition("=")
                if separator and key and not key.startswith("="):
                    environment[key] = value
            return {"cwd": cwd, "environment": environment}
        finally:
            close_handle(handle)
    except Exception:
        return None


def _project_root_from_cwd(cwd: str) -> Path | None:
    if not cwd:
        return None
    path = Path(cwd)
    for candidate in (path, *path.parents):
        if (candidate / "backend" / "app" / "main.py").is_file() and (candidate / "frontend" / "package.json").is_file():
            return candidate.resolve()
    return None


def _source_manifest(root: Path, service_type: str) -> dict[str, str]:
    """Fingerprint tracked runtime source while excluding local config and dependencies."""
    if service_type == "frontend":
        base = root / "frontend"
        paths = list((base / "src").rglob("*"))
        paths.extend(path for path in base.glob("*") if path.is_file())
        paths = [path for path in paths if path.is_file() and path.name not in {".env", ".env.local"}]
    elif service_type == "sandbox":
        relative_paths = (
            "backend/app/hrm_sandbox.py",
            "backend/app/hrm_storage.py",
            "backend/app/database.py",
            "backend/app/hrm_sandbox_console.html",
        )
        paths = [root / name for name in relative_paths]
    else:
        base = root / "backend" / "app"
        paths = list(base.rglob("*.py")) + list(base.rglob("*.html"))
        paths.append(root / "backend" / "requirements.txt")

    manifest = {}
    for path in paths:
        try:
            relative = path.relative_to(root).as_posix()
            manifest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        except (OSError, ValueError):
            continue
    return manifest


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


OWNERSHIP_VERSION = 3


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
    if expected_type == "frontend":
        details = get_remote_process_details(pid)
        environment = details.get("environment", {}) if details else {}
        identity_matches = (
            hmac.compare_digest(environment.get("IMS_LAUNCHER_OWNER", ""), saved_proc_info["owner_token"])
            and hmac.compare_digest(environment.get("IMS_LAUNCHER_ROOT", ""), _root_fingerprint())
        )
    else:
        identity_matches = token_marker in cmdline and root_marker in cmdline
    if not identity_matches:
        return False, "Process does not carry this launcher's ownership identity"

    if expected_type == "backend":
        is_python = Path(proc_name).name in ("python.exe", "pythonw.exe")
        if is_python and "uvicorn.run" in cmdline and ("app.main:app" in cmdline or "backend.app.main:app" in cmdline):
            return True, "Xác minh thành công backend của dự án"
        return False, f"Tiến trình PID {pid} không thuộc backend của dự án này"

    elif expected_type == "frontend":
        is_node = Path(proc_name).name == "node.exe"
        if is_node and "vite" in cmdline and "strictport" in cmdline:
            return True, "Xác minh thành công frontend của dự án"
        return False, f"Tiến trình PID {pid} không thuộc frontend của dự án này"

    elif expected_type == "sandbox":
        is_python = Path(proc_name).name in ("python.exe", "pythonw.exe")
        if is_python and "app.hrm_sandbox" in cmdline:
            return True, "Xác minh thành công HRM Sandbox của dự án"
        return False, f"Tiến trình PID {pid} không thuộc HRM Sandbox của dự án này"

    return False, f"Loại tiến trình không xác định: {expected_type}"



def _launcher_owner_token_from_process(pid: int) -> str | None:
    """Return a valid owner token embedded in a process created by this source tree."""
    cmdline = get_process_cmdline(pid).lower()
    if f"ims_launcher_root={_root_fingerprint()}" not in cmdline:
        return None
    match = re.search(r"ims_launcher_owner=([0-9a-f]{32})", cmdline)
    return match.group(1) if match else None

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
        self.vite_bin = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        if not self.vite_bin.is_file():
            self.vite_bin = CONFIG_ROOT_DIR / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
        self.managed_processes: dict[str, dict] = {}

    @staticmethod
    def _base_child_environment() -> dict[str, str]:
        windows_runtime_keys = {
            "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH", "PATHEXT",
            "COMSPEC", "PROGRAMDATA", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
        }
        return {key: value for key, value in os.environ.items() if key.upper() in windows_runtime_keys}

    def _backend_environment(self) -> dict[str, str]:
        environment = self._base_child_environment()
        environment.update(self.env)
        environment["IMS_SKIP_STARTUP_DB_INIT"] = "1"
        environment["PYTHONPATH"] = str(BACKEND_DIR)
        return environment

    def _sandbox_environment(self) -> dict[str, str]:
        environment = self._base_child_environment()
        for key in (
            "HRM_SANDBOX_API_KEY", "HRM_SANDBOX_ADMIN_API_KEY", "HRM_SANDBOX_DATABASE_PATH",
            "HRM_SANDBOX_DATABASE_BACKEND", "HRM_SANDBOX_MYSQL_HOST", "HRM_SANDBOX_MYSQL_PORT",
            "HRM_SANDBOX_MYSQL_USER", "HRM_SANDBOX_MYSQL_PASSWORD", "HRM_SANDBOX_MYSQL_DATABASE",
            "HRM_SANDBOX_PORT",
        ):
            if key in self.env:
                environment[key] = self.env[key]
        environment["HRM_SANDBOX_SKIP_STARTUP_DB_INIT"] = "1"
        environment["PYTHONPATH"] = str(BACKEND_DIR)
        return environment

    def _frontend_environment(self, owner_token: str) -> dict[str, str]:
        environment = self._base_child_environment()
        environment["VITE_API_PROXY_TARGET"] = self.env.get(
            "VITE_API_PROXY_TARGET", "http://127.0.0.1:8000"
        )
        environment["IMS_LAUNCHER_OWNER"] = owner_token
        environment["IMS_LAUNCHER_ROOT"] = _root_fingerprint()
        return environment

    def _process_matches_service(self, pid: int, service_type: str) -> bool:
        details = get_remote_process_details(pid)
        if not details:
            return False
        process_root = _project_root_from_cwd(details.get("cwd", ""))
        if not process_root:
            return False
        if _source_manifest(process_root, service_type) != _source_manifest(ROOT_DIR, service_type):
            return False

        command = get_process_cmdline(pid).casefold()
        process_name = Path(get_process_name(pid)).name.casefold()
        environment = details.get("environment", {})
        if service_type == "frontend":
            if process_name != "node.exe" or not ("vite" in command or "createserver" in command):
                return False
            actual_target = environment.get("VITE_API_PROXY_TARGET", "http://127.0.0.1:8000")
            expected_target = self.env.get("VITE_API_PROXY_TARGET", "http://127.0.0.1:8000")
            return actual_target.rstrip("/") == expected_target.rstrip("/")

        if process_name not in ("python.exe", "pythonw.exe"):
            return False
        if service_type == "sandbox":
            if "app.hrm_sandbox" not in command:
                return False
            comparisons = (
                ("HRM_SANDBOX_DATABASE_BACKEND", "mysql"),
                ("HRM_SANDBOX_MYSQL_HOST", self.env.get("HRM_SANDBOX_MYSQL_HOST", "127.0.0.1")),
                ("HRM_SANDBOX_MYSQL_PORT", self.env.get("HRM_SANDBOX_MYSQL_PORT", "3306")),
                ("HRM_SANDBOX_MYSQL_DATABASE", self.env.get("HRM_SANDBOX_MYSQL_DATABASE", "")),
                ("HRM_SANDBOX_API_KEY", self.env.get("HRM_SANDBOX_API_KEY", "")),
                ("HRM_SANDBOX_ADMIN_API_KEY", self.env.get("HRM_SANDBOX_ADMIN_API_KEY", "")),
            )
        else:
            if "uvicorn" not in command or not ("app.main:app" in command or "backend.app.main:app" in command):
                return False
            comparisons = (
                ("IMS_DATABASE_BACKEND", self.env.get("IMS_DATABASE_BACKEND", "mysql")),
                ("MYSQL_HOST", self.env.get("MYSQL_HOST", "127.0.0.1")),
                ("MYSQL_PORT", self.env.get("MYSQL_PORT", "3306")),
                ("MYSQL_DATABASE", self.env.get("MYSQL_DATABASE", "")),
                ("HRM_SANDBOX_BASE_URL", self.env.get("HRM_SANDBOX_BASE_URL", "")),
                ("HRM_SANDBOX_API_KEY", self.env.get("HRM_SANDBOX_API_KEY", "")),
                ("SMTP_HOST", self.env.get("SMTP_HOST", "")),
                ("SMTP_USERNAME", self.env.get("SMTP_USERNAME", "")),
                ("SMTP_PASSWORD", self.env.get("SMTP_PASSWORD", "")),
                ("EMAIL_WORKER_INTERVAL_SECONDS", self.env.get("EMAIL_WORKER_INTERVAL_SECONDS", "5")),
            )
            if environment.get("IMS_DISABLE_EMAIL_WORKER", "0") == "1":
                return False

        return all(
            hmac.compare_digest(environment.get(key, ""), expected)
            for key, expected in comparisons
        )

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
                if not (
                    payload.get("system") == "Hệ thống Quản lý Thực tập sinh"
                    and payload.get("status") == "Online"
                ):
                    return False
            with urllib.request.urlopen(url.rstrip("/") + "/openapi.json", timeout=3) as response:
                if response.status != 200:
                    return False
                paths = json.loads(response.read().decode("utf-8")).get("paths", {})
            path_names = tuple(paths)
            required_markers = (
                ("/api/meetings",),
                ("/api/integrations/hrm",),
                ("/api/admin/backups",),
                ("/api/audit-logs",),
                ("attendance",),
            )
            return all(any(any(marker in path for marker in markers) for path in path_names) for markers in required_markers)
        except Exception:
            return False

    @staticmethod
    def _sandbox_health(url: str, api_key: str) -> dict | None:
        try:
            request = urllib.request.Request(
                url.rstrip("/") + "/api/v1/health",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                if response.status != 200:
                    return None
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

    def _sandbox_is_healthy(self, url: str) -> bool:
        service_key = self.env.get("HRM_SANDBOX_API_KEY", "")
        admin_key = self.env.get("HRM_SANDBOX_ADMIN_API_KEY", "")
        expected_database = self.env.get("HRM_SANDBOX_MYSQL_DATABASE", "")
        if not service_key or not admin_key or hmac.compare_digest(service_key, admin_key):
            return False
        payload = self._sandbox_health(url, service_key)
        if not payload:
            return False
        if payload.get("status") != "ok" or payload.get("database_backend") != "mysql":
            return False
        if payload.get("database_name") != expected_database or not isinstance(payload.get("employee_count"), int):
            return False
        return self._sandbox_health(url, admin_key) is not None

    @staticmethod
    def _is_spawned_backend_process(pid: int, owner_token: str) -> bool:
        """Recognize Uvicorn's Windows child process using this launch's token."""
        if pid <= 0 or not is_pid_alive(pid):
            return False
        cmdline = get_process_cmdline(pid).lower()
        process_name = Path(get_process_name(pid)).name.lower()
        return (
            process_name in ("python.exe", "pythonw.exe")
            and f"ims_launcher_owner={owner_token}" in cmdline
            and f"ims_launcher_root={_root_fingerprint()}" in cmdline
            and "uvicorn.run" in cmdline
            and "backend.app.main:app" in cmdline
        )

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
        if not self.vite_bin.is_file():
            allow_install = "--install" in sys.argv or "--setup" in sys.argv
            if allow_install:
                self.vite_bin = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        if not self.vite_bin.is_file():
            allow_install = "--install" in sys.argv or "--setup" in sys.argv
            if allow_install:
                print("  -> Đang cài đặt gói thư viện Frontend ban đầu (npm install)...")
                res = subprocess.run(
                    ["npm.cmd", "install", "--no-audit", "--no-fund"],
                    cwd=str(FRONTEND_DIR), capture_output=True, text=True,
                    env=self._frontend_environment(""),
                )
                if res.returncode != 0:
                    return False, f"Cài đặt thư viện frontend thất bại: {res.stderr.strip() or res.stdout.strip()}"
            else:
                return False, (
                    "Thư viện frontend chưa được cài đặt (thiếu frontend\\node_modules).\n"
                    "  Vui lòng chạy: cd frontend && npm install\n"
                    "  Hoặc chạy launcher với cờ '--install' để tự động cài đặt."
                )

        if self.env.get("IMS_DATABASE_BACKEND", "mysql").strip().lower() != "mysql":
            return False, "IMS_DATABASE_BACKEND phải là mysql. Launcher không chuyển môi trường sang SQLite."
        if self.env.get("HRM_SANDBOX_DATABASE_BACKEND", "").strip().lower() != "mysql":
            return False, "HRM_SANDBOX_DATABASE_BACKEND phải là mysql. Launcher không chuyển Sandbox sang SQLite."
        service_key = self.env.get("HRM_SANDBOX_API_KEY", "")
        admin_key = self.env.get("HRM_SANDBOX_ADMIN_API_KEY", "")
        if len(service_key) < 32 or len(admin_key) < 32 or hmac.compare_digest(service_key, admin_key):
            return False, "Cấu hình HRM Sandbox cần service key và admin key riêng, hợp lệ trong backend\\.env."
        if self.env.get("IMS_DISABLE_EMAIL_WORKER", "0").strip() == "1":
            return False, "IMS_DISABLE_EMAIL_WORKER=1; bật worker bằng cấu hình local trước khi khởi động."
        if self.env.get("VITE_API_PROXY_TARGET", "http://127.0.0.1:8000").rstrip("/") != "http://127.0.0.1:8000":
            return False, "VITE_API_PROXY_TARGET phải trỏ tới backend local http://127.0.0.1:8000."
        required_mysql_values = (
            "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE", "HRM_SANDBOX_MYSQL_USER",
            "HRM_SANDBOX_MYSQL_PASSWORD", "HRM_SANDBOX_MYSQL_DATABASE",
        )
        missing_mysql = [key for key in required_mysql_values if not self.env.get(key, "").strip()]
        if missing_mysql:
            return False, "Thiếu cấu hình MySQL local: " + ", ".join(missing_mysql)

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

        sandbox_host = self.env.get("HRM_SANDBOX_MYSQL_HOST", "127.0.0.1").strip()
        sandbox_port = int(self.env.get("HRM_SANDBOX_MYSQL_PORT", "3306").strip() or 3306)
        sandbox_user = self.env.get("HRM_SANDBOX_MYSQL_USER", "").strip()
        sandbox_password = self.env.get("HRM_SANDBOX_MYSQL_PASSWORD", "")
        sandbox_database = self.env.get("HRM_SANDBOX_MYSQL_DATABASE", "").strip()
        try:
            import pymysql
            connection = pymysql.connect(
                host=sandbox_host,
                port=sandbox_port,
                user=sandbox_user,
                password=sandbox_password,
                database=sandbox_database,
                charset="utf8mb4",
                connect_timeout=5,
                autocommit=False,
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            connection.close()
            log_startup("HRM_MYSQL_CONNECTED", f"Connected to HRM Sandbox MySQL database '{sandbox_database}'")
            return True, "CONNECTED", f"IMS MySQL {database}; HRM Sandbox MySQL {sandbox_database}"
        except Exception as exc:
            code = getattr(exc, "args", [None])[0] if hasattr(exc, "args") else None
            if code == 1049:
                detail = f"HRM Sandbox database '{sandbox_database}' không tồn tại. Launcher không tự tạo schema."
            elif code in (1045, 1698):
                detail = "Xác thực MySQL HRM Sandbox thất bại; kiểm tra HRM_SANDBOX_MYSQL_USER/PASSWORD trong backend\\.env."
            else:
                detail = f"Không thể kết nối HRM Sandbox MySQL '{sandbox_database}': {type(exc).__name__}."
            log_startup("HRM_MYSQL_CONNECT_ERROR", detail, level="ERROR")
            return False, "FAILED", detail

    def start_sandbox(self) -> tuple[bool, str, int, str]:
        port = int(self.env.get("HRM_SANDBOX_PORT", "8100").strip() or 8100)
        sandbox_url = self.env.get("HRM_SANDBOX_BASE_URL", f"http://127.0.0.1:{port}").rstrip("/")
        if port != 8100 or sandbox_url != f"http://127.0.0.1:{port}":
            return False, "FAILED", 0, "HRM Sandbox phải dùng endpoint loopback và cổng 8100 đã cấu hình."

        p_pid = get_port_listener_pid(port)
        if p_pid:
            saved = self.state.get("sandbox", {})
            is_ours, _ = verify_process_ownership(p_pid, "sandbox", saved)
            if is_ours:
                if self._sandbox_is_healthy(sandbox_url) and self._process_matches_service(p_pid, "sandbox"):
                    self.managed_processes["sandbox"] = saved
                    log_startup("SANDBOX_REUSED", f"Managed HRM Sandbox already running on PID {p_pid}")
                    return True, "RUNNING (Existing)", p_pid, sandbox_url
                return False, "FAILED", 0, f"HRM Sandbox launcher-owned PID {p_pid} không khớp source/config hiện tại hoặc health check thất bại."
            if self._sandbox_is_healthy(sandbox_url) and self._process_matches_service(p_pid, "sandbox"):
                owner_token = _launcher_owner_token_from_process(p_pid)
                process_state = self._make_process_state(p_pid, "sandbox", owner_token, port, sandbox_url) if owner_token else None
                if process_state:
                    self.managed_processes["sandbox"] = process_state
                    log_startup("SANDBOX_ADOPTED", f"Adopted verified launcher-owned Sandbox PID {p_pid}")
                    return True, "RUNNING (Managed Existing)", p_pid, sandbox_url
                log_startup("SANDBOX_EXTERNAL", f"Verified HRM Sandbox on port {port}; it will not be managed or stopped")
                return True, "RUNNING (Verified External)", 0, sandbox_url
            proc_name = get_process_name(p_pid) or "Unknown"
            return False, "FAILED", 0, f"Cổng HRM Sandbox {port} đang do PID {p_pid} ({proc_name}) chiếm; source/database/key chưa xác minh khớp, giữ nguyên process."

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        owner_token = uuid.uuid4().hex
        identity = f"IMS_LAUNCHER_OWNER={owner_token};IMS_LAUNCHER_ROOT={_root_fingerprint()}"
        launch_code = (
            f"__ims_identity__={identity!r}; import runpy; "
            "runpy.run_module('app.hrm_sandbox', run_name='__main__')"
        )
        cmd = [str(self.python_exe), "-c", launch_code]
        with open(BACKEND_LOG, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n--- HRM Sandbox Session Started at {get_current_timestamp()} ---\n")
            log_f.flush()
            proc = subprocess.Popen(
                cmd,
                cwd=str(BACKEND_DIR),
                env=self._sandbox_environment(),
                stdout=log_f,
                stderr=log_f,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        pid = proc.pid
        process_state = self._make_process_state(pid, "sandbox", owner_token, port, sandbox_url)
        if process_state is None:
            self._stop_spawned_child(proc)
            return False, "FAILED", 0, f"Không đọc được creation time của HRM Sandbox PID {pid}; process mới tạo đã được dừng an toàn."

        for _ in range(30):
            time.sleep(1)
            if proc.poll() is not None:
                break
            listener_pid = get_port_listener_pid(port)
            if (
                listener_pid == pid
                and self._sandbox_is_healthy(sandbox_url)
                and self._process_matches_service(listener_pid, "sandbox")
            ):
                self.managed_processes["sandbox"] = process_state
                log_startup("SANDBOX_HEALTHY", f"HRM Sandbox healthcheck passed at {sandbox_url}")
                return True, "RUNNING", pid, sandbox_url

        tail_lines = ""
        try:
            lines = BACKEND_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            tail_lines = "\n    ".join(lines[-10:]) if lines else "Không có chi tiết lỗi trong log."
        except Exception:
            pass
        tail_lines = sanitize_text(tail_lines)
        log_startup("SANDBOX_FAILED", f"HRM Sandbox failed to become healthy. Log snippet:\n{tail_lines}", level="ERROR")
        self._stop_spawned_child(proc)
        return False, "FAILED", 0, f"HRM Sandbox không sẵn sàng sau 30s.\n  Chi tiết:\n    {tail_lines}"

    def start_backend(self) -> tuple[bool, str, int, str]:
        port = 8000
        health_url = f"http://127.0.0.1:{port}/"

        p_pid = get_port_listener_pid(port)
        if p_pid:
            saved_be = self.state.get("backend", {})
            is_our_backend, _ = verify_process_ownership(p_pid, "backend", saved_be)
            saved_parent_pid = saved_be.get("pid") if isinstance(saved_be, dict) else None
            parent_is_ours = (
                isinstance(saved_parent_pid, int)
                and not isinstance(saved_parent_pid, bool)
                and saved_parent_pid > 0
                and verify_process_ownership(saved_parent_pid, "backend", saved_be)[0]
            )
            is_our_backend_child = (
                not is_our_backend
                and parent_is_ours
                and self._is_spawned_backend_process(p_pid, saved_be.get("owner_token", ""))
            )
            if is_our_backend or is_our_backend_child:
                if self._backend_is_healthy(health_url) and self._process_matches_service(p_pid, "backend"):
                    self.managed_processes["backend"] = saved_be
                    log_startup("BACKEND_REUSED", f"Managed backend already running on PID {p_pid}")
                    return True, "RUNNING (Existing)", p_pid, health_url
                return False, "FAILED", 0, f"Backend launcher-owned PID {p_pid} không khớp source/database/SMTP hiện tại hoặc health check thất bại."
            if self._backend_is_healthy(health_url) and self._process_matches_service(p_pid, "backend"):
                owner_token = _launcher_owner_token_from_process(p_pid)
                process_state = self._make_process_state(p_pid, "backend", owner_token, port, health_url) if owner_token else None
                if process_state:
                    self.managed_processes["backend"] = process_state
                    log_startup("BACKEND_ADOPTED", f"Adopted verified launcher-owned backend PID {p_pid}")
                    return True, "RUNNING (Managed Existing)", p_pid, health_url
                log_startup("BACKEND_EXTERNAL", f"Verified external backend on port {port}; it will not be managed or stopped")
                return True, "RUNNING (Verified External)", 0, health_url
            proc_name = get_process_name(p_pid) or "Unknown"
            return False, "FAILED", 0, f"Cổng 8000 đang bị PID {p_pid} ({proc_name}) chiếm; source/database/SMTP chưa xác minh khớp, giữ nguyên process."

        # Spawn backend
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        owner_token = uuid.uuid4().hex
        identity = f"IMS_LAUNCHER_OWNER={owner_token};IMS_LAUNCHER_ROOT={_root_fingerprint()}"
        launch_code = (
            f"__ims_identity__={identity!r}; import uvicorn; "
            "uvicorn.run('app.main:app', host='127.0.0.1', port=8000, log_level='warning')"
        )
        cmd = [str(self.python_exe), "-c", launch_code]

        with open(BACKEND_LOG, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n--- Backend Session Started at {get_current_timestamp()} ---\n")
            log_f.flush()
            proc = subprocess.Popen(
                cmd,
                cwd=str(BACKEND_DIR),
                env=self._backend_environment(),
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
            listener_pid = get_port_listener_pid(port)
            owns_listener = (
                listener_pid == pid
                or self._is_spawned_backend_process(listener_pid or 0, owner_token)
            )
            if owns_listener and self._backend_is_healthy(health_url) and self._process_matches_service(listener_pid or pid, "backend"):
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
        tail_lines = sanitize_text(tail_lines)

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
            log_startup("SMTP_CHECK", "SMTP is not configured; email worker cannot deliver queued mail.", level="ERROR")
            return False, "ERROR (NOT CONFIGURED)", "NOT READY"

        if not is_tcp_open(host, port, timeout=min(timeout, 4.0)):
            log_startup("SMTP_UNREACHABLE", f"Cannot connect to SMTP server {host}:{port}", level="WARNING")
            return False, f"ERROR (UNREACHABLE, port {port})", "NOT READY"

        smtp_status = "CONNECTED"
        server = None
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=timeout)
            else:
                server = smtplib.SMTP(host, port, timeout=timeout)
                if use_starttls:
                    server.starttls(context=ssl.create_default_context())

            if user and password:
                server.login(user, password)
                smtp_status = "CONNECTED / AUTHENTICATED"
            elif user or password:
                raise ValueError("SMTP username/password must both be configured")
            server.quit()
        except Exception as exc:
            try:
                server.close()
            except Exception:
                pass
            smtp_status = f"ERROR ({type(exc).__name__})"
            log_startup("SMTP_AUTH_FAILED", f"SMTP check failed ({type(exc).__name__})", level="ERROR")
            return False, smtp_status, "NOT READY"

        log_startup("SMTP_STATUS", f"SMTP Status: {smtp_status}")
        return True, smtp_status, "RUNNING (In-Process; no test email sent)"

    def start_frontend(self) -> tuple[bool, str, int, str]:
        port = 3000
        frontend_url = f"http://localhost:{port}"

        p_pid = get_port_listener_pid(port)
        if p_pid:
            saved_fe = self.state.get("frontend", {})
            is_our_frontend, _ = verify_process_ownership(p_pid, "frontend", saved_fe)
            if is_our_frontend:
                if self._frontend_is_healthy(f"http://127.0.0.1:{port}") and self._process_matches_service(p_pid, "frontend"):
                    self.managed_processes["frontend"] = saved_fe
                    log_startup("FRONTEND_REUSED", f"Managed frontend already running on PID {p_pid}")
                    return True, "RUNNING (Existing)", p_pid, frontend_url
                return False, "FAILED", 0, f"Frontend launcher-owned PID {p_pid} không khớp source/API URL hiện tại hoặc health check thất bại."
            if self._frontend_is_healthy(f"http://127.0.0.1:{port}") and self._process_matches_service(p_pid, "frontend"):
                log_startup("FRONTEND_EXTERNAL", f"Verified external frontend on port {port}; it will not be managed or stopped")
                return True, "RUNNING (Verified External)", 0, frontend_url
            proc_name = get_process_name(p_pid) or "Unknown"
            return False, "FAILED", 0, f"Cổng 3000 đang bị PID {p_pid} ({proc_name}) chiếm; source/API URL chưa xác minh khớp, giữ nguyên process."

        # Spawn frontend
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        node_bin = shutil.which("node") or "node"
        owner_token = uuid.uuid4().hex
        cmd = [
            node_bin,
            str(self.vite_bin),
            "--config", str(FRONTEND_DIR / "vite.config.js"),
            "--host", "127.0.0.1", "--port", str(port), "--strictPort",
        ]

        with open(FRONTEND_LOG, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n--- Frontend Session Started at {get_current_timestamp()} ---\n")
            log_f.flush()
            proc = subprocess.Popen(
                cmd,
                cwd=str(FRONTEND_DIR),
                env=self._frontend_environment(owner_token),
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
            if (
                get_port_listener_pid(port) == pid
                and self._frontend_is_healthy(f"http://127.0.0.1:{port}")
                and self._process_matches_service(pid, "frontend")
            ):
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
        tail_lines = sanitize_text(tail_lines)

        log_startup("FRONTEND_FAILED", f"Frontend failed to become healthy. Log snippet:\n{tail_lines}", level="ERROR")
        self._stop_spawned_child(proc)
        return False, "FAILED", 0, f"Frontend không sẵn sàng sau 30s.\n  Chi tiết:\n    {tail_lines}"

    def run_startup(self) -> int:
        try:
            lock_file, lock_error = acquire_startup_lock()
        except Exception as exc:
            detail = sanitize_text(str(exc))
            log_startup("STARTUP_LOCK_FAILED", detail, level="ERROR")
            print("Không thể tạo khóa khởi động hệ thống.")
            print(detail)
            return 1
        if lock_file is None:
            log_startup("STARTUP_LOCK_TIMEOUT", lock_error, level="ERROR")
            print(lock_error)
            return 1

        try:
            # A launcher that waited for another startup must read its newly saved
            # process ownership state before deciding whether to reuse the services.
            self.state = load_state()
            return self._run_startup_locked()
        finally:
            release_startup_lock(lock_file)

    def _run_startup_locked(self) -> int:
        self.print_banner()

        # Step 1: Check environment (.env precheck & dependencies)
        sys.stdout.write("[1/6] Checking environment...     ")
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

        # Step 2: Verify both MySQL schemas using SELECT only.
        sys.stdout.write("[2/6] Checking MySQL...            ")
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

        # Step 3: Authenticate with the configured SMTP relay without sending a message.
        sys.stdout.write("[3/6] Checking SMTP...             ")
        sys.stdout.flush()
        smtp_ok, smtp_badge, worker_badge = self.check_smtp_and_worker()
        if not smtp_ok:
            print("FAILED")
            print("=========================================")
            print(" ERROR: SMTP CHECK FAILED")
            print("=========================================")
            print(smtp_badge)
            print(f"Log: {STARTUP_LOG}")
            print("=========================================")
            return 1
        print("OK")
        self.state["smtp"] = {"status": smtp_badge}

        # Step 4: Verify or start Sandbox on the configured local MySQL schema.
        sys.stdout.write("[4/6] Starting HRM Sandbox...     ")
        sys.stdout.flush()
        sandbox_ok, sandbox_badge, sandbox_pid, sandbox_url = self.start_sandbox()
        if not sandbox_ok:
            print("FAILED")
            print("=========================================")
            print(" ERROR: HRM SANDBOX STARTUP FAILED")
            print("=========================================")
            print(sandbox_url)
            print(f"Log: {BACKEND_LOG}")
            print("=========================================")
            return 1
        print("OK")
        self.state["sandbox"] = {"status": sandbox_badge, "url": sandbox_url}
        self._persist_managed_processes()

        # Step 5: Start backend only after both MySQL and Sandbox are verified.
        sys.stdout.write("[5/6] Starting Backend...         ")
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
        self.state["worker"] = {"status": worker_badge}
        self._persist_managed_processes()

        # Step 6: Start Frontend last so all proxied API endpoints are already ready.
        sys.stdout.write("[6/6] Starting Frontend...        ")
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
            "sandbox": {"status": sandbox_badge, "url": sandbox_url},
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
        print(f"HRM Sandbox:  {sandbox_badge} ({sandbox_url})")
        print("IMS ↔ Sandbox: CONNECTED (service/admin credentials verified)")
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
        try:
            lock_file, lock_error = acquire_startup_lock()
        except Exception as exc:
            detail = sanitize_text(str(exc))
            log_startup("SHUTDOWN_LOCK_FAILED", detail, level="ERROR")
            print("Không thể tạo khóa dừng hệ thống.")
            print(detail)
            return 1
        if lock_file is None:
            log_startup("SHUTDOWN_LOCK_TIMEOUT", lock_error, level="ERROR")
            print(lock_error)
            return 1

        try:
            return self._run_shutdown_locked()
        finally:
            release_startup_lock(lock_file)

    def _run_shutdown_locked(self) -> int:
        print("=========================================")
        print(" INTERNSHIP MANAGEMENT - SERVER SHUTDOWN")
        print("=========================================")

        state = load_state()
        fe_info = state.get("frontend")
        be_info = state.get("backend")
        sandbox_info = state.get("sandbox")
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

        # 3. Stop HRM Sandbox only when this launcher's ownership record matches.
        sys.stdout.write("Stopping HRM Sandbox...          ")
        sys.stdout.flush()
        if isinstance(sandbox_info, dict) and isinstance(sandbox_info.get("pid"), int) and not isinstance(sandbox_info.get("pid"), bool) and sandbox_info["pid"] > 0:
            sandbox_pid = sandbox_info["pid"]
            if is_pid_alive(sandbox_pid):
                ok, reason = terminate_owned_process(sandbox_pid, "sandbox", sandbox_info)
                if ok:
                    print(f"STOPPED (PID {sandbox_pid})")
                else:
                    print(f"SKIPPED ({reason})")
                    pending_stop = True
            else:
                print("NOT RUNNING")
        else:
            print("PRESERVED (Sandbox không do launcher này quản lý)")

        # 4. MySQL state preserved
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
