"""Explicit HR-approved intern candidate staging for the local HRM Sandbox."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from . import database
from .hrm_storage import PROVIDER_ID, db_timestamp, parse_timestamp

PREVIEW_TTL_SECONDS = 900
MAX_COMPLETED_PROGRAMS = 20


def outbound_enabled() -> bool:
    return database.DATABASE_BACKEND == "sqlite" and os.getenv("IMS_HRM_SANDBOX_OUTBOUND_ENABLED") == "1"


def build_candidate_payload(db, profile_id: int) -> tuple[dict[str, Any] | None, str | None]:
    profile = db.execute(
        """SELECT h.ma_ho_so, h.trang_thai_xet_duyet, u.ho_ten, u.vai_tro
           FROM HO_SO_THUC_TAP h JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
           WHERE h.ma_ho_so = ?""",
        (profile_id,),
    ).fetchone()
    if not profile or profile["vai_tro"] != "ThucTapSinh":
        return None, "A valid intern profile was not found."
    if profile["trang_thai_xet_duyet"] != "DaDuyet":
        return None, "The intern profile has not been approved."

    completions = db.execute(
        """SELECT a.ma_ung_tuyen, c.ma_chuong_trinh, c.ten_ct,
                  c.ngay_bat_dau, c.ngay_ket_thuc, a.completion_updated_by, a.completion_updated_at
           FROM UNG_TUYEN_CHUONG_TRINH a
           JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
           WHERE a.ma_ho_so = ? AND a.trang_thai = 'DaDuyet'
             AND a.completion_status = 'HoanThanh'
             AND a.completion_updated_by IS NOT NULL
           ORDER BY c.ngay_bat_dau, c.ma_chuong_trinh, a.ma_ung_tuyen""",
        (profile_id,),
    ).fetchall()
    if not completions:
        return None, "No approved program participation has an explicit completed status."
    if len(completions) > MAX_COMPLETED_PROGRAMS:
        return None, "The profile has too many completed programs for an automatic draft; review it manually."
    full_name = " ".join(str(profile["ho_ten"] or "").split())
    if not full_name:
        return None, "The intern profile has no valid name."

    programs = [{
        "program_reference": str(row["ma_chuong_trinh"]),
        "program_name": " ".join(str(row["ten_ct"] or "").split()),
        "start_date": str(row["ngay_bat_dau"])[:10] if row["ngay_bat_dau"] else None,
        "completion_date": str(row["ngay_ket_thuc"])[:10] if row["ngay_ket_thuc"] else None,
        "completion_confirmed_at": str(row["completion_updated_at"]) if row["completion_updated_at"] else None,
    } for row in completions]
    if any(not item["completion_confirmed_at"] for item in programs):
        return None, "A completed status is missing its confirmation timestamp."

    return {
        "external_reference": f"ims-profile-{profile_id}",
        "full_name": full_name,
        "request_type": "candidate_review",
        "source_status": "HR_REVIEW_REQUESTED",
        "completed_programs": programs,
    }, None


def payload_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def list_candidates(db, page: int, page_size: int) -> dict[str, Any]:
    where = f"""h.trang_thai_xet_duyet = 'DaDuyet' AND u.vai_tro = 'ThucTapSinh'
        AND EXISTS (SELECT 1 FROM UNG_TUYEN_CHUONG_TRINH a
                    WHERE a.ma_ho_so = h.ma_ho_so AND a.trang_thai = 'DaDuyet'
                      AND a.completion_status = 'HoanThanh'
                      AND a.completion_updated_by IS NOT NULL
                      AND a.completion_updated_at IS NOT NULL)
        AND (SELECT COUNT(*) FROM UNG_TUYEN_CHUONG_TRINH a
             WHERE a.ma_ho_so = h.ma_ho_so AND a.trang_thai = 'DaDuyet'
               AND a.completion_status = 'HoanThanh'
               AND a.completion_updated_by IS NOT NULL
               AND a.completion_updated_at IS NOT NULL) <= {MAX_COMPLETED_PROGRAMS}
        AND TRIM(COALESCE(u.ho_ten, '')) <> ''"""
    total = int(db.execute(
        f"SELECT COUNT(*) AS total FROM HO_SO_THUC_TAP h JOIN NGUOI_DUNG u "
        f"ON u.ma_nguoi_dung = h.ma_nguoi_dung WHERE {where}"
    ).fetchone()["total"])
    offset = (page - 1) * page_size
    profile_rows = db.execute(
        f"""SELECT h.ma_ho_so FROM HO_SO_THUC_TAP h JOIN NGUOI_DUNG u
            ON u.ma_nguoi_dung = h.ma_nguoi_dung WHERE {where}
            ORDER BY h.ma_ho_so DESC LIMIT ? OFFSET ?""",
        (page_size, offset),
    ).fetchall()
    items = []
    for row in profile_rows:
        profile_id = int(row["ma_ho_so"])
        payload, reason = build_candidate_payload(db, profile_id)
        if not payload:
            continue
        decision = db.execute(
            "SELECT decision_status, actor_user_id, decision_at FROM HRM_HIRING_DECISIONS WHERE ma_ho_so = ?",
            (profile_id,),
        ).fetchone()
        proposal = db.execute(
            "SELECT status, candidate_request_id, external_employee_id, updated_at FROM HRM_OUTBOUND_PROPOSALS "
            "WHERE provider_id = ? AND ma_ho_so = ?", (PROVIDER_ID, profile_id),
        ).fetchone()
        items.append({
            "profile_id": profile_id,
            "full_name": payload["full_name"],
            "completed_programs": payload["completed_programs"],
            "eligibility_reason": reason,
            "hiring_decision": decision["decision_status"] if decision else "NOT_RECORDED",
            "decision_at": decision["decision_at"] if decision else None,
            "status": proposal["status"] if proposal else "AVAILABLE",
            "candidate_request_id": proposal["candidate_request_id"] if proposal else None,
            "external_employee_id": proposal["external_employee_id"] if proposal else None,
            "updated_at": proposal["updated_at"] if proposal else None,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def create_preview(db, actor_user_id: int, profile_id: int) -> dict[str, Any]:
    payload, reason = build_candidate_payload(db, profile_id)
    if payload is None:
        raise ValueError(reason or "The intern profile is not eligible.")
    proposal = db.execute(
        "SELECT status FROM HRM_OUTBOUND_PROPOSALS WHERE provider_id = ? AND ma_ho_so = ?",
        (PROVIDER_ID, profile_id),
    ).fetchone()
    if proposal and proposal["status"] not in {"REJECTED", "FAILED"}:
        raise ValueError("A candidate request already exists or needs reconciliation.")
    now = datetime.now(timezone.utc)
    preview_id = str(uuid.uuid4())
    expires_at = db_timestamp(now + timedelta(seconds=PREVIEW_TTL_SECONDS))
    db.execute(
        """INSERT INTO HRM_OUTBOUND_PREVIEWS
           (preview_id, provider_id, actor_user_id, ma_ho_so, snapshot_hash, status, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
        (preview_id, PROVIDER_ID, actor_user_id, profile_id, payload_digest(payload), db_timestamp(now), expires_at),
    )
    db.commit()
    return {
        "preview_id": preview_id,
        "expires_at": expires_at,
        "profile_id": profile_id,
        "payload": payload,
        "destination": "Local HRM Sandbox candidate inbox",
        "resulting_status": "PENDING_REVIEW",
        "warnings": [
            "Only an HR-approved, explicitly completed application can be sent.",
            "The Sandbox stores a pending candidate draft; HRM must accept or reject it before an employee is created.",
            "No email, phone, CV, detailed evaluation, password, or IMS role is sent.",
            "All explicitly completed approved programs are listed; no historical program is chosen arbitrarily.",
            "Department is omitted; the HRM side must confirm the official department.",
        ],
    }


