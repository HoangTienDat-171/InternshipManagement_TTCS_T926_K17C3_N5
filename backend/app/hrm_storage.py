"""Persistent HRM import previews, department mappings, and audit history."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from . import database
from .hrm_integration import build_sync_preview

PROVIDER_ID = "sandbox"
PREVIEW_TTL_SECONDS = 900
SYNC_LOCK_SECONDS = 600

SQLITE_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS HRM_DEPARTMENT_MAPPINGS (
        provider_id TEXT NOT NULL,
        external_department_key TEXT NOT NULL,
        external_department_code TEXT NOT NULL,
        ma_phong_ban INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(provider_id, external_department_key),
        FOREIGN KEY(ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_EMPLOYEE_DIRECTORY (
        provider_id TEXT NOT NULL,
        external_employee_key TEXT NOT NULL,
        external_employee_id TEXT NOT NULL,
        full_name TEXT NOT NULL,
        work_email TEXT NULL,
        phone TEXT NULL,
        department_code TEXT NULL,
        department TEXT NULL,
        ma_phong_ban INTEGER NULL,
        job_title TEXT NULL,
        employment_status TEXT NOT NULL CHECK(employment_status IN ('active', 'inactive')),
        source_updated_at TEXT NULL,
        synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(provider_id, external_employee_key),
        FOREIGN KEY(ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE SET NULL
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_SYNC_PREVIEWS (
        preview_id TEXT PRIMARY KEY,
        provider_id TEXT NOT NULL,
        actor_user_id INTEGER NOT NULL,
        snapshot_hash TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('PENDING', 'APPLIED', 'STALE', 'EXPIRED')),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY(actor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_SYNC_HISTORY (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id TEXT NOT NULL,
        actor_user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        total_count INTEGER NOT NULL,
        created_count INTEGER NOT NULL,
        updated_count INTEGER NOT NULL,
        unchanged_count INTEGER NOT NULL,
        skipped_count INTEGER NOT NULL,
        error_count INTEGER NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY(actor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_SYNC_LOCKS (
        provider_id TEXT PRIMARY KEY,
        lock_token TEXT NULL,
        lease_until TEXT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_hrm_employee_name ON HRM_EMPLOYEE_DIRECTORY(full_name)",
    "CREATE INDEX IF NOT EXISTS idx_hrm_history_created ON HRM_SYNC_HISTORY(created_at)",
)


def ensure_hrm_sqlite_schema(db) -> None:
    """Create only additive US37 tables in an explicitly isolated SQLite DB."""
    for statement in SQLITE_SCHEMA:
        db.execute(statement)
    db.commit()


def hrm_schema_ready(db) -> bool:
    try:
        for table in (
            "HRM_DEPARTMENT_MAPPINGS", "HRM_EMPLOYEE_DIRECTORY", "HRM_SYNC_PREVIEWS",
            "HRM_SYNC_HISTORY", "HRM_SYNC_LOCKS",
        ):
            db.execute(f"SELECT 1 FROM {table} LIMIT 0")
        return True
    except Exception:
        return False


def load_sync_context(db, provider_id: str = PROVIDER_ID) -> dict[str, Any]:
    current_rows = db.execute(
        "SELECT external_employee_key, external_employee_id, full_name, work_email, phone, "
        "department_code, department, ma_phong_ban, job_title, employment_status, source_updated_at "
        "FROM HRM_EMPLOYEE_DIRECTORY WHERE provider_id = ?",
        (provider_id,),
    ).fetchall()
    department_rows = db.execute(
        "SELECT m.external_department_key, m.external_department_code, m.ma_phong_ban, p.ten_phong_ban "
        "FROM HRM_DEPARTMENT_MAPPINGS m JOIN PHONG_BAN p ON p.ma_phong_ban = m.ma_phong_ban "
        "WHERE m.provider_id = ?",
        (provider_id,),
    ).fetchall()
    user_rows = db.execute("SELECT ma_nguoi_dung, email FROM NGUOI_DUNG WHERE email IS NOT NULL").fetchall()

    existing = {}
    for row in current_rows:
        value = dict(row)
        external_key = value.pop("external_employee_key")
        value.pop("external_employee_id", None)
        existing[external_key.casefold()] = value
    mappings = {}
    for row in department_rows:
        value = dict(row)
        department_key = value.pop("external_department_key")
        value.pop("external_department_code", None)
        mappings[department_key.casefold()] = value
    emails: dict[str, list[int]] = {}
    for row in user_rows:
        email = (row["email"] or "").strip().casefold()
        if email:
            emails.setdefault(email, []).append(int(row["ma_nguoi_dung"]))
    return {
        "existing": existing,
        "mappings": mappings,
        "ims_user_ids_by_email": emails,
    }


def department_mapping_data(db, provider_departments: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    choices = [dict(row) for row in db.execute(
        "SELECT ma_phong_ban, ten_phong_ban FROM PHONG_BAN ORDER BY ten_phong_ban"
    ).fetchall()]
    mappings = {row["external_department_key"]: dict(row) for row in db.execute(
        "SELECT m.external_department_key, m.external_department_code, m.ma_phong_ban, p.ten_phong_ban "
        "FROM HRM_DEPARTMENT_MAPPINGS m JOIN PHONG_BAN p ON p.ma_phong_ban = m.ma_phong_ban "
        "WHERE m.provider_id = ?",
        (PROVIDER_ID,),
    ).fetchall()}
    return {
        "ims_departments": choices,
        "hrm_departments": [
            {
                "department_code": code,
                "department_name": name,
                "mapped_department_id": (mappings.get(code.casefold()) or {}).get("ma_phong_ban"),
                "mapped_department_name": (mappings.get(code.casefold()) or {}).get("ten_phong_ban"),
            }
            for code, name in sorted(
                {(str(item.get("department_code") or "").strip().upper(), str(item.get("department") or "").strip())
                 for item in provider_departments if item.get("department_code")}
            )
        ],
    }


def preview_rows(records: Sequence[Mapping[str, Any]], context: Mapping[str, Any]) -> list[dict[str, Any]]:
    return build_sync_preview(
        records,
        existing_by_external_id=context["existing"],
        department_mappings=context["mappings"],
        ims_user_ids_by_email=context["ims_user_ids_by_email"],
    )


def snapshot_digest(records: Sequence[Mapping[str, Any]], context: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    snapshot = {
        "records": list(records),
        "context": context,
        "preview": list(rows),
    }
    normalized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def persist_preview(db, actor_user_id: int, digest: str, provider_id: str = PROVIDER_ID) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    preview_id = str(uuid.uuid4())
    created_at = db_timestamp(now)
    expires_at = db_timestamp(now + timedelta(seconds=PREVIEW_TTL_SECONDS))
    db.execute(
        "INSERT INTO HRM_SYNC_PREVIEWS "
        "(preview_id, provider_id, actor_user_id, snapshot_hash, status, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, 'PENDING', ?, ?)",
        (preview_id, provider_id, actor_user_id, digest, created_at, expires_at),
    )
    db.commit()
    return {"preview_id": preview_id, "expires_at": expires_at}


def acquire_sync_lock(db, provider_id: str = PROVIDER_ID) -> str | None:
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    begin_transaction(db)
    try:
        db.execute("INSERT OR IGNORE INTO HRM_SYNC_LOCKS(provider_id, lock_token, lease_until) VALUES (?, NULL, NULL)", (provider_id,))
        suffix = " FOR UPDATE" if database.DATABASE_BACKEND == "mysql" else ""
        row = db.execute(
            "SELECT lock_token, lease_until FROM HRM_SYNC_LOCKS WHERE provider_id = ?" + suffix,
            (provider_id,),
        ).fetchone()
        lease_until = parse_timestamp(row["lease_until"]) if row and row["lease_until"] else None
        if row and row["lock_token"] and lease_until and lease_until > now:
            db.rollback()
            return None
        db.execute(
            "UPDATE HRM_SYNC_LOCKS SET lock_token = ?, lease_until = ? WHERE provider_id = ?",
            (token, db_timestamp(now + timedelta(seconds=SYNC_LOCK_SECONDS)), provider_id),
        )
        db.commit()
        return token
    except Exception:
        db.rollback()
        raise


def release_sync_lock(db, token: str, provider_id: str = PROVIDER_ID) -> None:
    begin_transaction(db)
    try:
        db.execute(
            "UPDATE HRM_SYNC_LOCKS SET lock_token = NULL, lease_until = NULL "
            "WHERE provider_id = ? AND lock_token = ?",
            (provider_id, token),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


def begin_transaction(db) -> None:
    if database.DATABASE_BACKEND == "mysql":
        db.execute("START TRANSACTION")
    else:
        db.execute("BEGIN IMMEDIATE")


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def db_timestamp(value: datetime | None = None) -> str:
    value = value or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def apply_rows_and_history(db, actor_user_id: int, rows: Sequence[Mapping[str, Any]], preview_id: str) -> dict[str, Any]:
    created = updated = unchanged = skipped = 0
    now = db_timestamp()
    begin_transaction(db)
    try:
        for row in rows:
            action = row["action"]
            if action == "UNCHANGED":
                unchanged += 1
                continue
            if action in {"CONFLICT", "INVALID"}:
                skipped += 1
                continue
            if action not in {"NEW", "UPDATE"}:
                skipped += 1
                continue
            db.execute(
                """INSERT INTO HRM_EMPLOYEE_DIRECTORY (
                    provider_id, external_employee_key, external_employee_id, full_name, work_email,
                    phone, department_code, department, ma_phong_ban, job_title,
                    employment_status, source_updated_at, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, external_employee_key) DO UPDATE SET
                    external_employee_id = excluded.external_employee_id,
                    full_name = excluded.full_name,
                    work_email = excluded.work_email,
                    phone = excluded.phone,
                    department_code = excluded.department_code,
                    department = excluded.department,
                    ma_phong_ban = excluded.ma_phong_ban,
                    job_title = excluded.job_title,
                    employment_status = excluded.employment_status,
                    source_updated_at = excluded.source_updated_at,
                    synced_at = excluded.synced_at""",
                (
                    PROVIDER_ID,
                    str(row["external_employee_id"]).casefold(),
                    row["external_employee_id"],
                    row["full_name"],
                    row["work_email"],
                    row["phone"],
                    row["department_code"],
                    row["department"],
                    row["mapped_department_id"],
                    row["job_title"],
                    row["employment_status"],
                    row["source_updated_at"],
                    now,
                ),
            )
            if action == "NEW":
                created += 1
            else:
                updated += 1
        status = "SUCCESS" if skipped == 0 else "PARTIAL"
        total = len(rows)
        db.execute(
            """INSERT INTO HRM_SYNC_HISTORY (
                provider_id, actor_user_id, created_at, total_count, created_count,
                updated_count, unchanged_count, skipped_count, error_count, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (PROVIDER_ID, actor_user_id, now, total, created, updated, unchanged, skipped, status),
        )
        db.execute("UPDATE HRM_SYNC_PREVIEWS SET status = 'APPLIED' WHERE preview_id = ?", (preview_id,))
        db.commit()
        return {
            "status": status,
            "total": total,
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "skipped": skipped,
            "errors": 0,
        }
    except Exception:
        db.rollback()
        raise


