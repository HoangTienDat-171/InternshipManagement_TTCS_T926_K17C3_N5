"""Isolated E2E coverage for US37 candidate staging and explicit Mentor sync."""
import asyncio
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import uvicorn
from fastapi import HTTPException

from app import database, hrm_outbound, hrm_sandbox
from app.hrm_provider import HRMSandboxConfig, HRMSandboxProvider
from app.hrm_storage import ensure_hrm_sqlite_schema, list_directory
from app.routes import hrm_routes


def request_for(role, user_id):
    return SimpleNamespace(state=SimpleNamespace(current_user={"vai_tro": role, "ma_nguoi_dung": user_id}))


class FakeInboundProvider:
    provider_id = "sandbox"
    provider_name = "HRM Sandbox"

    def __init__(self, records):
        self.records = records

    async def test_connection(self):
        return None

    async def fetch_employees(self):
        return [dict(record) for record in self.records]


class US37OutboundConfigurationTests(unittest.TestCase):
    def test_mysql_outbound_is_enabled_only_for_local_us37_uat_sandbox(self):
        base_env = {
            "HRM_PROVIDER": "sandbox",
            "IMS_HRM_SANDBOX_OUTBOUND_ENABLED": "1",
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_DATABASE": "internship_management_us37_uat",
        }
        with patch.object(database, "DATABASE_BACKEND", "mysql"), patch.dict(os.environ, base_env, clear=False):
            self.assertTrue(hrm_outbound.outbound_enabled())
            for key, value in (("MYSQL_DATABASE", "internship_management"), ("MYSQL_HOST", "db.example.test"), ("HRM_PROVIDER", "enterprise")):
                with patch.dict(os.environ, {key: value}, clear=False):
                    self.assertFalse(hrm_outbound.outbound_enabled())