def read_outbound_preview(db, preview_id: str):
    return db.execute(
        "SELECT preview_id, provider_id, actor_user_id, ma_ho_so, snapshot_hash, status, expires_at "
        "FROM HRM_OUTBOUND_PREVIEWS WHERE preview_id = ?", (preview_id,),
    ).fetchone()


def approve_preview(db, preview, actor_user_id: int, reason: str | None = None) -> None:
    now = db_timestamp()
    existing = db.execute(
        "SELECT status FROM HRM_OUTBOUND_PROPOSALS WHERE provider_id = ? AND ma_ho_so = ?",
        (PROVIDER_ID, int(preview["ma_ho_so"])),
    ).fetchone()
    if existing and existing["status"] not in {"REJECTED", "FAILED"}:
        raise ValueError("A candidate request already exists or needs reconciliation.")
    db.execute(
        """INSERT INTO HRM_HIRING_DECISIONS (ma_ho_so, decision_status, actor_user_id, decision_at, reason)
           VALUES (?, 'APPROVED', ?, ?, ?)
           ON CONFLICT(ma_ho_so) DO UPDATE SET decision_status = 'APPROVED',
             actor_user_id = excluded.actor_user_id, decision_at = excluded.decision_at, reason = excluded.reason""",
        (int(preview["ma_ho_so"]), actor_user_id, now, reason),
    )
    db.execute(
        "INSERT INTO HRM_HIRING_DECISION_HISTORY (ma_ho_so, decision_status, actor_user_id, reason, created_at) "
        "VALUES (?, 'APPROVED', ?, ?, ?)",
        (int(preview["ma_ho_so"]), actor_user_id, reason, now),
    )
    db.execute("UPDATE HRM_OUTBOUND_PREVIEWS SET status = 'APPROVED' WHERE preview_id = ?", (preview["preview_id"],))
    db.commit()


