"""Isolated US35/US36 meeting, notification, ownership, and outbox tests."""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException, Response
from pydantic import ValidationError

from app import database, email_outbox
from app.meeting_service import MeetingService
from app.routes import meeting_routes
from app.schemas import MeetingCreate, MeetingUpdate


class US35MeetingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us35-meetings-")
        self.db_path = Path(self.temp_dir.name) / "meetings.sqlite3"
        self.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        self.path_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.backend_patch.start()
        self.path_patch.start()
        database.init_db()
        self.db = database.get_db_connection()
        self.hr = self._user("HR Ngọc", "hr-meetings@test.invalid", "HR")
        self.admin = self._user("Admin Minh", "admin-meetings@test.invalid", "Admin")
        self.intern_a = self._user("TTS An", "intern-a-meetings@test.invalid", "ThucTapSinh")
        self.intern_b = self._user("TTS Bình", "intern-b-meetings@test.invalid", "ThucTapSinh")
        self.intern_c = self._user("TTS Chi", "intern-c-meetings@test.invalid", "ThucTapSinh")
        self.mentor = self._user("Mentor Dũng", "mentor-meetings@test.invalid", "Mentor")
        self.service = MeetingService(self.db)

    def tearDown(self):
        self.db.close()
        self.path_patch.stop()
        self.backend_patch.stop()
        self.temp_dir.cleanup()

    def _user(self, name, email, role, status="HoatDong"):
        cursor = self.db.execute("""
            INSERT INTO NGUOI_DUNG (ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES (?, ?, 'test-hash', ?, ?)
        """, (name, email, role, status))
        return {
            "ma_nguoi_dung": cursor.lastrowid, "ho_ten": name,
            "email": email, "vai_tro": role, "trang_thai": status,
        }

    def _payload(self, attendee_ids=None, **changes):
        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
        data = {
            "title": "Trao đổi tiến độ thực tập",
            "content": "Chuẩn bị cập nhật tiến độ và câu hỏi.",
            "start_at": start,
            "end_at": start + timedelta(hours=1),
            "location": "Phòng họp số 2",
            "meeting_url": None,
            "attendee_ids": attendee_ids or [self.intern_a["ma_nguoi_dung"], self.intern_b["ma_nguoi_dung"]],
        }
        data.update(changes)
        return MeetingCreate(**data)

    def _create(self, attendees=None, key="meeting-create-key-001"):
        return self.service.create_meeting(self.hr, self._payload(attendees).model_dump(), key)

    def _counts(self, table):
        return self.db.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()["total"]

    def test_create_is_idempotent_and_creates_private_app_and_email_events(self):
        meeting, created = self._create()
        self.assertTrue(created)
        self.assertEqual(meeting["status"], "SCHEDULED")
        self.assertEqual(meeting["email_queue_result"], {"queued": 2, "not_queued": 0})
        self.assertEqual(self._counts("LICH_HOP"), 1)
        self.assertEqual(self._counts("LICH_HOP_NGUOI_THAM_GIA"), 2)
        self.assertEqual(self._counts("THONG_BAO"), 2)
        self.assertEqual(self._counts("EMAIL_OUTBOX"), 2)

        repeated, created_again = self._create(key="meeting-create-key-001")
        self.assertFalse(created_again)
        self.assertEqual(repeated["id"], meeting["id"])
        self.assertEqual((self._counts("LICH_HOP"), self._counts("THONG_BAO"), self._counts("EMAIL_OUTBOX")), (1, 2, 2))

        changed_payload = self._payload(title="Nội dung khác").model_dump()
        with self.assertRaises(HTTPException) as conflict:
            self.service.create_meeting(self.hr, changed_payload, "meeting-create-key-001")
        self.assertEqual(conflict.exception.status_code, 409)

    def test_edit_versions_and_retains_removed_participant_history(self):
        meeting, _ = self._create()
        payload = self._payload(
            attendee_ids=[self.intern_a["ma_nguoi_dung"], self.intern_c["ma_nguoi_dung"]],
            title="Trao đổi tiến độ đã cập nhật",
            start_at=datetime.fromisoformat(meeting["start_at"].replace("Z", "+00:00")) + timedelta(hours=2),
            end_at=datetime.fromisoformat(meeting["end_at"].replace("Z", "+00:00")) + timedelta(hours=2),
        ).model_dump()
        payload["expected_version"] = meeting["version"]
        updated = self.service.update_meeting(meeting["id"], self.hr, payload)
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["email_queue_result"], {"queued": 3, "not_queued": 0})
        states = {
            row["user_id"]: row["status"] for row in self.db.execute(
                "SELECT user_id, status FROM LICH_HOP_NGUOI_THAM_GIA WHERE meeting_id = ?", (meeting["id"],)
            ).fetchall()
        }
        self.assertEqual(states, {
            self.intern_a["ma_nguoi_dung"]: "INVITED",
            self.intern_b["ma_nguoi_dung"]: "REMOVED",
            self.intern_c["ma_nguoi_dung"]: "INVITED",
        })
        self.assertEqual(self._counts("THONG_BAO"), 5)
        self.assertEqual(self._counts("EMAIL_OUTBOX"), 5)

        payload["expected_version"] = meeting["version"]
        with self.assertRaises(HTTPException) as stale_edit:
            self.service.update_meeting(meeting["id"], self.hr, payload)
        self.assertEqual(stale_edit.exception.status_code, 409)
        self.assertEqual((self._counts("THONG_BAO"), self._counts("EMAIL_OUTBOX")), (5, 5))

        no_change = self._payload(
            attendee_ids=[self.intern_a["ma_nguoi_dung"], self.intern_c["ma_nguoi_dung"]],
            title="Trao đổi tiến độ đã cập nhật",
            start_at=datetime.fromisoformat(updated["start_at"].replace("Z", "+00:00")),
            end_at=datetime.fromisoformat(updated["end_at"].replace("Z", "+00:00")),
        ).model_dump()
        no_change["expected_version"] = 2
        unchanged = self.service.update_meeting(meeting["id"], self.hr, no_change)
        self.assertTrue(unchanged["email_queue_result"]["unchanged"])
        self.assertEqual(self._counts("THONG_BAO"), 5)

    def test_cancel_preserves_history_and_is_idempotent(self):
        meeting, _ = self._create()
        cancelled = self.service.cancel_meeting(meeting["id"], self.hr, meeting["version"])
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertEqual(cancelled["email_queue_result"], {"queued": 2, "not_queued": 0})
        self.assertEqual(self._counts("LICH_HOP_NGUOI_THAM_GIA"), 2)
        before = (self._counts("THONG_BAO"), self._counts("EMAIL_OUTBOX"))
        repeated = self.service.cancel_meeting(meeting["id"], self.hr, meeting["version"])
        self.assertEqual(repeated["status"], "CANCELLED")
        self.assertEqual((self._counts("THONG_BAO"), self._counts("EMAIL_OUTBOX")), before)
        with self.assertRaises(HTTPException) as edit_cancelled:
            self.service.update_meeting(meeting["id"], self.hr, {
                **self._payload().model_dump(), "expected_version": cancelled["version"],
            })
        self.assertEqual(edit_cancelled.exception.status_code, 409)

    def test_idor_and_role_checks_hide_private_meetings(self):
        meeting, _ = self._create([self.intern_a["ma_nguoi_dung"]])
        intern_request = SimpleNamespace(state=SimpleNamespace(current_user=self.intern_a))
        other_request = SimpleNamespace(state=SimpleNamespace(current_user=self.intern_b))
        self.assertEqual(meeting_routes.get_meeting(meeting["id"], intern_request, self.db)["id"], meeting["id"])
        with self.assertRaises(HTTPException) as not_invited:
            meeting_routes.get_meeting(meeting["id"], other_request, self.db)
        self.assertEqual(not_invited.exception.status_code, 404)
        self.assertEqual(len(meeting_routes.list_meetings(intern_request, self.db)), 1)
        self.assertEqual(meeting_routes.list_meetings(other_request, self.db), [])
        with self.assertRaises(HTTPException) as forbidden:
            meeting_routes.create_meeting(
                self._payload([self.intern_a["ma_nguoi_dung"]]), intern_request,
                Response(), "meeting-create-key-002", self.db,
            )
        self.assertEqual(forbidden.exception.status_code, 403)

    def test_email_queue_failure_keeps_meeting_and_app_notification(self):
        self.db.execute("""
            CREATE TRIGGER reject_meeting_email BEFORE INSERT ON EMAIL_OUTBOX
            WHEN NEW.reference_type = 'meeting'
            BEGIN SELECT RAISE(ABORT, 'simulated outbox insert failure'); END
        """)
        meeting, _ = self._create([self.intern_a["ma_nguoi_dung"]])
        self.assertEqual(meeting["email_queue_result"], {"queued": 0, "not_queued": 1})
        self.assertEqual(self._counts("LICH_HOP"), 1)
        self.assertEqual(self._counts("THONG_BAO"), 1)
        self.assertEqual(self._counts("EMAIL_OUTBOX"), 0)

    def test_smtp_failure_retries_without_losing_meeting_or_notification(self):
        meeting, _ = self._create([self.intern_a["ma_nguoi_dung"]])
        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.test.invalid", "SMTP_PORT": "587",
            "SMTP_USERNAME": "test-user", "SMTP_PASSWORD": "test-secret",
            "SMTP_FROM": "no-reply@test.invalid", "SMTP_USE_SSL": "false",
            "SMTP_USE_STARTTLS": "false", "SMTP_TIMEOUT_SECONDS": "1",
        }), patch.object(email_outbox.smtplib, "SMTP", side_effect=OSError("simulated SMTP outage")):
            self.assertTrue(email_outbox.process_one_email())
        outbox = self.db.execute("SELECT status, retry_count FROM EMAIL_OUTBOX").fetchone()
        self.assertEqual((outbox["status"], outbox["retry_count"]), ("RETRY", 1))
        saved = self.service.get_meeting(meeting["id"], self.hr)
        self.assertEqual(saved["status"], "SCHEDULED")
        self.assertEqual(self._counts("THONG_BAO"), 1)

    def test_validation_and_program_context_in_participant_search(self):
        bad_data = self._payload([self.intern_a["ma_nguoi_dung"]]).model_dump()
        bad_data["start_at"] = bad_data["start_at"].replace(tzinfo=None)
        with self.assertRaises(ValidationError):
            MeetingCreate(**bad_data)
        with self.assertRaises(ValidationError):
            self._payload([self.intern_a["ma_nguoi_dung"], self.intern_a["ma_nguoi_dung"]])
        with self.assertRaises(ValidationError):
            self._payload([self.intern_a["ma_nguoi_dung"]], location=None, meeting_url=None)

        program = self.db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, chi_tieu, trang_thai)
            VALUES ('MEETING-QA', 'Chương trình kiểm thử lịch họp', 5, 'DangMo')
        """).lastrowid
        profile = self.db.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, trang_thai_xet_duyet)
            VALUES (?, 'DaDuyet')
        """, (self.intern_a["ma_nguoi_dung"],)).lastrowid
        self.db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai)
            VALUES (?, ?, 'DaDuyet')
        """, (program, profile))
        self.db.commit()
        participants = self.service.list_participants("intern-a-meetings")
        self.assertEqual(len(participants), 1)
        self.assertEqual(participants[0]["programs"], ["Chương trình kiểm thử lịch họp"])
        program_search = self.service.list_participants("kiểm thử lịch họp")
        self.assertEqual([person["ma_nguoi_dung"] for person in program_search], [self.intern_a["ma_nguoi_dung"]])


if __name__ == "__main__":
    unittest.main()