def record_failed_sync(db, actor_user_id: int, total: int = 0) -> None:
    now = db_timestamp()
    try:
        db.execute(
            """INSERT INTO HRM_SYNC_HISTORY (
                provider_id, actor_user_id, created_at, total_count, created_count,
                updated_count, unchanged_count, skipped_count, error_count, status
            ) VALUES (?, ?, ?, ?, 0, 0, 0, ?, 1, 'ERROR')""",
            (PROVIDER_ID, actor_user_id, now, total, total),
        )
        db.commit()
    except Exception:
        db.rollback()


def list_history(db, page: int, page_size: int) -> dict[str, Any]:
    total = db.execute("SELECT COUNT(*) AS total FROM HRM_SYNC_HISTORY").fetchone()["total"]
    offset = (page - 1) * page_size
    rows = db.execute(
        """SELECT h.id, h.provider_id, h.created_at, h.total_count, h.created_count,
                  h.updated_count, h.unchanged_count, h.skipped_count, h.error_count,
                  h.status, u.ho_ten AS actor_name
           FROM HRM_SYNC_HISTORY h
           LEFT JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.actor_user_id
           ORDER BY h.id DESC LIMIT ? OFFSET ?""",
        (page_size, offset),
    ).fetchall()
    return {"items": [dict(row) for row in rows], "total": int(total), "page": page, "page_size": page_size}


