"""US37 sandbox contract, authorization, preview, and idempotent apply tests."""
import asyncio
import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import database
from app.hrm_integration import HRMEmployeeRecord, build_import_preview, build_sync_preview, validate_employee_batch
from app.hrm_provider import HRMProviderError, HRMSandboxConfig, HRMSandboxProvider, get_sandbox_config
from app.hrm_sandbox import SandboxEmployeePatch, get_employee, initialize_database, list_employees, require_api_key, update_employee
from app.hrm_storage import (
    acquire_sync_lock,
    ensure_hrm_sqlite_schema,
    list_directory,
    load_sync_context,
    list_history,
    preview_rows,
)
from app.routes import hrm_routes


def request_for(role="Admin", user_id=1):
    return SimpleNamespace(state=SimpleNamespace(current_user={"vai_tro": role, "ma_nguoi_dung": user_id}))


class FakeSandboxProvider:
    provider_name = "HRM Sandbox"
    provider_id = "sandbox"

    def __init__(self, records):
        self.records = records
        self.available = True

    async def test_connection(self):
        if not self.available:
            raise HRMProviderError("Sandbox unavailable in isolated test.")

    async def fetch_employees(self):
        if not self.available:
            raise HRMProviderError("Sandbox unavailable in isolated test.")
        return [dict(record) for record in self.records]