class US37BidirectionalE2ETests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us37-bidirectional-")
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "ims-uat.sqlite3"
        self.sandbox_path = self.root / "hrm-sandbox.sqlite3"
        self.db_backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        self.db_path_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.db_backend_patch.start()
        self.db_path_patch.start()
        database.init_db()
        self.db = database.get_db_connection()
        ensure_hrm_sqlite_schema(self.db)
        self.admin_id = int(self.db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro='Admin' LIMIT 1").fetchone()[0])
        self.hr_id = int(self.db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro='HR' LIMIT 1").fetchone()[0])
        self.api_key = "isolated-us37-sandbox-test-key-2026"
        self.env_patch = patch.dict(os.environ, {
            "HRM_SANDBOX_DATABASE_PATH": str(self.sandbox_path),
            "HRM_SANDBOX_API_KEY": self.api_key,
            "HRM_PROVIDER": "sandbox",
            "IMS_HRM_SANDBOX_OUTBOUND_ENABLED": "1",
        }, clear=False)
        self.env_patch.start()
        hrm_sandbox.initialize_database()
        self.server = uvicorn.Server(uvicorn.Config(
            hrm_sandbox.app, host="127.0.0.1", port=0, log_level="critical", access_log=False,
        ))
        self.server_thread = threading.Thread(target=self.server.run, daemon=True)
        self.server_thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.server.started, "The loopback-only HRM Sandbox test server did not start.")
        self.sandbox_port = self.server.servers[0].sockets[0].getsockname()[1]
        self.provider = HRMSandboxProvider(HRMSandboxConfig(
            f"http://127.0.0.1:{self.sandbox_port}", self.api_key, 3,
        ))
        self.configured_provider_patch = patch.object(hrm_routes, "_provider_or_error", return_value=self.provider)
        self.configured_provider_patch.start()

    def tearDown(self):
        self.configured_provider_patch.stop()
        self.server.should_exit = True
        self.server_thread.join(timeout=5)
        self.db.close()
        self.env_patch.stop()
        self.db_path_patch.stop()
        self.db_backend_patch.stop()
        self.temp_dir.cleanup()

    def add_completed_intern(self, suffix):
        email = f"us37-{suffix}@example.test"
        cursor = self.db.execute(
            "INSERT INTO NGUOI_DUNG (ho_ten,email,mat_khau,vai_tro,trang_thai) VALUES (?,?,?,'ThucTapSinh','HoatDong')",
            (f"Sandbox Candidate {suffix}", email, "test-password-hash"),
        )
        profile_id = int(self.db.execute(
            "INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung,trang_thai_xet_duyet,trang_thai_thuc_tap) VALUES (?,'DaDuyet','HoanThanh')",
            (cursor.lastrowid,),
        ).lastrowid)
        program_id = int(self.db.execute(
            "INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct,ten_ct,chi_tieu,trang_thai,ngay_bat_dau,ngay_ket_thuc) VALUES (?,?,1,'DaDong','2026-01-01','2026-03-01')",
            (f"US37-{suffix}", f"Synthetic completed program {suffix}"),
        ).lastrowid)
        self.db.execute(
            "INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh,ma_ho_so,trang_thai,completion_status,completion_updated_by,completion_updated_at) VALUES (?,?,'DaDuyet','HoanThanh',?, '2026-03-02 10:00:00')",
            (program_id, profile_id, self.hr_id),
        )
        self.db.commit()
        return profile_id

    def test_hr_approval_pending_acceptance_idempotency_and_sandbox_console(self):
        profile_id = self.add_completed_intern("outbound")
        candidate, reason = hrm_outbound.build_candidate_payload(self.db, profile_id)
        self.assertIsNone(reason)
        self.assertEqual(candidate["completed_programs"][0]["program_name"], "Synthetic completed program outbound")
        self.assertNotIn("email", candidate)
        self.assertNotIn("phone", candidate)
        self.assertNotIn("password", str(candidate).casefold())

        with self.assertRaises(HTTPException) as admin_denied:
            hrm_routes.preview_outbound_candidate(
                hrm_routes.OutboundProfileRequest(profile_id=profile_id), request_for("Admin", self.admin_id), self.db,
            )
        self.assertEqual(admin_denied.exception.status_code, 403)

        hr_request = request_for("HR", self.hr_id)
        preview = hrm_routes.preview_outbound_candidate(
            hrm_routes.OutboundProfileRequest(profile_id=profile_id), hr_request, self.db,
        )
        hrm_routes.approve_outbound_candidate(
            hrm_routes.OutboundPreviewRequest(preview_id=preview["preview_id"], reason="Hiring decision confirmed in isolated UAT."),
            hr_request, self.db,
        )
        sent = asyncio.run(hrm_routes.send_outbound_candidate(
            hrm_routes.OutboundPreviewRequest(preview_id=preview["preview_id"]), hr_request, self.db,
        ))
        self.assertEqual(sent["status"], "PENDING")
        self.assertIsNone(sent["external_employee_id"])
        with self.assertRaises(HTTPException) as duplicate_send:
            asyncio.run(hrm_routes.send_outbound_candidate(
                hrm_routes.OutboundPreviewRequest(preview_id=preview["preview_id"]), hr_request, self.db,
            ))
        self.assertEqual(duplicate_send.exception.status_code, 409)

        repeated = asyncio.run(self.provider.submit_candidate_request(candidate))
        self.assertEqual(repeated["candidate_request_id"], sent["candidate_request_id"])
        self.assertFalse(repeated["created"])
        pending = hrm_sandbox.list_candidate_requests(status_filter="PENDING", page=1, page_size=100)
        self.assertEqual(pending["total"], 1)

        accepted = asyncio.run(hrm_routes.decide_sandbox_candidate(
            candidate["external_reference"], hrm_routes.SandboxDecisionRequest(decision="ACCEPT"), hr_request, self.db,
        ))
        self.assertEqual(accepted["status"], "ACCEPTED")
        self.assertTrue(accepted["external_employee_id"])
        final = asyncio.run(self.provider.submit_candidate_request(candidate))
        self.assertEqual(final["employee_id"], accepted["external_employee_id"])
        self.assertEqual(hrm_sandbox.list_employees(page=1, page_size=100)["total"], 19)
        sandbox_employee = hrm_sandbox.get_employee(accepted["external_employee_id"])
        self.assertIsNone(sandbox_employee["work_email"])
        self.assertIsNone(sandbox_employee["phone"])
        local = self.db.execute(
            "SELECT status, external_employee_id FROM HRM_OUTBOUND_PROPOSALS WHERE ma_ho_so=?", (profile_id,),
        ).fetchone()
        self.assertEqual((local["status"], local["external_employee_id"]), ("ACCEPTED", accepted["external_employee_id"]))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM HRM_OUTBOUND_HISTORY WHERE ma_ho_so=?", (profile_id,)).fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT trang_thai_thuc_tap FROM HO_SO_THUC_TAP WHERE ma_ho_so=?", (profile_id,)).fetchone()[0], "HoanThanh")
        console = hrm_sandbox.sandbox_console()
        self.assertIn("Hộp thư đề xuất tuyển dụng", console.body.decode("utf-8"))
        self.assertIn("Chấp nhận và tạo nhân viên", console.body.decode("utf-8"))

    def test_sandbox_rejection_resubmit_and_acceptance_are_idempotent(self):
        payload = {
            "external_reference": "ims-profile-999999",
            "full_name": "Synthetic Retry Candidate",
            "request_type": "candidate_review",
            "source_status": "HR_REVIEW_REQUESTED",
            "completed_programs": [{
                "program_reference": "TEST-RETRY", "program_name": "Synthetic program",
                "start_date": "2026-01-01", "completion_date": "2026-02-01",
                "completion_confirmed_at": "2026-02-02T10:00:00+00:00",
            }],
        }
        first = asyncio.run(self.provider.submit_candidate_request(payload))
        rejected = asyncio.run(self.provider.decide_candidate_request(
            payload["external_reference"], "REJECT", "Synthetic review rejection for test.",
        ))
        self.assertEqual(rejected["status"], "REJECTED")
        changed_payload = {**payload, "full_name": "Synthetic Candidate Resubmitted"}
        retry = asyncio.run(self.provider.submit_candidate_request(changed_payload))
        self.assertEqual((retry["candidate_request_id"], retry["revision"], retry["status"]),
                         (first["candidate_request_id"], 2, "PENDING"))
        accepted = asyncio.run(self.provider.decide_candidate_request(payload["external_reference"], "ACCEPT"))
        repeated_accept = asyncio.run(self.provider.decide_candidate_request(payload["external_reference"], "ACCEPT"))
        self.assertEqual(accepted["status"], "ACCEPTED")
        self.assertEqual(repeated_accept["employee_id"], accepted["employee_id"])
        self.assertEqual(hrm_sandbox.list_employees(page=1, page_size=100)["total"], 19)

    def test_reconcile_pending_proposal_after_hrm_sandbox_acceptance(self):
        profile_id = self.add_completed_intern("external-acceptance")
        hr_request = request_for("HR", self.hr_id)
        preview = hrm_routes.preview_outbound_candidate(
            hrm_routes.OutboundProfileRequest(profile_id=profile_id), hr_request, self.db,
        )
        hrm_routes.approve_outbound_candidate(
            hrm_routes.OutboundPreviewRequest(preview_id=preview["preview_id"], reason="Synthetic UAT approval."),
            hr_request, self.db,
        )
        sent = asyncio.run(hrm_routes.send_outbound_candidate(
            hrm_routes.OutboundPreviewRequest(preview_id=preview["preview_id"]), hr_request, self.db,
        ))
        self.assertEqual(sent["status"], "PENDING")

        # Simulate HR accepting from the separate Sandbox UI rather than the IMS inbox.
        accepted = asyncio.run(self.provider.decide_candidate_request(
            f"ims-profile-{profile_id}", "ACCEPT",
        ))
        still_pending = self.db.execute(
            "SELECT status, external_employee_id FROM HRM_OUTBOUND_PROPOSALS WHERE ma_ho_so=?",
            (profile_id,),
        ).fetchone()
        self.assertEqual((still_pending["status"], still_pending["external_employee_id"]), ("PENDING", None))

        reconciled = asyncio.run(hrm_routes.reconcile_outbound_candidate(
            profile_id, hr_request, self.db,
        ))

        self.assertEqual(reconciled["status"], "ACCEPTED")
        self.assertEqual(reconciled["external_employee_id"], accepted["employee_id"])
        saved = self.db.execute(
            "SELECT status, external_employee_id FROM HRM_OUTBOUND_PROPOSALS WHERE ma_ho_so=?",
            (profile_id,),
        ).fetchone()
        self.assertEqual((saved["status"], saved["external_employee_id"]), ("ACCEPTED", accepted["employee_id"]))
        history = self.db.execute(
            "SELECT event_status FROM HRM_OUTBOUND_HISTORY WHERE ma_ho_so=? ORDER BY id",
            (profile_id,),
        ).fetchall()
        self.assertEqual([row["event_status"] for row in history], ["PENDING", "ACCEPTED"])

    def test_expired_dates_do_not_infer_completion_or_hiring_eligibility(self):
        profile_id = self.add_completed_intern("ineligible")
        application_id = self.db.execute(
            "SELECT ma_ung_tuyen FROM UNG_TUYEN_CHUONG_TRINH WHERE ma_ho_so=?", (profile_id,),
        ).fetchone()["ma_ung_tuyen"]
        self.db.execute(
            "UPDATE UNG_TUYEN_CHUONG_TRINH SET completion_status='ChuaHoanThanh' WHERE ma_ung_tuyen=?",
            (application_id,),
        )
        self.db.commit()
        candidate, reason = hrm_outbound.build_candidate_payload(self.db, profile_id)
        self.assertIsNone(candidate)
        self.assertIn("explicit completed status", reason)

    def test_candidate_count_excludes_completion_without_confirmation_timestamp(self):
        profile_id = self.add_completed_intern("missing-confirmation-time")
        self.db.execute(
            "UPDATE UNG_TUYEN_CHUONG_TRINH SET completion_updated_at=NULL WHERE ma_ho_so=?",
            (profile_id,),
        )
        self.db.commit()

        result = hrm_outbound.list_candidates(self.db, page=1, page_size=20)

        self.assertEqual((result["total"], result["items"]), (0, []))

    def test_explicit_external_id_mapping_updates_only_supported_mentor_fields(self):
        email = "mentor-us37@example.test"
        mentor_id = int(self.db.execute(
            "INSERT INTO NGUOI_DUNG (ho_ten,email,mat_khau,so_dien_thoai,vai_tro,trang_thai) VALUES ('Old Mentor',?,'keep-password','0900000000','Mentor','HoatDong')",
            (email,),
        ).lastrowid)
        self.db.commit()
        record = {
            "external_employee_id": "HRM-MENTOR-001", "full_name": "Updated Mentor",
            "work_email": email, "phone": "0900123456", "department_code": None,
            "department": None, "job_title": "Senior Mentor", "employment_status": "active",
            "source_updated_at": "2026-10-15T08:00:00+00:00",
        }
        fake = FakeInboundProvider([record])
        provider_patch = patch.object(hrm_routes, "_provider_or_error", return_value=fake)
        provider_patch.start()
        try:
            first_preview = asyncio.run(hrm_routes.create_preview(request_for("Admin", self.admin_id), self.db))
            self.assertEqual(first_preview["rows"][0]["action"], "CONFLICT")
            asyncio.run(hrm_routes.save_mentor_mapping(
                hrm_routes.MentorMappingRequest(external_employee_id="HRM-MENTOR-001", ma_nguoi_dung=mentor_id),
                request_for("Admin", self.admin_id), self.db,
            ))
            preview = asyncio.run(hrm_routes.create_preview(request_for("Admin", self.admin_id), self.db))
            self.assertEqual(preview["counts"]["MENTOR_UPDATE"], 1)
            result = asyncio.run(hrm_routes.apply_sync(
                hrm_routes.ApplySyncRequest(preview_id=preview["preview_id"]), request_for("Admin", self.admin_id), self.db,
            ))
            self.assertEqual((result["updated"], result["skipped"]), (1, 0))
            updated = self.db.execute(
                "SELECT ho_ten,email,so_dien_thoai,vai_tro,trang_thai,mat_khau FROM NGUOI_DUNG WHERE ma_nguoi_dung=?",
                (mentor_id,),
            ).fetchone()
            self.assertEqual((updated["ho_ten"], updated["email"], updated["so_dien_thoai"]),
                             ("Updated Mentor", email, "0900123456"))
            self.assertEqual((updated["vai_tro"], updated["trang_thai"], updated["mat_khau"]),
                             ("Mentor", "HoatDong", "keep-password"))
            self.assertEqual(list_directory(self.db, 1, 20)["total"], 1)
            self.assertEqual(self.db.execute("SELECT COUNT(*) FROM HRM_MENTOR_SYNC_AUDIT WHERE mentor_user_id=?", (mentor_id,)).fetchone()[0], 1)

            record["employment_status"] = "inactive"
            record["source_updated_at"] = "2026-10-15T09:00:00+00:00"
            status_preview = asyncio.run(hrm_routes.create_preview(request_for("Admin", self.admin_id), self.db))
            self.assertEqual(status_preview["counts"]["MENTOR_DIRECTORY_UPDATE"], 1)
            asyncio.run(hrm_routes.apply_sync(
                hrm_routes.ApplySyncRequest(preview_id=status_preview["preview_id"]),
                request_for("Admin", self.admin_id), self.db,
            ))
            after_status_import = self.db.execute(
                "SELECT trang_thai FROM NGUOI_DUNG WHERE ma_nguoi_dung=?", (mentor_id,),
            ).fetchone()["trang_thai"]
            hrm_status = self.db.execute(
                "SELECT employment_status FROM HRM_EMPLOYEE_DIRECTORY WHERE external_employee_id='HRM-MENTOR-001'",
            ).fetchone()["employment_status"]
            self.assertEqual((after_status_import, hrm_status), ("HoatDong", "inactive"))
        finally:
            provider_patch.stop()


if __name__ == "__main__":
    unittest.main()
