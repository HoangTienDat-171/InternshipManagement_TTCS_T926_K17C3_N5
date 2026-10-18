"""Meeting scheduling, ownership, and transactional event delivery for US35/US36."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from .notifications import create_notification

logger = logging.getLogger(__name__)
UTC = timezone.utc
LOCAL_MEETING_TIMEZONE = timezone(timedelta(hours=7))
MAX_MEETINGS = 200
MAX_PARTICIPANTS = 200


def _utc_datetime(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None, microsecond=0)


def _db_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso_utc(value: Any) -> str | None:
    if value is None:
        return None
    return _db_datetime(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _hash_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_integrity_error(error: Exception) -> bool:
    error_type = type(error)
    return isinstance(error, sqlite3.IntegrityError) or (
        error_type.__name__ == "IntegrityError"
        and error_type.__module__.split(".", maxsplit=1)[0] in {"pymysql", "mysql"}
    )


def _manager(user: dict[str, Any]) -> bool:
    return user.get("vai_tro") in {"Admin", "HR"}


def _email_datetime(value: datetime) -> str:
    return value.astimezone(LOCAL_MEETING_TIMEZONE).strftime("%d/%m/%Y %H:%M") + " (UTC+7)"


class MeetingService:
    def __init__(self, db):
        self.db = db

    def list_participants(self, search: str = "") -> list[dict[str, Any]]:
        search = (search or "").strip()
        params: list[Any] = []
        where = "WHERE u.trang_thai = 'HoatDong'"
        if search:
            where += """ AND (
                LOWER(u.ho_ten) LIKE LOWER(?) OR LOWER(u.email) LIKE LOWER(?)
                OR EXISTS (
                    SELECT 1 FROM HO_SO_THUC_TAP h
                    JOIN UNG_TUYEN_CHUONG_TRINH a ON a.ma_ho_so = h.ma_ho_so AND a.trang_thai = 'DaDuyet'
                    JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
                    WHERE h.ma_nguoi_dung = u.ma_nguoi_dung AND LOWER(c.ten_ct) LIKE LOWER(?)
                )
                OR EXISTS (
                    SELECT 1 FROM PHAN_CONG_MENTOR_TTS assignment
                    JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = assignment.ma_chuong_trinh
                    WHERE assignment.ma_nguoi_dung_mentor = u.ma_nguoi_dung AND LOWER(c.ten_ct) LIKE LOWER(?)
                )
            )"""
            pattern = f"%{search[:100]}%"
            params.extend((pattern, pattern, pattern, pattern))
        users = self.db.execute(f"""
            SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.vai_tro, u.ma_phong_ban, p.ten_phong_ban
            FROM NGUOI_DUNG u
            LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = u.ma_phong_ban
            {where}
            ORDER BY u.ho_ten, u.ma_nguoi_dung
            LIMIT ?
        """, (*params, MAX_PARTICIPANTS)).fetchall()
        items = [dict(row) for row in users]
        ids = [item["ma_nguoi_dung"] for item in items]
        programs_by_user: dict[int, set[str]] = {int(user_id): set() for user_id in ids}
        if ids:
            placeholders = ",".join("?" for _ in ids)
            intern_programs = self.db.execute(f"""
                SELECT h.ma_nguoi_dung, c.ten_ct
                FROM HO_SO_THUC_TAP h
                JOIN UNG_TUYEN_CHUONG_TRINH a ON a.ma_ho_so = h.ma_ho_so AND a.trang_thai = 'DaDuyet'
                JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
                WHERE h.ma_nguoi_dung IN ({placeholders})
            """, tuple(ids)).fetchall()
            for row in intern_programs:
                programs_by_user[int(row["ma_nguoi_dung"])].add(row["ten_ct"])
            mentor_programs = self.db.execute(f"""
                SELECT assignment.ma_nguoi_dung_mentor AS ma_nguoi_dung, c.ten_ct
                FROM PHAN_CONG_MENTOR_TTS assignment
                JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = assignment.ma_chuong_trinh
                WHERE assignment.ma_nguoi_dung_mentor IN ({placeholders})
            """, tuple(ids)).fetchall()
            for row in mentor_programs:
                programs_by_user[int(row["ma_nguoi_dung"])].add(row["ten_ct"])
        for item in items:
            item["programs"] = sorted(programs_by_user.get(int(item["ma_nguoi_dung"]), set()))
        return items

    def list_meetings(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        if _manager(user):
            rows = self.db.execute("""
                SELECT m.*, organizer.ho_ten AS organizer_name, organizer.email AS organizer_email
                FROM LICH_HOP m
                JOIN NGUOI_DUNG organizer ON organizer.ma_nguoi_dung = m.organizer_id
                ORDER BY m.start_at DESC, m.id DESC LIMIT ?
            """, (MAX_MEETINGS,)).fetchall()
        else:
            rows = self.db.execute("""
                SELECT m.*, organizer.ho_ten AS organizer_name, organizer.email AS organizer_email
                FROM LICH_HOP m
                JOIN NGUOI_DUNG organizer ON organizer.ma_nguoi_dung = m.organizer_id
                JOIN LICH_HOP_NGUOI_THAM_GIA participant
                  ON participant.meeting_id = m.id AND participant.user_id = ? AND participant.status = 'INVITED'
                ORDER BY m.start_at DESC, m.id DESC LIMIT ?
            """, (user["ma_nguoi_dung"], MAX_MEETINGS)).fetchall()
        return self._attach_details(rows, include_removed=_manager(user))

    def get_meeting(self, meeting_id: int, user: dict[str, Any]) -> dict[str, Any]:
        row = self.db.execute("""
            SELECT m.*, organizer.ho_ten AS organizer_name, organizer.email AS organizer_email
            FROM LICH_HOP m
            JOIN NGUOI_DUNG organizer ON organizer.ma_nguoi_dung = m.organizer_id
            WHERE m.id = ?
        """, (meeting_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lịch họp.")
        if not _manager(user):
            participant = self.db.execute("""
                SELECT 1 FROM LICH_HOP_NGUOI_THAM_GIA
                WHERE meeting_id = ? AND user_id = ? AND status = 'INVITED'
            """, (meeting_id, user["ma_nguoi_dung"])).fetchone()
            if not participant:
                # Do not disclose that another user's meeting exists.
                raise HTTPException(status_code=404, detail="Không tìm thấy lịch họp.")
        return self._attach_details([row], include_removed=_manager(user))[0]

    def create_meeting(self, user: dict[str, Any], payload: dict[str, Any], idempotency_key: str):
        normalized = self._normalize_payload(payload)
        request_hash = _hash_payload(normalized)
        existing = self.db.execute(
            "SELECT id, request_hash FROM LICH_HOP WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing:
            if existing["request_hash"] != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency-Key đã được dùng cho nội dung khác.")
            return self.get_meeting(int(existing["id"]), user), False

        self._validate_attendees(normalized["attendee_ids"])
        try:
            cursor = self.db.execute("""
                INSERT INTO LICH_HOP
                    (title, content, start_at, end_at, location, meeting_url, organizer_id,
                     status, version, idempotency_key, request_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'SCHEDULED', 1, ?, ?)
            """, (
                normalized["title"], normalized["content"], normalized["start_at"],
                normalized["end_at"], normalized["location"], normalized["meeting_url"],
                user["ma_nguoi_dung"], idempotency_key, request_hash,
            ))
            meeting_id = int(cursor.lastrowid)
            attendees = self._load_users(normalized["attendee_ids"])
            if len(attendees) != len(normalized["attendee_ids"]):
                raise HTTPException(status_code=422, detail="Một người tham gia không còn hoạt động. Hãy tải lại danh sách.")
            self.db.executemany("""
                INSERT INTO LICH_HOP_NGUOI_THAM_GIA (meeting_id, user_id, status)
                VALUES (?, ?, 'INVITED')
            """, [(meeting_id, attendee["ma_nguoi_dung"]) for attendee in attendees])
            queued_count = 0
            for attendee in attendees:
                queued_count += int(self._emit_event(
                    meeting_id, 1, attendee, event_type="meeting_invitation",
                    title=f"Lời mời họp: {normalized['title']}",
                    message=self._participant_message("Bạn được mời tham gia cuộc họp.", normalized),
                    email_label="Lịch họp mới",
                    organizer_name=user["ho_ten"],
                    key_suffix="created",
                ))
            self.db.commit()
            result = self.get_meeting(meeting_id, user)
            result["email_queue_result"] = {"queued": queued_count, "not_queued": len(attendees) - queued_count}
            return result, True
        except Exception as exc:
            self.db.rollback()
            try:
                existing = self.db.execute(
                    "SELECT id, request_hash FROM LICH_HOP WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone()
            except Exception:
                existing = None
            if existing:
                if existing["request_hash"] != request_hash:
                    raise HTTPException(status_code=409, detail="Idempotency-Key đã được dùng cho nội dung khác.") from exc
                return self.get_meeting(int(existing["id"]), user), False
            if _is_integrity_error(exc):
                raise HTTPException(status_code=422, detail="Người tham gia không hợp lệ hoặc dữ liệu vi phạm ràng buộc.") from exc
            raise

    def update_meeting(self, meeting_id: int, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_payload(payload)
        expected_version = int(payload["expected_version"])
        current = self.db.execute("SELECT * FROM LICH_HOP WHERE id = ?", (meeting_id,)).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Không tìm thấy lịch họp.")
        if current["status"] != "SCHEDULED":
            raise HTTPException(status_code=409, detail="Không thể sửa lịch họp đã hủy.")
        if int(current["version"]) != expected_version:
            raise HTTPException(status_code=409, detail="Lịch họp đã được cập nhật. Hãy tải lại trước khi sửa.")
        old_attendees = self.db.execute("""
            SELECT user_id FROM LICH_HOP_NGUOI_THAM_GIA
            WHERE meeting_id = ? AND status = 'INVITED'
        """, (meeting_id,)).fetchall()
        old_ids = {int(row["user_id"]) for row in old_attendees}
        new_ids = set(normalized["attendee_ids"])
        self._validate_attendees(sorted(new_ids - old_ids))
        old_values = {
            "title": current["title"],
            "content": current["content"] or "",
            "start_at": _db_datetime(current["start_at"]).strftime("%Y-%m-%d %H:%M:%S"),
            "end_at": _db_datetime(current["end_at"]).strftime("%Y-%m-%d %H:%M:%S"),
            "location": current["location"],
            "meeting_url": current["meeting_url"],
        }
        comparable = {key: normalized[key] for key in old_values}
        if old_values == comparable and old_ids == new_ids:
            result = self.get_meeting(meeting_id, user)
            result["email_queue_result"] = {"queued": 0, "not_queued": 0, "unchanged": True}
            return result

        next_version = expected_version + 1
        try:
            updated = self.db.execute("""
                UPDATE LICH_HOP SET title = ?, content = ?, start_at = ?, end_at = ?,
                    location = ?, meeting_url = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND version = ? AND status = 'SCHEDULED'
            """, (
                normalized["title"], normalized["content"], normalized["start_at"],
                normalized["end_at"], normalized["location"], normalized["meeting_url"],
                meeting_id, expected_version,
            ))
            if updated.rowcount != 1:
                self.db.rollback()
                raise HTTPException(status_code=409, detail="Lịch họp đã thay đổi. Hãy tải lại trước khi sửa.")

            removed_ids = old_ids - new_ids
            added_ids = new_ids - old_ids
            if removed_ids:
                placeholders = ",".join("?" for _ in removed_ids)
                self.db.execute(f"""
                    UPDATE LICH_HOP_NGUOI_THAM_GIA SET status = 'REMOVED', removed_at = CURRENT_TIMESTAMP
                    WHERE meeting_id = ? AND status = 'INVITED' AND user_id IN ({placeholders})
                """, (meeting_id, *sorted(removed_ids)))
            if added_ids:
                all_existing = self._load_users(sorted(added_ids))
                if len(all_existing) != len(added_ids):
                    raise HTTPException(status_code=422, detail="Một người tham gia không còn hoạt động. Hãy tải lại danh sách.")
                for attendee in all_existing:
                    prior = self.db.execute("""
                        SELECT 1 FROM LICH_HOP_NGUOI_THAM_GIA WHERE meeting_id = ? AND user_id = ?
                    """, (meeting_id, attendee["ma_nguoi_dung"])).fetchone()
                    if prior:
                        self.db.execute("""
                            UPDATE LICH_HOP_NGUOI_THAM_GIA SET status = 'INVITED', invited_at = CURRENT_TIMESTAMP,
                                removed_at = NULL WHERE meeting_id = ? AND user_id = ?
                        """, (meeting_id, attendee["ma_nguoi_dung"]))
                    else:
                        self.db.execute("""
                            INSERT INTO LICH_HOP_NGUOI_THAM_GIA (meeting_id, user_id, status)
                            VALUES (?, ?, 'INVITED')
                        """, (meeting_id, attendee["ma_nguoi_dung"]))

            event_payload = {**normalized, "version": next_version}
            queue_results = {"queued": 0, "not_queued": 0}
            if removed_ids:
                removed_users = self._load_users(sorted(removed_ids), include_inactive=True)
                for attendee in removed_users:
                    queued = self._emit_event(
                        meeting_id, next_version, attendee, event_type="meeting_removed",
                        title=f"Thay đổi lịch họp: {normalized['title']}",
                        message=f"Bạn đã được gỡ khỏi cuộc họp “{normalized['title']}”. Lịch họp đã được HR/Admin cập nhật.",
                        email_label="Bạn không còn trong lịch họp",
                        organizer_name=user["ho_ten"], key_suffix="removed",
                    )
                    queue_results["queued" if queued else "not_queued"] += 1
            current_attendees = self._load_users(sorted(new_ids), include_inactive=True)
            for attendee in current_attendees:
                event_type = "meeting_invitation" if int(attendee["ma_nguoi_dung"]) in added_ids else "meeting_updated"
                label = "Lịch họp mới" if event_type == "meeting_invitation" else "Lịch họp được cập nhật"
                sentence = "Bạn được mời tham gia cuộc họp." if event_type == "meeting_invitation" else "Thông tin cuộc họp bạn tham gia đã thay đổi."
                queued = self._emit_event(
                    meeting_id, next_version, attendee, event_type=event_type,
                    title=f"{label}: {normalized['title']}",
                    message=self._participant_message(sentence, event_payload),
                    email_label=label, organizer_name=user["ho_ten"], key_suffix="updated",
                )
                queue_results["queued" if queued else "not_queued"] += 1
            self.db.commit()
            result = self.get_meeting(meeting_id, user)
            result["email_queue_result"] = queue_results
            return result
        except HTTPException:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise

    def cancel_meeting(self, meeting_id: int, user: dict[str, Any], expected_version: int) -> dict[str, Any]:
        current = self.db.execute("SELECT * FROM LICH_HOP WHERE id = ?", (meeting_id,)).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Không tìm thấy lịch họp.")
        if current["status"] == "CANCELLED":
            return self.get_meeting(meeting_id, user)
        if int(current["version"]) != expected_version:
            raise HTTPException(status_code=409, detail="Lịch họp đã thay đổi. Hãy tải lại trước khi hủy.")
        next_version = expected_version + 1
        try:
            updated = self.db.execute("""
                UPDATE LICH_HOP SET status = 'CANCELLED', version = version + 1,
                    cancelled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND version = ? AND status = 'SCHEDULED'
            """, (meeting_id, expected_version))
            if updated.rowcount != 1:
                self.db.rollback()
                current = self.db.execute("SELECT status FROM LICH_HOP WHERE id = ?", (meeting_id,)).fetchone()
                if current and current["status"] == "CANCELLED":
                    return self.get_meeting(meeting_id, user)
                raise HTTPException(status_code=409, detail="Lịch họp đã thay đổi. Hãy tải lại trước khi hủy.")
            attendees = self.db.execute("""
                SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.vai_tro
                FROM LICH_HOP_NGUOI_THAM_GIA participant
                JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = participant.user_id
                WHERE participant.meeting_id = ? AND participant.status = 'INVITED'
            """, (meeting_id,)).fetchall()
            summary = {
                "title": current["title"], "content": current["content"] or "",
                "start_at": _db_datetime(current["start_at"]).strftime("%Y-%m-%d %H:%M:%S"),
                "end_at": _db_datetime(current["end_at"]).strftime("%Y-%m-%d %H:%M:%S"),
                "location": current["location"], "meeting_url": current["meeting_url"],
            }
            queue_results = {"queued": 0, "not_queued": 0}
            for attendee in attendees:
                queued = self._emit_event(
                    meeting_id, next_version, dict(attendee), event_type="meeting_cancelled",
                    title=f"Cuộc họp đã hủy: {current['title']}",
                    message=self._participant_message("Cuộc họp này đã bị HR/Admin hủy.", summary),
                    email_label="Cuộc họp đã hủy", organizer_name=user["ho_ten"], key_suffix="cancelled",
                )
                queue_results["queued" if queued else "not_queued"] += 1
            self.db.commit()
            result = self.get_meeting(meeting_id, user)
            result["email_queue_result"] = queue_results
            return result
        except HTTPException:
            raise
        except Exception:
            self.db.rollback()
            raise

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        start = _utc_datetime(payload["start_at"])
        end = _utc_datetime(payload["end_at"])
        if end <= start:
            raise HTTPException(status_code=422, detail="Thời gian kết thúc phải sau thời gian bắt đầu.")
        attendee_ids = [int(value) for value in payload["attendee_ids"]]
        if not attendee_ids or len(attendee_ids) > 100 or len(attendee_ids) != len(set(attendee_ids)):
            raise HTTPException(status_code=422, detail="Danh sách người tham gia không hợp lệ.")
        return {
            "title": payload["title"].strip(), "content": (payload.get("content") or "").strip(),
            "start_at": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end_at": end.strftime("%Y-%m-%d %H:%M:%S"),
            "location": (payload.get("location") or "").strip() or None,
            "meeting_url": (payload.get("meeting_url") or "").strip() or None,
            "attendee_ids": sorted(attendee_ids),
        }

    def _validate_attendees(self, attendee_ids: list[int]):
        attendees = self._load_users(attendee_ids)
        if len(attendees) != len(attendee_ids):
            raise HTTPException(status_code=422, detail="Danh sách có tài khoản không tồn tại hoặc chưa hoạt động.")

    def _load_users(self, attendee_ids: list[int], include_inactive: bool = False) -> list[dict[str, Any]]:
        if not attendee_ids:
            return []
        placeholders = ",".join("?" for _ in attendee_ids)
        status_filter = "" if include_inactive else "AND trang_thai = 'HoatDong'"
        rows = self.db.execute(f"""
            SELECT ma_nguoi_dung, ho_ten, email, vai_tro
            FROM NGUOI_DUNG WHERE ma_nguoi_dung IN ({placeholders}) {status_filter}
            ORDER BY ma_nguoi_dung
        """, tuple(attendee_ids)).fetchall()
        return [dict(row) for row in rows]

    def _emit_event(
        self, meeting_id: int, version: int, attendee: dict[str, Any], *, event_type: str,
        title: str, message: str, email_label: str, organizer_name: str, key_suffix: str,
    ):
        recipient_id = int(attendee["ma_nguoi_dung"])
        dedup_key = f"us35:meeting:{meeting_id}:v{version}:{key_suffix}:user:{recipient_id}"
        portal_url = os.getenv("IMS_PORTAL_URL", "").strip().rstrip("/") or "http://localhost:3000"
        detail_url = f"{portal_url}/meetings/{meeting_id}"
        email_body = (
            f"{email_label}\n\n{message}\n"
            f"Người tổ chức: {organizer_name}\n"
            f"Mở chi tiết trong IMS Portal: {detail_url}"
        )
        # App notifications are the durable event. If enqueueing an email fails,
        # rollback only the savepoint and persist the notification without mail.
        self.db.execute("SAVEPOINT meeting_delivery")
        try:
            create_notification(
                self.db, recipient_id, title, message,
                notification_type=event_type,
                reference_type="meeting" if event_type != "meeting_removed" else "meeting_removed",
                reference_id=meeting_id,
                email_recipient=attendee.get("email"),
                email_deduplication_key=dedup_key,
                email_subject=f"[IMS Portal] {email_label}: {title.partition(': ')[-1]}",
                email_template_type=f"meeting_{key_suffix}",
                email_reference_type="meeting",
                email_reference_id=meeting_id,
                email_body=email_body,
            )
            queued = self.db.execute(
                "SELECT 1 FROM EMAIL_OUTBOX WHERE deduplication_key = ?", (dedup_key,)
            ).fetchone() is not None
            self.db.execute("RELEASE SAVEPOINT meeting_delivery")
            return queued
        except Exception as exc:
            self.db.execute("ROLLBACK TO SAVEPOINT meeting_delivery")
            self.db.execute("RELEASE SAVEPOINT meeting_delivery")
            logger.warning("Meeting email enqueue failed for meeting %s (%s).", meeting_id, type(exc).__name__)
            create_notification(
                self.db, recipient_id, title, message,
                notification_type=event_type,
                reference_type="meeting" if event_type != "meeting_removed" else "meeting_removed",
                reference_id=meeting_id,
            )
            return False

    def _participant_message(self, opening: str, meeting: dict[str, Any]) -> str:
        start = _db_datetime(meeting["start_at"])
        end = _db_datetime(meeting["end_at"])
        place = meeting.get("location") or meeting.get("meeting_url") or "Chưa cập nhật"
        online = f"\nLink họp: {meeting['meeting_url']}" if meeting.get("meeting_url") else ""
        content = meeting.get("content") or "Không có nội dung bổ sung."
        return (
            f"{opening} Thời gian: {_email_datetime(start)} – {_email_datetime(end)}. "
            f"Địa điểm: {place}.{online}\nNội dung: {content}"
        )

    def _attach_details(self, rows, include_removed: bool) -> list[dict[str, Any]]:
        if not rows:
            return []
        meeting_ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in meeting_ids)
        attendee_status = "" if include_removed else "AND participant.status = 'INVITED'"
        participant_rows = self.db.execute(f"""
            SELECT participant.meeting_id, participant.user_id, participant.status,
                   participant.invited_at, participant.removed_at,
                   u.ho_ten, u.email, u.vai_tro
            FROM LICH_HOP_NGUOI_THAM_GIA participant
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = participant.user_id
            WHERE participant.meeting_id IN ({placeholders}) {attendee_status}
            ORDER BY participant.meeting_id, u.ho_ten, u.ma_nguoi_dung
        """, tuple(meeting_ids)).fetchall()
        attendees_by_meeting: dict[int, list[dict[str, Any]]] = {meeting_id: [] for meeting_id in meeting_ids}
        for row in participant_rows:
            attendee = dict(row)
            for field in ("invited_at", "removed_at"):
                attendee[field] = _iso_utc(attendee[field])
            attendees_by_meeting[int(attendee.pop("meeting_id"))].append(attendee)
        email_counts = self.db.execute(f"""
            SELECT reference_id, status, COUNT(*) AS count
            FROM EMAIL_OUTBOX
            WHERE reference_type = 'meeting' AND reference_id IN ({','.join('?' for _ in meeting_ids)})
            GROUP BY reference_id, status
        """, tuple(str(meeting_id) for meeting_id in meeting_ids)).fetchall()
        email_by_meeting: dict[int, dict[str, int]] = {meeting_id: {"total": 0, "sent": 0, "queued": 0, "failed": 0} for meeting_id in meeting_ids}
        for row in email_counts:
            meeting_id = int(row["reference_id"])
            status_value = str(row["status"])
            count = int(row["count"])
            summary = email_by_meeting.setdefault(meeting_id, {"total": 0, "sent": 0, "queued": 0, "failed": 0})
            summary["total"] += count
            if status_value == "SENT":
                summary["sent"] += count
            elif status_value in {"PENDING", "PROCESSING", "RETRY"}:
                summary["queued"] += count
            elif status_value == "FAILED":
                summary["failed"] += count
        output = []
        for source in rows:
            item = dict(source)
            for field in ("start_at", "end_at", "cancelled_at", "created_at", "updated_at"):
                item[field] = _iso_utc(item[field])
            item["version"] = int(item["version"])
            item["attendees"] = attendees_by_meeting.get(int(item["id"]), [])
            item["email_summary"] = email_by_meeting.get(int(item["id"]), {"total": 0, "sent": 0, "queued": 0, "failed": 0})
            output.append(item)
        return output