class US37ContractTests(unittest.TestCase):
    def employee(self, **changes):
        record = {
            "external_employee_id": " EMP-001 ",
            "full_name": "  Nguyen   An  ",
            "work_email": " AN@EXAMPLE.TEST ",
            "phone": " 0900 000 000 ",
            "department_code": "tech",
            "department": " Engineering ",
            "job_title": " Analyst ",
            "employment_status": "ACTIVE",
            "source_updated_at": "2026-10-15T08:00:00+00:00",
        }
        record.update(changes)
        return record

    def test_contract_normalizes_and_rejects_unknown_or_invalid_fields(self):
        record = HRMEmployeeRecord.model_validate(self.employee())
        self.assertEqual(record.external_employee_id, "EMP-001")
        self.assertEqual(record.full_name, "Nguyen An")
        self.assertEqual(record.work_email, "an@example.test")
        self.assertEqual(record.department_code, "TECH")
        self.assertEqual(record.employment_status, "active")
        with self.assertRaises(ValidationError):
            HRMEmployeeRecord.model_validate(self.employee(api_key="must-not-enter-IMS"))
        with self.assertRaises(ValidationError):
            HRMEmployeeRecord.model_validate(self.employee(external_employee_id="   "))

    def test_batch_rejects_duplicate_external_ids_for_legacy_preview(self):
        with self.assertRaisesRegex(ValueError, "mã nhân viên ngoài bị trùng"):
            validate_employee_batch([
                self.employee(external_employee_id="EMP-001"),
                self.employee(external_employee_id="emp-001"),
            ])

    def test_sync_preview_covers_new_update_unchanged_conflict_and_invalid(self):
        existing = {
            "emp-upd": {
                "full_name": "Changed Name", "work_email": "update@example.test", "phone": "old",
                "department_code": "TECH", "department": "Engineering", "ma_phong_ban": 9,
                "job_title": "Analyst", "employment_status": "active",
                "source_updated_at": "2026-10-14T08:00:00Z",
            },
            "emp-same": {
                "full_name": "Nguyen An", "work_email": "same@example.test", "phone": "0900 000 000",
                "department_code": "TECH", "department": "Engineering", "ma_phong_ban": 9,
                "job_title": "Analyst", "employment_status": "active",
                "source_updated_at": "2026-10-15T08:00:00+00:00",
            },
        }
        records = [
            self.employee(external_employee_id="EMP-NEW", work_email="new@example.test"),
            self.employee(external_employee_id="EMP-UPD", full_name="New Name", work_email="update@example.test", phone="new", source_updated_at="2026-10-15T09:00:00Z"),
            self.employee(external_employee_id="EMP-SAME", work_email="same@example.test", phone="0900 000 000"),
            self.employee(external_employee_id="EMP-UNMAPPED", work_email="unmapped@example.test", department_code="UNKNOWN"),
            self.employee(external_employee_id="EMP-MATCH", work_email="existing@ims.test"),
            self.employee(external_employee_id="EMP-BAD", work_email="bad-email"),
        ]
        preview = build_sync_preview(
            records,
            existing,
            {"tech": {"ma_phong_ban": 9, "ten_phong_ban": "Engineering"}},
            {"existing@ims.test": [12]},
        )
        self.assertEqual([row["action"] for row in preview], ["NEW", "UPDATE", "UNCHANGED", "CONFLICT", "CONFLICT", "INVALID"])
        self.assertEqual(preview[1]["mapped_department_id"], 9)
        self.assertIn(12, preview[4]["candidate_user_ids"])

    def test_duplicate_source_ids_are_invalid_and_inactive_is_only_a_warning(self):
        preview = build_sync_preview(
            [
                self.employee(),
                self.employee(external_employee_id="emp-001"),
                self.employee(external_employee_id="EMP-003", work_email="inactive@example.test", employment_status="inactive"),
            ],
            {},
            {"tech": {"ma_phong_ban": 9, "ten_phong_ban": "Engineering"}},
            {},
        )
        self.assertEqual([row["action"] for row in preview], ["INVALID", "INVALID", "NEW"])
        self.assertTrue(any("không khóa" in warning for warning in preview[2]["warnings"]))

    def test_legacy_email_match_is_not_an_automatic_link(self):
        preview = build_import_preview([self.employee()], {}, {"an@example.test": [42]})[0]
        self.assertEqual(preview["action"], "MANUAL_LINK_REVIEW")
        self.assertEqual(preview["candidate_user_id"], 42)
        self.assertFalse(preview["applied"])

    def test_configuration_requires_sandbox_provider_and_loopback_endpoint(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(get_sandbox_config()[0])
        with patch.dict(os.environ, {
            "HRM_PROVIDER": "sandbox",
            "HRM_SANDBOX_BASE_URL": "https://attacker.example/api",
            "HRM_SANDBOX_API_KEY": "local-test-key-value-long-enough-123456",
        }, clear=True):
            config, error = get_sandbox_config()
        self.assertIsNone(config)
        self.assertIn("loopback", error)

    def test_status_never_includes_api_key(self):
        sources = {"active_connection_id": "sandbox", "items": [{
            "connection_id": "sandbox", "connection_name": "HRM Sandbox A", "endpoint": "http://127.0.0.1:8100",
            "state": "CONNECTED", "is_active": True, "has_credential": True, "last_check_message": "OK",
        }]}
        with patch.object(hrm_routes.hrm_connection_service, "list_connections", return_value=sources):
            with patch.object(hrm_routes, "hrm_schema_ready", return_value=True):
                payload = hrm_routes.get_status(request_for(), db=object())
        self.assertNotIn("top-secret-test-token-value-long-enough-123456", str(payload))
        self.assertEqual(payload["provider_name"], "HRM Sandbox")
        self.assertEqual(payload["endpoint"], "http://127.0.0.1:8100")


class US37SandboxPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "hrm-sandbox.sqlite3")
        self.env_patch = patch.dict(os.environ, {
            "HRM_SANDBOX_DATABASE_PATH": self.db_path,
            "HRM_SANDBOX_API_KEY": "sandbox-test-secret",
        }, clear=False)
        self.env_patch.start()
        initialize_database()

    def tearDown(self):
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_auth_pagination_details_and_patch_persist(self):
        with self.assertRaises(HTTPException) as denied:
            require_api_key("Bearer wrong-key")
        self.assertEqual(denied.exception.status_code, 401)
        require_api_key("Bearer sandbox-test-secret")

        first_page = list_employees(page=1, page_size=2)
        self.assertEqual(len(first_page["items"]), 2)
        self.assertGreaterEqual(first_page["total_pages"], 2)
        original = get_employee("NV001")
        updated = update_employee("NV001", SandboxEmployeePatch(
            phone="0901999000", department_code="TECH", expected_updated_at=original["updated_at"],
        ))
        self.assertNotEqual(updated.updated_at, original["updated_at"])
        self.assertEqual(get_employee("NV001")["phone"], "0901999000")

    def test_starter_employees_are_seeded_idempotently(self):
        first_load = list_employees(page=1, page_size=100)
        self.assertEqual(first_load["total"], 18)
        self.assertEqual(len({row["employee_id"] for row in first_load["items"]}), 18)
        self.assertEqual({row["employment_status"] for row in first_load["items"]}, {"ACTIVE", "INACTIVE"})
        original = get_employee("NV001")
        update_employee("NV001", SandboxEmployeePatch(phone="0901999000", expected_updated_at=original["updated_at"]))

        initialize_database()
        second_load = list_employees(page=1, page_size=100)
        self.assertEqual(second_load["total"], 18)
        self.assertEqual([row["employee_id"] for row in first_load["items"]], [row["employee_id"] for row in second_load["items"]])
        self.assertEqual(get_employee("NV001")["phone"], "0901999000")


