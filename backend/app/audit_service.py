"""Structured IMS activity audit helpers. Values are metadata-only and redacted."""
import json
import logging
import re
from typing import Any

from fastapi import Request

from . import database


logger = logging.getLogger(__name__)
_SECRET_KEYS = {
    "password", "password_hash", "mat_khau", "token", "api_key", "apikey",
    "authorization", "cookie", "secret", "credential", "smtp_password",
    "mysql_password", "refresh_token", "access_token",
}
_SAFE_METADATA_KEYS = {
    "source", "shift_id", "expires_in_seconds", "backup_type", "file_name",
    "file_size_bytes", "checksum_sha256", "checksum_status", "retention_count",
    "schedule_enabled", "interval_hours", "files_removed", "retention_removed",
    "http_status", "reason", "method", "error_code",
    "source_backup_id", "restore_database", "table_count", "files_expired",
    "foreign_key_constraints", "upload_file_count",
}
_FIELD_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        safe = {}
        for key, item in list(value.items())[:80]:
            name = str(key)
            normalized = re.sub(r"[^a-z0-9_]", "", name.casefold())
            if normalized in _SECRET_KEYS or any(part in normalized for part in ("password", "token", "apikey", "secret", "credential")):
                continue
            safe[name[:100]] = _sanitize(item, depth=depth + 1)
        return safe
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth=depth + 1) for item in value[:80]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text[:1000]


def filter_safe_metadata(metadata: dict | None) -> dict:
    """Allow only reviewed operational fields; never persist arbitrary request data."""
    result = {}
    for key, value in (metadata or {}).items():
        name = str(key)
        if name not in _SAFE_METADATA_KEYS:
            continue
        if value is None or isinstance(value, (bool, int, float, str)):
            result[name] = _sanitize(value)
    return result


def audit_schema_ready(db) -> bool:
    if database.DATABASE_BACKEND == "mysql":
        row = db.execute(
            "SELECT 1 AS present FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'IMS_AUDIT_LOG' LIMIT 1"
        ).fetchone()
        return row is not None
    return db.execute(
        "SELECT 1 AS present FROM sqlite_master WHERE type='table' AND name='IMS_AUDIT_LOG'"
    ).fetchone() is not None