def list_directory(db, page: int, page_size: int) -> dict[str, Any]:
    total = db.execute(
        "SELECT COUNT(*) AS total FROM HRM_EMPLOYEE_DIRECTORY WHERE provider_id = ?", (PROVIDER_ID,)
    ).fetchone()["total"]
    offset = (page - 1) * page_size
    rows = db.execute(
        """SELECT d.external_employee_id, d.full_name, d.work_email, d.phone,
                  d.department_code, d.department, d.ma_phong_ban,
                  p.ten_phong_ban AS mapped_department_name, d.job_title,
                  d.employment_status, d.source_updated_at, d.synced_at
           FROM HRM_EMPLOYEE_DIRECTORY d
           LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = d.ma_phong_ban
           WHERE d.provider_id = ? ORDER BY d.full_name, d.external_employee_id
           LIMIT ? OFFSET ?""",
        (PROVIDER_ID, page_size, offset),
    ).fetchall()
    return {"items": [dict(row) for row in rows], "total": int(total), "page": page, "page_size": page_size}


def read_preview(db, preview_id: str):
    return db.execute(
        "SELECT preview_id, provider_id, actor_user_id, snapshot_hash, status, created_at, expires_at "
        "FROM HRM_SYNC_PREVIEWS WHERE preview_id = ?",
        (preview_id,),
    ).fetchone()
