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
    """CREATE TABLE IF NOT EXISTS HRM_EMPLOYEE_DEPARTMENT_OVERRIDES (
        provider_id TEXT NOT NULL,
        external_employee_key TEXT NOT NULL,
        external_employee_id TEXT NOT NULL,
        external_department_code TEXT NULL,
        ma_phong_ban INTEGER NOT NULL,
        reason TEXT NOT NULL,
        approved_by INTEGER NOT NULL,
        approved_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(provider_id, external_employee_key),
        FOREIGN KEY(ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE RESTRICT,
        FOREIGN KEY(approved_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_DEPARTMENT_MAPPING_AUDIT (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id TEXT NOT NULL,
        mapping_scope TEXT NOT NULL CHECK(mapping_scope IN ('GLOBAL', 'EMPLOYEE')),
        external_department_code TEXT NULL,
        external_employee_id TEXT NULL,
        event_type TEXT NOT NULL,
        before_department_id INTEGER NULL,
        after_department_id INTEGER NULL,
        reason TEXT NOT NULL,
        actor_user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(actor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
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
    """CREATE TABLE IF NOT EXISTS HRM_MENTOR_LINKS (
        provider_id TEXT NOT NULL,
        external_employee_key TEXT NOT NULL,
        external_employee_id TEXT NOT NULL,
        ma_nguoi_dung INTEGER NOT NULL,
        approved_by INTEGER NOT NULL,
        approved_at TEXT NOT NULL,
        PRIMARY KEY(provider_id, external_employee_key),
        UNIQUE(provider_id, ma_nguoi_dung),
        FOREIGN KEY(ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
        FOREIGN KEY(approved_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_MENTOR_SYNC_AUDIT (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id TEXT NOT NULL,
        external_employee_id TEXT NOT NULL,
        mentor_user_id INTEGER NOT NULL,
        actor_user_id INTEGER NOT NULL,
        changed_fields_json TEXT NOT NULL,
        before_values_json TEXT NOT NULL,
        after_values_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(mentor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
        FOREIGN KEY(actor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_HIRING_DECISIONS (
        ma_ho_so INTEGER PRIMARY KEY,
        decision_status TEXT NOT NULL CHECK(decision_status IN ('APPROVED', 'REVOKED')),
        actor_user_id INTEGER NOT NULL,
        decision_at TEXT NOT NULL,
        reason TEXT NULL,
        FOREIGN KEY(ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
        FOREIGN KEY(actor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_HIRING_DECISION_HISTORY (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_ho_so INTEGER NOT NULL,
        decision_status TEXT NOT NULL CHECK(decision_status IN ('APPROVED', 'REVOKED')),
        actor_user_id INTEGER NOT NULL,
        reason TEXT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
        FOREIGN KEY(actor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_OUTBOUND_PREVIEWS (
        preview_id TEXT PRIMARY KEY,
        provider_id TEXT NOT NULL,
        actor_user_id INTEGER NOT NULL,
        ma_ho_so INTEGER NOT NULL,
        snapshot_hash TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('PENDING', 'APPROVED', 'SENT', 'STALE', 'EXPIRED')),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY(actor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
        FOREIGN KEY(ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_OUTBOUND_PROPOSALS (
        provider_id TEXT NOT NULL,
        ma_ho_so INTEGER NOT NULL,
        external_reference TEXT NOT NULL,
        candidate_request_id TEXT NULL,
        status TEXT NOT NULL,
        external_employee_id TEXT NULL,
        last_payload_hash TEXT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(provider_id, ma_ho_so),
        UNIQUE(provider_id, external_reference),
        UNIQUE(provider_id, candidate_request_id),
        FOREIGN KEY(ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS HRM_OUTBOUND_HISTORY (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id TEXT NOT NULL,
        actor_user_id INTEGER NOT NULL,
        ma_ho_so INTEGER NOT NULL,
        external_reference TEXT NOT NULL,
        candidate_request_id TEXT NULL,
        event_status TEXT NOT NULL,
        reason TEXT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(actor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
        FOREIGN KEY(ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_hrm_employee_name ON HRM_EMPLOYEE_DIRECTORY(full_name)",
    "CREATE INDEX IF NOT EXISTS idx_hrm_employee_override_department ON HRM_EMPLOYEE_DEPARTMENT_OVERRIDES(provider_id, external_department_code)",
    "CREATE INDEX IF NOT EXISTS idx_hrm_department_audit_created ON HRM_DEPARTMENT_MAPPING_AUDIT(provider_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_hrm_history_created ON HRM_SYNC_HISTORY(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_hrm_outbound_history_created ON HRM_OUTBOUND_HISTORY(created_at)",
)


def ensure_hrm_sqlite_schema(db) -> None:
    """Create only additive US37 tables in an explicitly isolated SQLite DB."""
    for statement in SQLITE_SCHEMA:
        db.execute(statement)
    db.commit()


def hrm_schema_ready(db) -> bool:
    try:
        for table in (
            "HRM_DEPARTMENT_MAPPINGS", "HRM_EMPLOYEE_DEPARTMENT_OVERRIDES",
            "HRM_DEPARTMENT_MAPPING_AUDIT", "HRM_EMPLOYEE_DIRECTORY", "HRM_SYNC_PREVIEWS",
            "HRM_SYNC_HISTORY", "HRM_SYNC_LOCKS", "HRM_MENTOR_LINKS",
            "HRM_MENTOR_SYNC_AUDIT", "HRM_HIRING_DECISIONS",
            "HRM_HIRING_DECISION_HISTORY", "HRM_OUTBOUND_PREVIEWS",
            "HRM_OUTBOUND_PROPOSALS", "HRM_OUTBOUND_HISTORY",
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
    override_rows = db.execute(
        "SELECT o.external_employee_key, o.external_employee_id, o.external_department_code, "
        "o.ma_phong_ban, p.ten_phong_ban, o.reason, o.approved_by, o.approved_at, o.updated_at, o.revision "
        "FROM HRM_EMPLOYEE_DEPARTMENT_OVERRIDES o JOIN PHONG_BAN p ON p.ma_phong_ban = o.ma_phong_ban "
        "WHERE o.provider_id = ?",
        (provider_id,),
    ).fetchall()
    user_rows = db.execute("SELECT ma_nguoi_dung, email FROM NGUOI_DUNG WHERE email IS NOT NULL").fetchall()
    mentor_rows = db.execute(
        "SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai, u.ma_phong_ban, "
        "u.vai_tro, p.ten_phong_ban FROM NGUOI_DUNG u "
        "LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = u.ma_phong_ban WHERE u.vai_tro = 'Mentor'"
    ).fetchall()
    link_rows = db.execute(
        "SELECT external_employee_key, external_employee_id, ma_nguoi_dung "
        "FROM HRM_MENTOR_LINKS WHERE provider_id = ?", (provider_id,)
    ).fetchall()

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
    overrides = {}
    for row in override_rows:
        value = dict(row)
        external_key = value.pop("external_employee_key")
        overrides[str(external_key).casefold()] = value
    emails: dict[str, list[int]] = {}
    for row in user_rows:
        email = (row["email"] or "").strip().casefold()
        if email:
            emails.setdefault(email, []).append(int(row["ma_nguoi_dung"]))
    mentors = {int(row["ma_nguoi_dung"]): dict(row) for row in mentor_rows}
    links = {str(row["external_employee_key"]).casefold(): {
        "external_employee_id": row["external_employee_id"],
        "ma_nguoi_dung": int(row["ma_nguoi_dung"]),
        **mentors.get(int(row["ma_nguoi_dung"]), {}),
    } for row in link_rows}
    return {
        "existing": existing,
        "mappings": mappings,
        "employee_department_overrides": overrides,
        "ims_user_ids_by_email": emails,
        "ims_users_by_id": mentors,
        "linked_mentors": links,
    }


def department_mapping_data(
    db, provider_departments: Sequence[Mapping[str, Any]], provider_id: str = PROVIDER_ID,
    source_departments: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    choices = [dict(row) for row in db.execute(
        "SELECT ma_phong_ban, ten_phong_ban FROM PHONG_BAN ORDER BY ten_phong_ban"
    ).fetchall()]
    mappings = {row["external_department_key"]: dict(row) for row in db.execute(
        "SELECT m.external_department_key, m.external_department_code, m.ma_phong_ban, p.ten_phong_ban "
        "FROM HRM_DEPARTMENT_MAPPINGS m JOIN PHONG_BAN p ON p.ma_phong_ban = m.ma_phong_ban "
        "WHERE m.provider_id = ?",
        (provider_id,),
    ).fetchall()}
    department_names: dict[str, str] = {}
    for item in source_departments:
        code = str(item.get("department_code") or "").strip().upper()
        name = str(item.get("department") or item.get("department_name") or "").strip()
        if code:
            department_names[code] = name
    for item in provider_departments:
        code = str(item.get("department_code") or "").strip().upper()
        name = str(item.get("department") or item.get("department_name") or "").strip()
        if code:
            department_names.setdefault(code, name)
    return {
        "ims_departments": choices,
        "hrm_departments": [
            {
                "department_code": code,
                "department_name": name,
                "mapped_department_id": (mappings.get(code.casefold()) or {}).get("ma_phong_ban"),
                "mapped_department_name": (mappings.get(code.casefold()) or {}).get("ten_phong_ban"),
            }
            for code, name in sorted(department_names.items())
        ],
    }


def preview_rows(records: Sequence[Mapping[str, Any]], context: Mapping[str, Any]) -> list[dict[str, Any]]:
    return build_sync_preview(
        records,
        existing_by_external_id=context["existing"],
        department_mappings=context["mappings"],
        ims_user_ids_by_email=context["ims_user_ids_by_email"],
        linked_mentors=context.get("linked_mentors", {}),
        employee_department_overrides=context.get("employee_department_overrides", {}),
    )


def employee_department_mapping_data(
    db, records: Sequence[Mapping[str, Any]], provider_id: str = PROVIDER_ID,
    source_departments: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Resolve each live HRM record using employee override, then global mapping."""
    context = load_sync_context(db, provider_id)
    by_code = {str(key).casefold(): value for key, value in context["mappings"].items()}
    overrides = context.get("employee_department_overrides", {})
    employees = []
    seen: set[str] = set()
    for record in records:
        external_id = str(record.get("external_employee_id") or "").strip()
        if not external_id or external_id.casefold() in seen:
            continue
        seen.add(external_id.casefold())
        department_code = str(record.get("department_code") or "").strip().upper()
        override = overrides.get(external_id.casefold())
        global_mapping = by_code.get(department_code.casefold())
        needs_review = bool(override and str(override.get("external_department_code") or "").casefold() != department_code.casefold())
        effective = override if override and not needs_review else global_mapping
        if needs_review:
            mapping_source = "OVERRIDE_REVIEW"
            mapping_state = "CONFLICT"
        elif override:
            mapping_source = "EMPLOYEE_OVERRIDE"
            mapping_state = "OVERRIDE"
        elif global_mapping:
            mapping_source = "DEPARTMENT_DEFAULT"
            mapping_state = "DEFAULT"
        else:
            mapping_source = "UNMAPPED"
            mapping_state = "UNMAPPED"
        employees.append({
            "external_employee_id": external_id,
            "full_name": record.get("full_name") or "",
            "work_email": record.get("work_email"),
            "department_code": department_code or None,
            "department": record.get("department"),
            "source_department_code_at_override": override.get("external_department_code") if override else None,
            "override_department_id": int(override["ma_phong_ban"]) if override else None,
            "override_department_name": override.get("ten_phong_ban") if override else None,
            "mapped_department_id": effective.get("ma_phong_ban") if effective else None,
            "mapped_department_name": effective.get("ten_phong_ban") if effective else None,
            "global_department_id": global_mapping.get("ma_phong_ban") if global_mapping else None,
            "global_department_name": global_mapping.get("ten_phong_ban") if global_mapping else None,
            "mapping_source": mapping_source,
            "mapping_state": mapping_state,
            "override_reason": override.get("reason") if override else None,
            "override_revision": int(override["revision"]) if override else None,
            "override_updated_at": override.get("updated_at") if override else None,
            "override_actor_id": int(override["approved_by"]) if override else None,
        })
    return {"employees": employees, "ims_departments": department_mapping_data(
        db, records, provider_id, source_departments,
    )["ims_departments"]}


def invalidate_pending_previews(db, provider_id: str) -> None:
    db.execute(
        "UPDATE HRM_SYNC_PREVIEWS SET status = 'STALE' WHERE provider_id = ? AND status = 'PENDING'",
        (provider_id,),
    )


def _department_name(db, department_id: int | None) -> str | None:
    if department_id is None:
        return None
    row = db.execute("SELECT ten_phong_ban FROM PHONG_BAN WHERE ma_phong_ban = ?", (department_id,)).fetchone()
    return row["ten_phong_ban"] if row else None


def _write_mapping_audit(
    db, *, provider_id: str, scope: str, event: str, actor_user_id: int,
    reason: str, before_department_id: int | None, after_department_id: int | None,
    department_code: str | None = None, external_employee_id: str | None = None,
) -> None:
    db.execute(
        "INSERT INTO HRM_DEPARTMENT_MAPPING_AUDIT (provider_id, mapping_scope, external_department_code, "
        "external_employee_id, event_type, before_department_id, after_department_id, reason, actor_user_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (provider_id, scope, department_code, external_employee_id, event,
         before_department_id, after_department_id, reason, actor_user_id, db_timestamp()),
    )


def save_global_department_mapping(
    db, *, provider_id: str, department_code: str, department_id: int,
    expected_department_id: int | None, actor_user_id: int, reason: str,
) -> dict[str, Any]:
    key = department_code.casefold()
    begin_transaction(db)
    try:
        suffix = " FOR UPDATE" if database.DATABASE_BACKEND == "mysql" else ""
        current = db.execute(
            "SELECT ma_phong_ban FROM HRM_DEPARTMENT_MAPPINGS WHERE provider_id = ? AND external_department_key = ?" + suffix,
            (provider_id, key),
        ).fetchone()
        current_id = int(current["ma_phong_ban"]) if current else None
        if current_id != expected_department_id:
            raise ValueError("Ánh xạ mặc định đã được thay đổi bởi người khác; hãy tải lại rồi xác nhận lại.")
        if current_id == department_id:
            db.rollback()
            return {"saved": True, "unchanged": True}
        if not _department_name(db, department_id):
            raise ValueError("Phòng ban IMS được chọn không tồn tại.")
        db.execute(
            "INSERT INTO HRM_DEPARTMENT_MAPPINGS (provider_id, external_department_key, external_department_code, ma_phong_ban) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(provider_id, external_department_key) DO UPDATE SET "
            "external_department_code = excluded.external_department_code, ma_phong_ban = excluded.ma_phong_ban",
            (provider_id, key, department_code, department_id),
        )
        _write_mapping_audit(
            db, provider_id=provider_id, scope="GLOBAL", event="CREATED" if current_id is None else "UPDATED",
            actor_user_id=actor_user_id, reason=reason, before_department_id=current_id,
            after_department_id=department_id, department_code=department_code,
        )
        invalidate_pending_previews(db, provider_id)
        db.commit()
        return {"saved": True, "unchanged": False}
    except Exception:
        db.rollback()
        raise


def delete_global_department_mapping(
    db, *, provider_id: str, department_code: str, expected_department_id: int,
    actor_user_id: int, reason: str,
) -> dict[str, Any]:
    key = department_code.casefold()
    begin_transaction(db)
    try:
        suffix = " FOR UPDATE" if database.DATABASE_BACKEND == "mysql" else ""
        current = db.execute(
            "SELECT ma_phong_ban FROM HRM_DEPARTMENT_MAPPINGS WHERE provider_id = ? AND external_department_key = ?" + suffix,
            (provider_id, key),
        ).fetchone()
        if not current or int(current["ma_phong_ban"]) != expected_department_id:
            raise ValueError("Ánh xạ mặc định đã thay đổi; hãy tải lại trước khi xóa.")
        db.execute("DELETE FROM HRM_DEPARTMENT_MAPPINGS WHERE provider_id = ? AND external_department_key = ?", (provider_id, key))
        _write_mapping_audit(
            db, provider_id=provider_id, scope="GLOBAL", event="DELETED", actor_user_id=actor_user_id,
            reason=reason, before_department_id=expected_department_id, after_department_id=None,
            department_code=department_code,
        )
        invalidate_pending_previews(db, provider_id)
        db.commit()
        return {"deleted": True}
    except Exception:
        db.rollback()
        raise


def save_employee_department_overrides(
    db, *, provider_id: str, employees: Sequence[Mapping[str, Any]], department_id: int,
    actor_user_id: int, reason: str,
) -> dict[str, Any]:
    if not _department_name(db, department_id):
        raise ValueError("Phòng ban IMS được chọn không tồn tại.")
    begin_transaction(db)
    changed = 0
    try:
        for employee in employees:
            external_id = str(employee["external_employee_id"]).strip()
            external_key = external_id.casefold()
            expected_revision = employee.get("expected_revision")
            current_department_code = str(employee.get("department_code") or "").upper() or None
            suffix = " FOR UPDATE" if database.DATABASE_BACKEND == "mysql" else ""
            current = db.execute(
                "SELECT ma_phong_ban, external_department_code, revision FROM HRM_EMPLOYEE_DEPARTMENT_OVERRIDES "
                "WHERE provider_id = ? AND external_employee_key = ?" + suffix,
                (provider_id, external_key),
            ).fetchone()
            current_revision = int(current["revision"]) if current else None
            if current_revision != expected_revision:
                raise ValueError(f"Ánh xạ riêng của {external_id} đã thay đổi; không có thay đổi nào được lưu. Hãy tải lại.")
            previous_id = int(current["ma_phong_ban"]) if current else None
            if previous_id == department_id and current and current["external_department_code"] == current_department_code:
                continue
            now = db_timestamp()
            db.execute(
                "INSERT INTO HRM_EMPLOYEE_DEPARTMENT_OVERRIDES (provider_id, external_employee_key, external_employee_id, "
                "external_department_code, ma_phong_ban, reason, approved_by, approved_at, updated_at, revision) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1) ON CONFLICT(provider_id, external_employee_key) DO UPDATE SET "
                "external_employee_id = excluded.external_employee_id, external_department_code = excluded.external_department_code, "
                "ma_phong_ban = excluded.ma_phong_ban, reason = excluded.reason, approved_by = excluded.approved_by, "
                "updated_at = excluded.updated_at, revision = HRM_EMPLOYEE_DEPARTMENT_OVERRIDES.revision + 1",
                (provider_id, external_key, external_id, current_department_code, department_id,
                 reason, actor_user_id, now, now),
            )
            _write_mapping_audit(
                db, provider_id=provider_id, scope="EMPLOYEE", event="CREATED" if current is None else "UPDATED",
                actor_user_id=actor_user_id, reason=reason, before_department_id=previous_id,
                after_department_id=department_id, department_code=current_department_code,
                external_employee_id=external_id,
            )
            changed += 1
        if changed:
            invalidate_pending_previews(db, provider_id)
        db.commit()
        return {"saved": True, "updated": changed, "total": len(employees)}
    except Exception:
        db.rollback()
        raise


def delete_employee_department_override(
    db, *, provider_id: str, external_employee_id: str, expected_revision: int,
    actor_user_id: int, reason: str,
) -> dict[str, Any]:
    external_key = external_employee_id.casefold()
    begin_transaction(db)
    try:
        suffix = " FOR UPDATE" if database.DATABASE_BACKEND == "mysql" else ""
        current = db.execute(
            "SELECT ma_phong_ban, external_department_code, revision FROM HRM_EMPLOYEE_DEPARTMENT_OVERRIDES "
            "WHERE provider_id = ? AND external_employee_key = ?" + suffix,
            (provider_id, external_key),
        ).fetchone()
        if not current or int(current["revision"]) != expected_revision:
            raise ValueError("Ánh xạ riêng đã thay đổi hoặc đã được xóa; hãy tải lại.")
        before_id = int(current["ma_phong_ban"])
        db.execute("DELETE FROM HRM_EMPLOYEE_DEPARTMENT_OVERRIDES WHERE provider_id = ? AND external_employee_key = ?", (provider_id, external_key))
        _write_mapping_audit(
            db, provider_id=provider_id, scope="EMPLOYEE", event="RESET_TO_DEFAULT", actor_user_id=actor_user_id,
            reason=reason, before_department_id=before_id, after_department_id=None,
            department_code=current["external_department_code"], external_employee_id=external_employee_id,
        )
        invalidate_pending_previews(db, provider_id)
        db.commit()
        return {"deleted": True}
    except Exception:
        db.rollback()
        raise


def list_department_mapping_audit(db, page: int = 1, page_size: int = 20, provider_id: str = PROVIDER_ID) -> dict[str, Any]:
    total = int(db.execute(
        "SELECT COUNT(*) AS total FROM HRM_DEPARTMENT_MAPPING_AUDIT WHERE provider_id = ?", (provider_id,),
    ).fetchone()["total"])
    rows = db.execute(
        "SELECT a.id, a.mapping_scope, a.external_department_code, a.external_employee_id, a.event_type, "
        "a.before_department_id, before_department.ten_phong_ban AS before_department_name, "
        "a.after_department_id, after_department.ten_phong_ban AS after_department_name, a.reason, a.created_at, "
        "u.ho_ten AS actor_name FROM HRM_DEPARTMENT_MAPPING_AUDIT a "
        "LEFT JOIN PHONG_BAN before_department ON before_department.ma_phong_ban = a.before_department_id "
        "LEFT JOIN PHONG_BAN after_department ON after_department.ma_phong_ban = a.after_department_id "
        "LEFT JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = a.actor_user_id "
        "WHERE a.provider_id = ? ORDER BY a.id DESC LIMIT ? OFFSET ?",
        (provider_id, page_size, (page - 1) * page_size),
    ).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


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


def apply_rows_and_history(db, actor_user_id: int, rows: Sequence[Mapping[str, Any]], preview_id: str, provider_id: str = PROVIDER_ID) -> dict[str, Any]:
    created = updated = unchanged = skipped = 0
    now = db_timestamp()
    begin_transaction(db)
    try:
        def upsert_directory_record(row: Mapping[str, Any]) -> None:
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
                    provider_id,
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

        for row in rows:
            action = row["action"]
            if action == "UNCHANGED":
                unchanged += 1
                continue
            if action in {"MENTOR_DIRECTORY_UPDATE", "MENTOR_UNCHANGED"}:
                upsert_directory_record(row)
                if action == "MENTOR_UNCHANGED":
                    unchanged += 1
                else:
                    updated += 1
                continue
            if action in {"CONFLICT", "INVALID"}:
                skipped += 1
                continue
            if action == "MENTOR_UPDATE":
                before = row.get("mentor_before") or {}
                after = row.get("mentor_after") or {}
                mentor_id = int(row["linked_user_id"])
                current = db.execute(
                    "SELECT ho_ten, email, so_dien_thoai, ma_phong_ban, vai_tro "
                    "FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?",
                    (mentor_id,),
                ).fetchone()
                if not current or current["vai_tro"] != "Mentor" or any(current[key] != before.get(key) for key in before):
                    raise ValueError("Linked Mentor data changed after the preview; create a new preview.")
                changed_fields = [key for key, value in after.items() if before.get(key) != value]
                db.execute(
                    "UPDATE NGUOI_DUNG SET ho_ten = ?, email = ?, so_dien_thoai = ?, ma_phong_ban = ? "
                    "WHERE ma_nguoi_dung = ? AND vai_tro = 'Mentor'",
                    (after["ho_ten"], after["email"], after["so_dien_thoai"], after["ma_phong_ban"], mentor_id),
                )
                db.execute(
                    """INSERT INTO HRM_MENTOR_SYNC_AUDIT (
                        provider_id, external_employee_id, mentor_user_id, actor_user_id,
                        changed_fields_json, before_values_json, after_values_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (provider_id, row["external_employee_id"], mentor_id, actor_user_id,
                     json.dumps(changed_fields), json.dumps(before, default=str),
                     json.dumps(after, default=str), now),
                )
                upsert_directory_record(row)
                updated += 1
                continue
            if action not in {"NEW", "UPDATE"}:
                skipped += 1
                continue
            upsert_directory_record(row)
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
            (provider_id, actor_user_id, now, total, created, updated, unchanged, skipped, status),
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


def record_failed_sync(db, actor_user_id: int, total: int = 0, provider_id: str = PROVIDER_ID) -> None:
    now = db_timestamp()
    try:
        db.execute(
            """INSERT INTO HRM_SYNC_HISTORY (
                provider_id, actor_user_id, created_at, total_count, created_count,
                updated_count, unchanged_count, skipped_count, error_count, status
            ) VALUES (?, ?, ?, ?, 0, 0, 0, ?, 1, 'ERROR')""",
            (provider_id, actor_user_id, now, total, total),
        )
        db.commit()
    except Exception:
        db.rollback()


def list_history(db, page: int, page_size: int, provider_id: str = PROVIDER_ID) -> dict[str, Any]:
    total = db.execute("SELECT COUNT(*) AS total FROM HRM_SYNC_HISTORY WHERE provider_id = ?", (provider_id,)).fetchone()["total"]
    offset = (page - 1) * page_size
    rows = db.execute(
        """SELECT h.id, h.provider_id, h.created_at, h.total_count, h.created_count,
                  h.updated_count, h.unchanged_count, h.skipped_count, h.error_count,
                  h.status, u.ho_ten AS actor_name
           FROM HRM_SYNC_HISTORY h
           LEFT JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.actor_user_id
           WHERE h.provider_id = ? ORDER BY h.id DESC LIMIT ? OFFSET ?""",
        (provider_id, page_size, offset),
    ).fetchall()
    return {"items": [dict(row) for row in rows], "total": int(total), "page": page, "page_size": page_size}


def list_directory(db, page: int, page_size: int, provider_id: str = PROVIDER_ID) -> dict[str, Any]:
    total = db.execute(
        "SELECT COUNT(*) AS total FROM HRM_EMPLOYEE_DIRECTORY WHERE provider_id = ?", (provider_id,)
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
        (provider_id, page_size, offset),
    ).fetchall()
    return {"items": [dict(row) for row in rows], "total": int(total), "page": page, "page_size": page_size}


def read_preview(db, preview_id: str):
    return db.execute(
        "SELECT preview_id, provider_id, actor_user_id, snapshot_hash, status, created_at, expires_at "
        "FROM HRM_SYNC_PREVIEWS WHERE preview_id = ?",
        (preview_id,),
    ).fetchone()
