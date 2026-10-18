"""Local-only HRM connection registry with per-source identity and DPAPI secrets."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException

from . import database
from .hrm_provider import HRMProviderError, HRMSandboxConfig, HRMSandboxProvider, get_sandbox_config

ALLOWED_PORTS = set(range(8100, 8110))
CONNECTION_TABLES = {"HRM_CONNECTIONS", "HRM_ACTIVE_CONNECTION", "HRM_CONNECTION_AUDIT"}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def validate_endpoint(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        hostname = (parsed.hostname or "").casefold()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError
        if hostname not in {"localhost", "127.0.0.1", "::1"} or port not in ALLOWED_PORTS:
            raise ValueError
        if parsed.scheme != "http":
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="Endpoint bị từ chối. Chỉ hỗ trợ HTTP localhost/127.0.0.1 tại cổng UAT 8100–8109; không nhập path, query hoặc thông tin đăng nhập trong URL.",
        ) from None
    host = "127.0.0.1" if hostname == "localhost" else ("[::1]" if hostname == "::1" else hostname)
    return f"http://{host}:{port}"


def validate_api_key(value: str) -> str:
    if not isinstance(value, str) or not 32 <= len(value) <= 256 or any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise HTTPException(status_code=422, detail="API key Sandbox phải dài 32–256 ký tự ASCII có thể in.")
    return value


class DpapiSecretVault:
    """Encrypt secrets with the current Windows user's DPAPI key; store only an opaque ref in SQL."""

    @staticmethod
    def _directory() -> Path:
        root = os.getenv("LOCALAPPDATA")
        if not root:
            raise RuntimeError("Không xác định được thư mục dữ liệu riêng của người dùng Windows.")
        path = Path(root) / "IMS-US37-UAT" / "hrm-secrets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _crypt(value: bytes, protect: bool) -> bytes:
        if os.name != "nt":
            raise RuntimeError("Kho bí mật DPAPI chỉ khả dụng trên Windows.")

        class DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        source_buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
        source = DataBlob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        target = DataBlob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if protect:
            function = crypt32.CryptProtectData
            function.argtypes = [ctypes.POINTER(DataBlob), wintypes.LPCWSTR, ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
            function.restype = wintypes.BOOL
            success = function(ctypes.byref(source), "IMS HRM Sandbox credential", None, None, None, 0, ctypes.byref(target))
        else:
            function = crypt32.CryptUnprotectData
            function.argtypes = [ctypes.POINTER(DataBlob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
            function.restype = wintypes.BOOL
            description = wintypes.LPWSTR()
            success = function(ctypes.byref(source), ctypes.byref(description), None, None, None, 0, ctypes.byref(target))
            if description:
                kernel32.LocalFree(description)
        if not success:
            raise RuntimeError("Windows không thể mở kho bí mật được bảo vệ.")
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            kernel32.LocalFree(target.pbData)

    def put(self, connection_id: str, api_key: str) -> str:
        protected = self._crypt(api_key.encode("utf-8"), True)
        target = self._directory() / f"{connection_id}.bin"
        target.write_bytes(protected)
        try:
            target.chmod(0o600)
        except OSError:
            pass
        return f"dpapi:{connection_id}"

    def get(self, reference: str | None) -> str | None:
        if not reference:
            return None
        if reference == "env:HRM_SANDBOX_API_KEY":
            return os.getenv("HRM_SANDBOX_API_KEY") or None
        if not reference.startswith("dpapi:"):
            return None
        connection_id = reference.split(":", 1)[1]
        if not connection_id.isalnum() or len(connection_id) > 32:
            return None
        secret_file = self._directory() / f"{connection_id}.bin"
        if not secret_file.is_file():
            return None
        return self._crypt(secret_file.read_bytes(), False).decode("utf-8")

    def delete(self, reference: str | None) -> None:
        if not reference or not reference.startswith("dpapi:"):
            return
        connection_id = reference.split(":", 1)[1]
        if connection_id.isalnum() and len(connection_id) <= 32:
            (self._directory() / f"{connection_id}.bin").unlink(missing_ok=True)


secret_vault = DpapiSecretVault()


def ensure_sqlite_schema(db) -> None:
    if database.DATABASE_BACKEND != "sqlite":
        return
    db.executescript("""
        CREATE TABLE IF NOT EXISTS HRM_CONNECTIONS (
            connection_id TEXT PRIMARY KEY,
            connection_name TEXT NOT NULL,
            provider_type TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            state TEXT NOT NULL,
            credential_ref TEXT,
            last_checked_at TEXT,
            last_check_message TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS HRM_ACTIVE_CONNECTION (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            active_connection_id TEXT REFERENCES HRM_CONNECTIONS(connection_id) ON DELETE RESTRICT,
            revision INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS HRM_CONNECTION_AUDIT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id TEXT NOT NULL REFERENCES HRM_CONNECTIONS(connection_id) ON DELETE RESTRICT,
            event_type TEXT NOT NULL,
            actor_user_id INTEGER NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        );
        INSERT OR IGNORE INTO HRM_ACTIVE_CONNECTION (singleton_id, active_connection_id, revision, updated_at)
        VALUES (1, NULL, 1, CURRENT_TIMESTAMP);
    """)
    db.commit()


def _tables_ready(db) -> bool:
    if database.DATABASE_BACKEND == "mysql":
        rows = db.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME IN ('HRM_CONNECTIONS', 'HRM_ACTIVE_CONNECTION', 'HRM_CONNECTION_AUDIT')"
        ).fetchall()
        # information_schema preserves the on-disk table-name casing, which may
        # be lowercase on Windows/MySQL even when migrations use uppercase SQL.
        return CONNECTION_TABLES.issubset({str(row["TABLE_NAME"]).upper() for row in rows})
    rows = db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return CONNECTION_TABLES.issubset({row["name"] for row in rows})


def _active_id(db) -> str | None:
    row = db.execute("SELECT active_connection_id FROM HRM_ACTIVE_CONNECTION WHERE singleton_id = 1").fetchone()
    return row["active_connection_id"] if row else None


def _insert_audit(db, connection_id: str, event_type: str, actor_id: int, details: str = "") -> None:
    db.execute(
        "INSERT INTO HRM_CONNECTION_AUDIT (connection_id, event_type, actor_user_id, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (connection_id, event_type, actor_id, details[:500] or None, utc_now()),
    )


def bootstrap_legacy_connection(db) -> None:
    """Import the existing environment-based sandbox as its original stable provider scope once."""
    if not _tables_ready(db):
        return
    total = int(db.execute("SELECT COUNT(*) AS total FROM HRM_CONNECTIONS").fetchone()["total"])
    if total:
        return
    config, _ = get_sandbox_config()
    if not config:
        return
    try:
        endpoint = validate_endpoint(config.base_url)
    except HTTPException:
        return
    now = utc_now()
    db.execute(
        "INSERT INTO HRM_CONNECTIONS (connection_id, connection_name, provider_type, endpoint, state, credential_ref, created_by, created_at, updated_at) "
        "VALUES ('sandbox', 'HRM Sandbox A', 'sandbox', ?, 'NOT_TESTED', 'env:HRM_SANDBOX_API_KEY', NULL, ?, ?)",
        (endpoint, now, now),
    )
    db.execute("UPDATE HRM_ACTIVE_CONNECTION SET active_connection_id = 'sandbox', revision = revision + 1, updated_at = ? WHERE singleton_id = 1", (now,))
    db.commit()


def _connection_row(db, connection_id: str):
    return db.execute("SELECT * FROM HRM_CONNECTIONS WHERE connection_id = ?", (connection_id,)).fetchone()


def make_provider(db, connection_id: str | None = None, *, require_connected: bool = True) -> tuple[HRMSandboxProvider, dict]:
    if not _tables_ready(db):
        raise HTTPException(status_code=503, detail="Thiếu schema quản lý kết nối HRM; hãy áp dụng migration master-data trên MySQL UAT.")
    bootstrap_legacy_connection(db)
    target_id = connection_id or _active_id(db)
    if not target_id:
        raise HTTPException(status_code=503, detail="Chưa chọn kết nối HRM đang sử dụng. Hãy thêm, kiểm tra rồi chọn một HRM Sandbox.")
    row = _connection_row(db, target_id)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết nối HRM đã chọn.")
    if require_connected and row["state"] != "CONNECTED":
        raise HTTPException(status_code=503, detail=f"Kết nối {row['connection_name']} đang ở trạng thái {row['state']}; hãy kiểm tra hoặc tiếp tục kết nối trước khi đồng bộ.")
    key = secret_vault.get(row["credential_ref"])
    if not key:
        raise HTTPException(status_code=503, detail=f"Kết nối {row['connection_name']} chưa có thông tin xác thực. Hãy kết nối lại và nhập API key local.")
    endpoint = validate_endpoint(row["endpoint"])
    config = HRMSandboxConfig(endpoint, key, 5.0)
    return HRMSandboxProvider(config, connection_id=str(row["connection_id"])), dict(row)


def list_connections(db) -> dict:
    if not _tables_ready(db):
        raise HTTPException(status_code=503, detail="Thiếu schema quản lý kết nối HRM; hãy áp dụng migration master-data trên MySQL UAT.")
    bootstrap_legacy_connection(db)
    active_id = _active_id(db)
    rows = db.execute(
        """SELECT c.connection_id, c.connection_name, c.provider_type, c.endpoint, c.state,
                  c.credential_ref, c.last_checked_at, c.last_check_message, c.created_at, c.updated_at,
                  (SELECT MAX(h.created_at) FROM HRM_SYNC_HISTORY h WHERE h.provider_id = c.connection_id) AS last_sync_at
           FROM HRM_CONNECTIONS c ORDER BY c.created_at, c.connection_id"""
    ).fetchall()
    return {"active_connection_id": active_id, "items": [
        {"connection_id": row["connection_id"], "connection_name": row["connection_name"],
         "provider_type": row["provider_type"], "endpoint": row["endpoint"], "state": row["state"],
         "is_active": row["connection_id"] == active_id, "has_credential": bool(row["credential_ref"]),
         "last_checked_at": row["last_checked_at"], "last_check_message": row["last_check_message"],
         "last_sync_at": row["last_sync_at"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
        for row in rows]}


async def test_configuration(connection_name: str, endpoint: str, api_key: str) -> dict:
    endpoint = validate_endpoint(endpoint)
    api_key = validate_api_key(api_key)
    if not connection_name.strip() or len(connection_name.strip()) > 100:
        raise HTTPException(status_code=422, detail="Tên kết nối phải có từ 1 đến 100 ký tự.")
    provider = HRMSandboxProvider(HRMSandboxConfig(endpoint, api_key, 5.0), connection_id="sandbox")
    try:
        await provider.test_connection()
    except HRMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return {"state": "CONNECTED", "connection_name": connection_name.strip(), "provider_type": "sandbox", "endpoint": endpoint}


async def test_connection_id(db, connection_id: str, *, require_connected: bool = False) -> tuple[HRMSandboxProvider, dict]:
    provider, row = make_provider(db, connection_id, require_connected=require_connected)
    try:
        await provider.test_connection()
    except HRMProviderError as exc:
        failed_state = "PAUSED" if row["state"] == "PAUSED" else "ERROR"
        db.execute("UPDATE HRM_CONNECTIONS SET state = ?, last_checked_at = ?, last_check_message = ?, updated_at = ? WHERE connection_id = ?",
                   (failed_state, utc_now(), str(exc)[:255], utc_now(), connection_id))
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from None
    # A connectivity check must not silently resume a paused connection.
    state = "PAUSED" if row["state"] == "PAUSED" else "CONNECTED"
    db.execute("UPDATE HRM_CONNECTIONS SET state = ?, last_checked_at = ?, last_check_message = 'Kết nối Sandbox thành công.', updated_at = ? WHERE connection_id = ?",
               (state, utc_now(), utc_now(), connection_id))
    db.commit()
    return provider, dict(_connection_row(db, connection_id))


def connection_history(db, connection_id: str, page: int = 1, page_size: int = 20) -> dict:
    row = _connection_row(db, connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết nối HRM.")
    offset = (page - 1) * page_size
    items = []
    fetch_limit = page * page_size
    for table, timestamp_column, status_column, description in (
        ("HRM_SYNC_HISTORY", "created_at", "status", "Inbound sync"),
        ("HRM_OUTBOUND_HISTORY", "created_at", "event_status", "Outbound proposal"),
        ("HRM_CONNECTION_AUDIT", "created_at", "event_type", "Connection"),
    ):
        if table == "HRM_CONNECTION_AUDIT":
            rows = db.execute(
                "SELECT id, event_type AS event, details AS detail, created_at FROM HRM_CONNECTION_AUDIT WHERE connection_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (connection_id, fetch_limit, 0),
            ).fetchall()
        elif table == "HRM_SYNC_HISTORY":
            rows = db.execute(
                "SELECT h.id, h.status AS event, h.created_at, h.total_count, h.created_count, h.updated_count, h.skipped_count, u.ho_ten AS actor_name FROM HRM_SYNC_HISTORY h LEFT JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.actor_user_id WHERE h.provider_id = ? ORDER BY h.id DESC LIMIT ? OFFSET ?",
                (connection_id, fetch_limit, 0),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT h.id, h.event_status AS event, h.reason AS detail, h.created_at, u.ho_ten AS actor_name FROM HRM_OUTBOUND_HISTORY h LEFT JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.actor_user_id WHERE h.provider_id = ? ORDER BY h.id DESC LIMIT ? OFFSET ?",
                (connection_id, fetch_limit, 0),
            ).fetchall()
        items.extend({"source": description, **dict(item)} for item in rows)
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {"connection_id": connection_id, "items": items[offset:offset + page_size], "page": page, "page_size": page_size}


def invalidate_previews(db, connection_id: str | None = None) -> None:
    where = " AND provider_id = ?" if connection_id else ""
    parameters = (connection_id,) if connection_id else ()
    db.execute(f"UPDATE HRM_SYNC_PREVIEWS SET status = 'STALE' WHERE status = 'PENDING'{where}", parameters)
    db.execute(f"UPDATE HRM_OUTBOUND_PREVIEWS SET status = 'STALE' WHERE status IN ('PENDING', 'APPROVED'){where}", parameters)


def add_connection(db, connection_name: str, endpoint: str, api_key: str, actor_id: int) -> dict:
    endpoint = validate_endpoint(endpoint)
    api_key = validate_api_key(api_key)
    connection_name = connection_name.strip()
    if not connection_name or len(connection_name) > 100:
        raise HTTPException(status_code=422, detail="Tên kết nối phải có từ 1 đến 100 ký tự.")
    connection_id = uuid4().hex
    try:
        credential_ref = secret_vault.put(connection_id, api_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Không thể lưu credential an toàn bằng DPAPI trên Windows. Chưa tạo kết nối.") from exc
    now = utc_now()
    try:
        db.execute(
            "INSERT INTO HRM_CONNECTIONS (connection_id, connection_name, provider_type, endpoint, state, credential_ref, last_checked_at, last_check_message, created_by, created_at, updated_at) "
            "VALUES (?, ?, 'sandbox', ?, 'CONNECTED', ?, ?, 'Kết nối đã được kiểm tra thành công.', ?, ?, ?)",
            (connection_id, connection_name, endpoint, credential_ref, now, actor_id, now, now),
        )
        _insert_audit(db, connection_id, "CREATED", actor_id, f"Đã thêm HRM Sandbox tại {endpoint}.")
        db.commit()
    except Exception as exc:
        db.rollback()
        secret_vault.delete(credential_ref)
        raise HTTPException(status_code=409, detail="Không thể lưu kết nối mới; hãy làm mới danh sách và thử lại.") from exc
    return {"connection_id": connection_id, "connection_name": connection_name, "provider_type": "sandbox", "endpoint": endpoint, "state": "CONNECTED", "is_active": False, "has_credential": True}


def update_connection_name(db, connection_id: str, connection_name: str, actor_id: int) -> dict:
    name = connection_name.strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=422, detail="Tên kết nối phải có từ 1 đến 100 ký tự.")
    row = _connection_row(db, connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết nối HRM.")
    db.execute("UPDATE HRM_CONNECTIONS SET connection_name = ?, updated_at = ? WHERE connection_id = ?", (name, utc_now(), connection_id))
    _insert_audit(db, connection_id, "RENAMED", actor_id, "Đã đổi tên kết nối.")
    db.commit()
    return {"connection_id": connection_id, "connection_name": name}


def pause_connection(db, connection_id: str, actor_id: int) -> dict:
    row = _connection_row(db, connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết nối HRM.")
    invalidate_previews(db, connection_id)
    db.execute("UPDATE HRM_CONNECTIONS SET state = 'PAUSED', updated_at = ? WHERE connection_id = ?", (utc_now(), connection_id))
    _insert_audit(db, connection_id, "PAUSED", actor_id, "Đã tạm dừng các lượt đồng bộ mới; dữ liệu và lịch sử được giữ lại.")
    db.commit()
    return {"state": "PAUSED"}


async def resume_connection(db, connection_id: str, actor_id: int) -> dict:
    row = _connection_row(db, connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết nối HRM.")
    await test_connection_id(db, connection_id)
    now = utc_now()
    db.execute(
        "UPDATE HRM_CONNECTIONS SET state = 'CONNECTED', last_checked_at = ?, last_check_message = ?, updated_at = ? WHERE connection_id = ?",
        (now, "Đã kiểm tra và tiếp tục kết nối Sandbox.", now, connection_id),
    )
    _insert_audit(db, connection_id, "RESUMED", actor_id, "Đã kiểm tra lại và tiếp tục kết nối.")
    db.commit()
    current = _connection_row(db, connection_id)
    return {"connection_id": connection_id, "state": current["state"], "message": current["last_check_message"]}


async def reconnect_connection(db, connection_id: str, api_key: str, actor_id: int) -> dict:
    row = _connection_row(db, connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết nối HRM.")
    api_key = validate_api_key(api_key)
    endpoint = validate_endpoint(row["endpoint"])
    provider = HRMSandboxProvider(HRMSandboxConfig(endpoint, api_key, 5.0), connection_id=connection_id)
    try:
        await provider.test_connection()
    except HRMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    try:
        reference = secret_vault.put(connection_id, api_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Không thể lưu credential an toàn bằng DPAPI trên Windows.") from exc
    now = utc_now()
    db.execute("UPDATE HRM_CONNECTIONS SET state = 'CONNECTED', credential_ref = ?, last_checked_at = ?, last_check_message = 'Kết nối Sandbox thành công.', updated_at = ? WHERE connection_id = ?",
               (reference, now, now, connection_id))
    _insert_audit(db, connection_id, "RECONNECTED", actor_id, "Đã kiểm tra lại và lưu credential mới trong kho DPAPI local.")
    db.commit()
    return {"connection_id": connection_id, "state": "CONNECTED", "has_credential": True}


def disconnect_connection(db, connection_id: str, actor_id: int) -> dict:
    row = _connection_row(db, connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết nối HRM.")
    reference = row["credential_ref"]
    invalidate_previews(db, connection_id)
    db.execute("UPDATE HRM_CONNECTIONS SET state = 'DISCONNECTED', credential_ref = NULL, updated_at = ? WHERE connection_id = ?", (utc_now(), connection_id))
    db.execute("UPDATE HRM_ACTIVE_CONNECTION SET active_connection_id = NULL, revision = revision + 1, updated_at = ? WHERE singleton_id = 1 AND active_connection_id = ?", (utc_now(), connection_id))
    _insert_audit(db, connection_id, "DISCONNECTED", actor_id, "Đã ngắt credential; dữ liệu danh bạ, mapping và lịch sử được giữ nguyên.")
    db.commit()
    secret_vault.delete(reference)
    return {"state": "DISCONNECTED"}


async def activate_connection(db, connection_id: str, expected_active_id: str | None, confirm: bool, actor_id: int) -> dict:
    if not confirm:
        raise HTTPException(status_code=422, detail="Cần xác nhận rõ thao tác chuyển kết nối.")
    row = _connection_row(db, connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết nối HRM.")
    if _active_id(db) != expected_active_id:
        raise HTTPException(status_code=409, detail="Kết nối đang dùng đã thay đổi; hãy làm mới trang và xem lại trước khi chuyển.")
    if row["state"] != "CONNECTED" or not row["credential_ref"]:
        raise HTTPException(status_code=409, detail="Kết nối đích chưa ở trạng thái CONNECTED; hãy kiểm tra hoặc kết nối lại trước.")
    await test_connection_id(db, connection_id, require_connected=True)
    previous_id = _active_id(db)
    invalidate_previews(db)
    db.execute("UPDATE HRM_ACTIVE_CONNECTION SET active_connection_id = ?, revision = revision + 1, updated_at = ? WHERE singleton_id = 1", (connection_id, utc_now()))
    _insert_audit(db, connection_id, "ACTIVATED", actor_id, f"Đã chọn làm nguồn đồng bộ đang dùng; nguồn trước: {previous_id or 'none'}.")
    if previous_id and previous_id != connection_id:
        _insert_audit(db, previous_id, "DEACTIVATED", actor_id, f"Đã chuyển nguồn đồng bộ sang {connection_id}; toàn bộ preview đang chờ bị vô hiệu hóa.")
    db.commit()
    return {"active_connection_id": connection_id, "previous_connection_id": previous_id}