def save_proposal(db, actor_user_id: int, profile_id: int, external_reference: str,
                  status: str, payload_hash: str, candidate_request_id: str | None = None,
                  external_employee_id: str | None = None, reason: str | None = None) -> None:
    now = db_timestamp()
    db.execute(
        """INSERT INTO HRM_OUTBOUND_PROPOSALS
           (provider_id, ma_ho_so, external_reference, candidate_request_id, status,
            external_employee_id, last_payload_hash, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(provider_id, ma_ho_so) DO UPDATE SET
             candidate_request_id = excluded.candidate_request_id,
             status = excluded.status,
             external_employee_id = excluded.external_employee_id,
             last_payload_hash = excluded.last_payload_hash,
             updated_at = excluded.updated_at""",
        (PROVIDER_ID, profile_id, external_reference, candidate_request_id, status,
         external_employee_id, payload_hash, now),
    )
    db.execute(
        """INSERT INTO HRM_OUTBOUND_HISTORY
           (provider_id, actor_user_id, ma_ho_so, external_reference, candidate_request_id,
            event_status, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (PROVIDER_ID, actor_user_id, profile_id, external_reference, candidate_request_id,
         status, reason, now),
    )
    db.commit()


def list_history(db, page: int, page_size: int) -> dict[str, Any]:
    total = int(db.execute("SELECT COUNT(*) AS total FROM HRM_OUTBOUND_HISTORY").fetchone()["total"])
    rows = db.execute(
        """SELECT h.id, h.ma_ho_so, h.external_reference, h.candidate_request_id,
                  h.event_status, h.reason, h.created_at, u.ho_ten AS actor_name
           FROM HRM_OUTBOUND_HISTORY h LEFT JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.actor_user_id
           ORDER BY h.id DESC LIMIT ? OFFSET ?""",
        (page_size, (page - 1) * page_size),
    ).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def is_preview_expired(preview) -> bool:
    expires_at = parse_timestamp(preview["expires_at"])
    return not expires_at or expires_at <= datetime.now(timezone.utc)