class US37SyncWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("CREATE TABLE PHONG_BAN(ma_phong_ban INTEGER PRIMARY KEY, ten_phong_ban TEXT NOT NULL)")
        self.db.execute("CREATE TABLE NGUOI_DUNG(ma_nguoi_dung INTEGER PRIMARY KEY, ma_phong_ban INTEGER, ho_ten TEXT NOT NULL, email TEXT NOT NULL, so_dien_thoai TEXT, vai_tro TEXT NOT NULL, trang_thai TEXT, mat_khau TEXT)")
        self.db.execute("INSERT INTO PHONG_BAN VALUES (9, 'Engineering')")
        self.db.execute("INSERT INTO PHONG_BAN VALUES (10, 'AI/Data')")
        self.db.execute("INSERT INTO NGUOI_DUNG (ma_nguoi_dung, ho_ten, email, vai_tro) VALUES (1, 'Admin Test', 'admin@ims.test', 'Admin')")
        ensure_hrm_sqlite_schema(self.db)
        self.records = [{
            "external_employee_id": "NV001",
            "full_name": "Nguyen An",
            "work_email": "nguyen.an@hrm-sandbox.test",
            "phone": "0901000001",
            "department_code": "TECH",
            "department": "Kỹ thuật",
            "job_title": "Kỹ sư Backend",
            "employment_status": "active",
            "source_updated_at": "2026-10-15T08:00:00+00:00",
        }]
        self.provider = FakeSandboxProvider(self.records)
        self.patches = patch.multiple(hrm_routes, _provider_or_error=lambda *args, **kwargs: self.provider)
        self.patches.start()
        self.db.execute(
            "INSERT INTO HRM_DEPARTMENT_MAPPINGS(provider_id, external_department_key, external_department_code, ma_phong_ban) VALUES ('sandbox', 'tech', 'TECH', 9)"
        )
        self.db.commit()

    def tearDown(self):
        self.patches.stop()
        self.db.close()

    def call(self, endpoint, *args):
        with patch.object(database, "DATABASE_BACKEND", "sqlite"):
            return asyncio.run(endpoint(*args, db=self.db))

    def test_admin_only_test_preview_apply_and_second_sync_is_idempotent(self):
        with patch.object(database, "DATABASE_BACKEND", "sqlite"):
            with patch.object(hrm_routes.hrm_connection_service, "_active_id", return_value="sandbox"):
                async def checked_connection(db, connection_id):
                    return self.provider, {"state": "CONNECTED", "endpoint": "http://127.0.0.1:8100"}
                with patch.object(hrm_routes.hrm_connection_service, "test_connection_id", side_effect=checked_connection):
                    self.assertEqual(asyncio.run(hrm_routes.test_connection(request_for(), db=self.db))["state"], "CONNECTED")
        with self.assertRaises(HTTPException) as denied:
            asyncio.run(hrm_routes.create_preview(request_for("HR"), db=self.db))
        self.assertEqual(denied.exception.status_code, 403)

        first = self.call(hrm_routes.create_preview, request_for())
        self.assertEqual(first["counts"]["NEW"], 1)
        result = self.call(hrm_routes.apply_sync, hrm_routes.ApplySyncRequest(preview_id=first["preview_id"]), request_for())
        self.assertEqual((result["created"], result["updated"], result["skipped"]), (1, 0, 0))
        self.assertEqual(list_directory(self.db, 1, 20)["total"], 1)
        self.assertEqual(list_history(self.db, 1, 20)["total"], 1)

        second = self.call(hrm_routes.create_preview, request_for())
        self.assertEqual(second["counts"]["UNCHANGED"], 1)
        result2 = self.call(hrm_routes.apply_sync, hrm_routes.ApplySyncRequest(preview_id=second["preview_id"]), request_for())
        self.assertEqual((result2["created"], result2["updated"], result2["unchanged"]), (0, 0, 1))
        self.assertEqual(list_directory(self.db, 1, 20)["total"], 1)

    def test_stale_preview_is_rejected_if_sandbox_changes_before_apply(self):
        preview = self.call(hrm_routes.create_preview, request_for())
        self.provider.records[0]["phone"] = "0901999000"
        with self.assertRaises(HTTPException) as stale:
            self.call(hrm_routes.apply_sync, hrm_routes.ApplySyncRequest(preview_id=preview["preview_id"]), request_for())
        self.assertEqual(stale.exception.status_code, 409)
        self.assertEqual(list_directory(self.db, 1, 20)["total"], 0)

    def test_department_mapping_requires_real_ims_department_and_known_source_code(self):
        with self.assertRaises(HTTPException) as denied:
            asyncio.run(hrm_routes.save_department_mapping(
                hrm_routes.DepartmentMappingRequest(department_code="NOPE", ma_phong_ban=9, expected_ma_phong_ban=None, reason="test"),
                request_for("HR"), self.db,
            ))
        self.assertEqual(denied.exception.status_code, 403)
        with self.assertRaises(HTTPException) as unknown:
            asyncio.run(hrm_routes.save_department_mapping(
                hrm_routes.DepartmentMappingRequest(department_code="NOPE", ma_phong_ban=9, expected_ma_phong_ban=None, reason="test"),
                request_for(), self.db,
            ))
        self.assertEqual(unknown.exception.status_code, 422)

    def test_employee_override_precedence_bulk_update_reset_and_audit(self):
        self.provider.records.append({**self.records[0], "external_employee_id": "NV002", "full_name": "Second Employee"})
        with self.assertRaises(HTTPException) as denied:
            self.call(
                hrm_routes.save_employee_department_mapping,
                hrm_routes.EmployeeDepartmentMappingRequest(
                    employees=[{"external_employee_id": "NV001", "expected_revision": None}],
                    ma_phong_ban=10, reason="HR cannot change Admin mappings.",
                ),
                request_for("HR"),
            )
        self.assertEqual(denied.exception.status_code, 403)
        created = self.call(
            hrm_routes.save_employee_department_mapping,
            hrm_routes.EmployeeDepartmentMappingRequest(
                employees=[{"external_employee_id": "NV001", "expected_revision": None}],
                ma_phong_ban=10, reason="Admin assigned this employee to AI/Data.",
            ),
            request_for(),
        )
        self.assertEqual(created["updated"], 1)
        with self.assertRaises(HTTPException) as stale_revision:
            self.call(
                hrm_routes.save_employee_department_mapping,
                hrm_routes.EmployeeDepartmentMappingRequest(
                    employees=[{"external_employee_id": "NV001", "expected_revision": None}],
                    ma_phong_ban=9, reason="An outdated version must not overwrite an exception.",
                ),
                request_for(),
            )
        self.assertEqual(stale_revision.exception.status_code, 409)
        context = load_sync_context(self.db)
        preview = preview_rows(self.provider.records, context)
        self.assertEqual((preview[0]["mapped_department_id"], preview[0]["mapping_source"]), (10, "EMPLOYEE_OVERRIDE"))
        self.assertEqual((preview[1]["mapped_department_id"], preview[1]["mapping_source"]), (9, "DEPARTMENT_DEFAULT"))

        mappings = self.call(hrm_routes.get_employee_department_mappings, request_for())
        revisions = {item["external_employee_id"]: item["override_revision"] for item in mappings["employees"]}
        bulk = self.call(
            hrm_routes.save_employee_department_mapping,
            hrm_routes.EmployeeDepartmentMappingRequest(
                employees=[
                    {"external_employee_id": "NV001", "expected_revision": revisions["NV001"]},
                    {"external_employee_id": "NV002", "expected_revision": None},
                ],
                ma_phong_ban=10, reason="Admin confirmed the selected batch.",
            ),
            request_for(),
        )
        self.assertEqual(bulk["total"], 2)
        self.assertEqual(bulk["updated"], 1)

        refreshed = self.call(hrm_routes.get_employee_department_mappings, request_for())
        nv001 = next(item for item in refreshed["employees"] if item["external_employee_id"] == "NV001")
        reset = self.call(
            hrm_routes.reset_employee_department_mapping,
            hrm_routes.EmployeeDepartmentResetRequest(
                external_employee_id="NV001", expected_revision=nv001["override_revision"],
                reason="Return to the current TECH default.",
            ),
            request_for(),
        )
        self.assertTrue(reset["deleted"])
        after_reset = preview_rows(self.provider.records, load_sync_context(self.db))
        self.assertEqual(after_reset[0]["mapped_department_id"], 9)
        self.assertEqual(after_reset[0]["mapping_source"], "DEPARTMENT_DEFAULT")
        audit = hrm_routes.get_department_mapping_audit(request_for(), page=1, page_size=20, db=self.db)
        self.assertGreaterEqual(audit["total"], 3)
        self.assertTrue(all(row["actor_name"] == "Admin Test" for row in audit["items"]))

    def test_changed_hrm_department_requires_override_review(self):
        self.call(
            hrm_routes.save_employee_department_mapping,
            hrm_routes.EmployeeDepartmentMappingRequest(
                employees=[{"external_employee_id": "NV001", "expected_revision": None}],
                ma_phong_ban=10, reason="Approved individual exception.",
            ),
            request_for(),
        )
        self.provider.records[0]["department_code"] = "DATA"
        preview = self.call(hrm_routes.create_preview, request_for())
        row = preview["rows"][0]
        self.assertEqual(row["action"], "CONFLICT")
        self.assertEqual(row["mapping_status"], "NEEDS_REVIEW")
        self.assertIsNone(row["mapped_department_id"])

    def test_mapping_change_invalidates_old_preview_and_global_change_is_audited(self):
        preview = self.call(hrm_routes.create_preview, request_for())
        updated = self.call(
            hrm_routes.save_department_mapping,
            hrm_routes.DepartmentMappingRequest(
                department_code="TECH", ma_phong_ban=10, expected_ma_phong_ban=9,
                reason="UAT validation of a changed department default.",
            ),
            request_for(),
        )
        self.assertFalse(updated["unchanged"])
        with self.assertRaises(HTTPException) as stale:
            self.call(hrm_routes.apply_sync, hrm_routes.ApplySyncRequest(preview_id=preview["preview_id"]), request_for())
        self.assertEqual(stale.exception.status_code, 409)
        audit = hrm_routes.get_department_mapping_audit(request_for(), page=1, page_size=20, db=self.db)
        self.assertEqual(audit["items"][0]["event_type"], "UPDATED")
        self.assertEqual(audit["items"][0]["reason"], "UAT validation of a changed department default.")

    def test_global_mapping_can_be_removed_with_audited_reason(self):
        result = self.call(
            hrm_routes.reset_department_mapping,
            hrm_routes.DepartmentMappingResetRequest(
                department_code="TECH", expected_ma_phong_ban=9,
                reason="The default is no longer approved for this source department.",
            ),
            request_for(),
        )
        self.assertTrue(result["deleted"])
        row = preview_rows(self.provider.records, load_sync_context(self.db))[0]
        self.assertEqual(row["action"], "CONFLICT")
        self.assertEqual(row["mapping_status"], "UNMAPPED")
        audit = hrm_routes.get_department_mapping_audit(request_for(), page=1, page_size=20, db=self.db)
        self.assertEqual(audit["items"][0]["event_type"], "DELETED")

    def test_concurrent_sync_lease_rejects_second_apply(self):
        with patch.object(database, "DATABASE_BACKEND", "sqlite"):
            first = acquire_sync_lock(self.db)
            second = acquire_sync_lock(self.db)
        self.assertTrue(first)
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()