def write_audit_event(
    db,
    *,
    action: str,
    resource: str,
    outcome: str,
    actor: dict | None = None,
    resource_id: Any = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
) -> int:
    """Insert an event into the caller's transaction; the caller controls commit."""
    if outcome not in {"SUCCESS", "FAILURE"}:
        raise ValueError("Invalid audit outcome")
    action = str(action).strip().upper()[:120]
    resource = str(resource).strip().upper()[:100]
    if not _FIELD_NAME.fullmatch(action) or not _FIELD_NAME.fullmatch(resource):
        raise ValueError("Invalid audit action or resource")
    resource_id_text = None if resource_id is None else str(resource_id)[:120]
    safe_metadata = filter_safe_metadata(metadata)
    if len(json.dumps(safe_metadata, ensure_ascii=False, separators=(",", ":"))) > 8000:
        safe_metadata = {"notice": "metadata truncated"}
    actor_id = actor.get("ma_nguoi_dung") if actor else None
    actor_name = actor.get("ho_ten") if actor else None
    session_id = actor.get("session_id") if actor else None
    cursor = db.execute(
        """INSERT INTO IMS_AUDIT_LOG
           (actor_user_id, actor_name, action, resource, resource_id, outcome,
            metadata, ip_address, session_id, request_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (
            actor_id,
            str(actor_name)[:255] if actor_name else None,
            action,
            resource,
            resource_id_text,
            outcome,
            json.dumps(safe_metadata, ensure_ascii=False, separators=(",", ":")),
            str(ip_address)[:45] if ip_address else None,
            str(session_id)[:64] if session_id else None,
            str(request_id)[:128] if request_id else None,
        ),
    )
    return int(cursor.lastrowid)


def record_request_event(request: Request, *, action: str, resource: str, outcome: str, resource_id=None, metadata=None) -> None:
    """Best-effort post-response audit for generic business mutations."""
    conn = database.get_db_connection()
    try:
        if not audit_schema_ready(conn):
            return
        write_audit_event(
            conn,
            actor=getattr(request.state, "current_user", None),
            action=action,
            resource=resource,
            resource_id=resource_id,
            outcome=outcome,
            metadata=metadata,
            ip_address=request.client.host if request.client else None,
            request_id=request.headers.get("x-request-id"),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Activity audit event could not be persisted")
    finally:
        conn.close()


def create_sqlite_schema(db) -> None:
    """Create feature tables for isolated SQLite tests; runtime migrations remain explicit."""
    db.executescript("""
    CREATE TABLE IF NOT EXISTS IMS_AUDIT_LOG (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      actor_user_id INTEGER NULL, actor_name TEXT NULL,
      action TEXT NOT NULL, resource TEXT NOT NULL, resource_id TEXT NULL,
      outcome TEXT NOT NULL CHECK(outcome IN ('SUCCESS','FAILURE')),
      metadata TEXT NULL, ip_address TEXT NULL, session_id TEXT NULL,
      request_id TEXT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_ims_audit_created ON IMS_AUDIT_LOG(created_at, event_id);
    CREATE INDEX IF NOT EXISTS idx_ims_audit_actor ON IMS_AUDIT_LOG(actor_user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_ims_audit_action ON IMS_AUDIT_LOG(action, created_at);
    CREATE INDEX IF NOT EXISTS idx_ims_audit_resource ON IMS_AUDIT_LOG(resource, resource_id, created_at);
    CREATE TABLE IF NOT EXISTS IMS_ATTENDANCE_SOURCES (
      attendance_id INTEGER PRIMARY KEY,
      source TEXT NOT NULL DEFAULT 'MANUAL' CHECK(source IN ('MANUAL','QR','CARD')),
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(attendance_id) REFERENCES CHAM_CONG(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS IMS_ATTENDANCE_QR_CREDENTIALS (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      token_hash TEXT NOT NULL UNIQUE,
      ma_nguoi_dung INTEGER NOT NULL,
      issued_at DATETIME NOT NULL,
      expires_at DATETIME NOT NULL,
      used_at DATETIME NULL,
      attendance_id INTEGER NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
      FOREIGN KEY(attendance_id) REFERENCES CHAM_CONG(id) ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_ims_attendance_qr_user_expiry ON IMS_ATTENDANCE_QR_CREDENTIALS(ma_nguoi_dung, expires_at);
    CREATE TABLE IF NOT EXISTS IMS_BACKUP_SETTINGS (
      id INTEGER PRIMARY KEY CHECK(id = 1), schedule_enabled INTEGER NOT NULL DEFAULT 0,
      interval_hours INTEGER NOT NULL DEFAULT 24, retention_count INTEGER NOT NULL DEFAULT 0,
      updated_by INTEGER NULL, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    INSERT OR IGNORE INTO IMS_BACKUP_SETTINGS(id, schedule_enabled, interval_hours, retention_count) VALUES(1,0,24,0);
    CREATE TABLE IF NOT EXISTS IMS_BACKUP_JOBS (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      backup_type TEXT NOT NULL CHECK(backup_type IN ('MANUAL','SCHEDULED','RESTORE_VERIFICATION')),
      status TEXT NOT NULL CHECK(status IN ('RUNNING','SUCCESS','FAILED','EXPIRED')),
      started_by INTEGER NULL, started_at DATETIME NOT NULL, finished_at DATETIME NULL,
      file_name TEXT NULL, file_size_bytes INTEGER NULL, checksum_sha256 TEXT NULL,
      checksum_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(checksum_status IN ('PENDING','VALID','INVALID')),
      checksum_checked_at DATETIME NULL, manifest TEXT NULL, error_code TEXT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_ims_backup_created ON IMS_BACKUP_JOBS(created_at, id);
    CREATE INDEX IF NOT EXISTS idx_ims_backup_status ON IMS_BACKUP_JOBS(status, started_at);
    """)
