import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.hrm_sandbox import _safe_audit_reason, app


class US37SandboxManagementApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patch = patch.dict(os.environ, {
            "HRM_SANDBOX_DATABASE_PATH": os.path.join(self.temp_dir.name, "sandbox.sqlite3"),
            "HRM_SANDBOX_API_KEY": "us37-sandbox-service-test-key-0123456789",
            "HRM_SANDBOX_ADMIN_API_KEY": "us37-sandbox-admin-test-key-9876543210",
        }, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)
        self.client.__enter__()
        self.headers = {"Authorization": "Bearer us37-sandbox-admin-test-key-9876543210"}
        self.service_headers = {"Authorization": "Bearer us37-sandbox-service-test-key-0123456789"}
        for code, name in (("DATA", "Dữ liệu"), ("OPS", "Vận hành"), ("TECH", "Kỹ thuật")):
            response = self.client.post("/api/v1/departments", headers=self.headers, json={
                "department_code": code, "department_name": name,
            })
            self.assertEqual(response.status_code, 201, response.text)
        for employee_id, name, department in (
            ("NV001", "Nguyễn An", "DATA"),
            ("NV003", "Lê Chi", "DATA"),
            ("NV008", "Ngô Minh", "DATA"),
            ("NV005", "Vũ Hà", "OPS"),
        ):
            response = self.client.post("/api/v1/employees", headers=self.headers, json={
                "employee_id": employee_id,
                "full_name": name,
                "work_email": f"{employee_id.lower()}@hrm-sandbox.test",
                "department_code": department,
                "employment_status": "ACTIVE",
            })
            self.assertEqual(response.status_code, 201, response.text)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_reads_are_protected_and_employee_management_is_audited(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Danh sách nhân viên", page.text)
        self.assertNotIn("us37-sandbox-management-test-key", page.text)

        denied = self.client.get("/api/v1/departments")
        self.assertEqual(denied.status_code, 401)
        service_employee_write = self.client.post("/api/v1/employees", headers=self.service_headers, json={
            "employee_id": "NV099", "full_name": "No admin scope",
        })
        self.assertEqual(service_employee_write.status_code, 403)
        service_audit_read = self.client.get("/api/v1/changes", headers=self.service_headers)
        self.assertEqual(service_audit_read.status_code, 403)

        listed = self.client.get("/api/v1/employees?q=NV001&employment_status=ACTIVE", headers=self.service_headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 1)
        self.assertEqual(listed.json()["items"][0]["employee_id"], "NV001")

        created = self.client.post("/api/v1/employees", headers=self.headers, json={
            "employee_id": "NV099", "full_name": "  UAT   Nhân viên  ",
            "work_email": "NV099@HRM-SANDBOX.TEST", "department_code": "DATA",
            "job_title": "Chuyên viên", "employment_status": "ACTIVE",
        })
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["full_name"], "UAT Nhân viên")
        self.assertEqual(created.json()["work_email"], "nv099@hrm-sandbox.test")
        self.assertEqual(created.json()["department_name"], "Dữ liệu")

        duplicate_id = self.client.post("/api/v1/employees", headers=self.headers, json={
            "employee_id": "nv099", "full_name": "Người trùng mã",
        })
        self.assertEqual(duplicate_id.status_code, 409)
        duplicate_email = self.client.post("/api/v1/employees", headers=self.headers, json={
            "employee_id": "NV098", "full_name": "Người trùng email", "work_email": "NV099@hrm-sandbox.test",
        })
        self.assertEqual(duplicate_email.status_code, 409)

        employee = self.client.get("/api/v1/employees/NV099", headers=self.headers).json()
        missing_version = self.client.patch("/api/v1/employees/NV099", headers=self.headers, json={"job_title": "Chuyên viên cao cấp"})
        self.assertEqual(missing_version.status_code, 428)
        changed = self.client.patch("/api/v1/employees/NV099", headers=self.headers, json={
            "job_title": "Chuyên viên cao cấp", "department_code": "OPS",
            "expected_updated_at": employee["updated_at"], "reason": "Điều chuyển trong UAT",
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["department_name"], "Vận hành")

        stale = self.client.patch("/api/v1/employees/NV099", headers=self.headers, json={
            "job_title": "Chức danh cũ", "expected_updated_at": employee["updated_at"],
        })
        self.assertEqual(stale.status_code, 409)
        immutable_id = self.client.patch("/api/v1/employees/NV099", headers=self.headers, json={
            "employee_id": "NV100", "expected_updated_at": changed.json()["updated_at"],
        })
        self.assertEqual(immutable_id.status_code, 422)

        history = self.client.get("/api/v1/changes?entity_type=EMPLOYEE&entity_id=NV099", headers=self.headers)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["total"], 2)
        update = history.json()["items"][0]
        self.assertNotIn("before", update)
        self.assertNotIn("after", update)
        self.assertNotIn("before_json", update)
        self.assertNotIn("after_json", update)
        self.assertEqual(update["actor_label"], "Quản trị Sandbox")
        self.assertIn("Mã phòng ban", update["changed_fields"])
        detail = self.client.get(f"/api/v1/changes/{update['id']}", headers=self.headers)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual({change["label"] for change in detail.json()["changes"]}, {"Mã phòng ban", "Tên phòng ban", "Chức danh"})
        self.assertNotIn("password", detail.text.casefold())
        self.assertNotIn("api_key", detail.text.casefold())

        changed_email = self.client.patch("/api/v1/employees/NV099", headers=self.headers, json={
            "work_email": "private.nv099@hrm-sandbox.test", "expected_updated_at": changed.json()["updated_at"],
        })
        self.assertEqual(changed_email.status_code, 200)
        email_event = self.client.get("/api/v1/changes?entity_id=NV099&page=1&page_size=1", headers=self.headers).json()["items"][0]
        email_detail = self.client.get(f"/api/v1/changes/{email_event['id']}", headers=self.headers).json()
        email_diff = next(change for change in email_detail["changes"] if change["field"] == "work_email")
        self.assertTrue(email_diff["sensitive"])
        self.assertNotEqual(email_diff["after"], "private.nv099@hrm-sandbox.test")
        revealed_email = self.client.get(f"/api/v1/changes/{email_event['id']}?show_sensitive=true", headers=self.headers).json()
        self.assertEqual(next(change for change in revealed_email["changes"] if change["field"] == "work_email")["after"], "private.nv099@hrm-sandbox.test")

        delete = self.client.delete("/api/v1/employees/NV099", headers=self.headers)
        self.assertEqual(delete.status_code, 405)
        delete_audit = self.client.delete(f"/api/v1/changes/{update['id']}", headers=self.headers)
        self.assertEqual(delete_audit.status_code, 405)

    def test_audit_filters_and_status_actions_are_persisted_only_on_success(self):
        employee = self.client.get("/api/v1/employees/NV001", headers=self.headers).json()
        deactivated = self.client.patch("/api/v1/employees/NV001", headers=self.headers, json={
            "employment_status": "INACTIVE", "expected_updated_at": employee["updated_at"],
        })
        self.assertEqual(deactivated.status_code, 200)
        reactivated = self.client.patch("/api/v1/employees/NV001", headers=self.headers, json={
            "employment_status": "ACTIVE", "expected_updated_at": deactivated.json()["updated_at"],
        })
        self.assertEqual(reactivated.status_code, 200)
        stale_before = self.client.get("/api/v1/changes?entity_id=NV001", headers=self.headers).json()["total"]
        stale = self.client.patch("/api/v1/employees/NV001", headers=self.headers, json={
            "job_title": "Stale update", "expected_updated_at": employee["updated_at"],
        })
        self.assertEqual(stale.status_code, 409)
        stale_after = self.client.get("/api/v1/changes?entity_id=NV001", headers=self.headers).json()["total"]
        self.assertEqual(stale_before, stale_after)

        filtered = self.client.get("/api/v1/changes?entity_id=NV001&actor=sandbox_admin_api_key&action=REACTIVATE&page=1&page_size=1", headers=self.headers)
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["total"], 1)
        self.assertEqual(filtered.json()["items"][0]["action"], "REACTIVATE")
        invalid_range = self.client.get("/api/v1/changes?date_from=2026-10-20&date_to=2026-10-01", headers=self.headers)
        self.assertEqual(invalid_range.status_code, 422)

    def test_console_uses_text_nodes_and_no_raw_history_json(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Content-Security-Policy", page.headers)
        self.assertIn("b\u1ed9 nh\u1edb tab hi\u1ec7n t\u1ea1i", page.text)
        self.assertIn("\u0111\u1ec3 t\u1ef1 \u0111\u1ed9ng k\u1ebft n\u1ed1i", page.text)
        self.assertIn("textContent", page.text)
        self.assertNotIn("innerHTML", page.text)
        self.assertNotIn("localStorage.setItem('hrmSandboxApiKey'", page.text)
        self.assertIn("sessionStorage.getItem(API_KEY_SESSION_STORAGE)", page.text)
        self.assertIn("sessionStorage.setItem(API_KEY_SESSION_STORAGE, apiKey)", page.text)
        self.assertNotIn("localStorage.setItem(API_KEY_SESSION_STORAGE", page.text)
        self.assertNotIn("JSON.stringify({before:", page.text)

    def test_hostile_audit_note_is_returned_as_text_for_safe_dom_rendering(self):
        employee = self.client.get("/api/v1/employees/NV001", headers=self.headers).json()
        hostile_note = '<img src=x onerror="alert(1)">'
        updated = self.client.patch("/api/v1/employees/NV001", headers=self.headers, json={
            "job_title": "Security Audit UAT",
            "expected_updated_at": employee["updated_at"],
            "reason": hostile_note,
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        event = self.client.get("/api/v1/changes?entity_id=NV001&page_size=1", headers=self.headers).json()["items"][0]
        detail = self.client.get(f"/api/v1/changes/{event['id']}", headers=self.headers).json()
        self.assertEqual(detail["reason"], hostile_note)
        page = self.client.get("/").text
        self.assertIn("el.textContent = text", page)
        self.assertNotIn("innerHTML", page)

    def test_audit_reason_masks_contact_info_and_secret_material(self):
        private_email = "person@example.test"
        private_phone = "0901234567"
        opaque_token = "A1b2C3d4E5f6G7h8J9k0L1m2N3o4P5q6R7s8T9u0V1w2"
        reason = (
            f"HR review {private_email} {private_phone} api_key=short-secret "
            f"Bearer {opaque_token} db=mysql://user:password@localhost/hrm"
        )

        safe = _safe_audit_reason(reason)

        self.assertNotIn(private_email, safe)
        self.assertNotIn(private_phone, safe)
        self.assertNotIn("short-secret", safe)
        self.assertNotIn(opaque_token, safe)
        self.assertNotIn("user:password", safe)

    def test_department_catalog_changes_update_employees_and_keep_mapping_warning(self):
        departments = self.client.get("/api/v1/departments", headers=self.headers).json()["items"]
        data = next(item for item in departments if item["department_code"] == "DATA")
        renamed = self.client.patch("/api/v1/departments/DATA", headers=self.headers, json={
            "department_name": "Phòng Dữ liệu UAT", "expected_updated_at": data["updated_at"],
            "reason": "Kiểm tra đổi tên danh mục",
        })
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(self.client.get("/api/v1/employees/NV003", headers=self.headers).json()["department_name"], "Phòng Dữ liệu UAT")

        renamed_dept = renamed.json()
        no_ack = self.client.patch("/api/v1/departments/DATA", headers=self.headers, json={
            "department_code": "ANALYTICS", "expected_updated_at": renamed_dept["updated_at"],
        })
        self.assertEqual(no_ack.status_code, 409)

        changed_code = self.client.patch("/api/v1/departments/DATA", headers=self.headers, json={
            "department_code": "ANALYTICS", "expected_updated_at": renamed_dept["updated_at"],
            "confirm_ims_mapping_impact": True,
        })
        self.assertEqual(changed_code.status_code, 200, changed_code.text)
        self.assertIn("mapping_warning", changed_code.json())
        employee = self.client.get("/api/v1/employees/NV008", headers=self.headers).json()
        self.assertEqual(employee["department_code"], "ANALYTICS")
        self.assertEqual(employee["department_name"], "Phòng Dữ liệu UAT")

        blocked_deactivation = self.client.patch("/api/v1/departments/OPS", headers=self.headers, json={
            "is_active": False,
            "expected_updated_at": next(item["updated_at"] for item in self.client.get("/api/v1/departments", headers=self.headers).json()["items"] if item["department_code"] == "OPS"),
        })
        self.assertEqual(blocked_deactivation.status_code, 409)

        added = self.client.post("/api/v1/departments", headers=self.headers, json={
            "department_code": "LEGAL", "department_name": "Pháp chế",
        })
        self.assertEqual(added.status_code, 201, added.text)
        self.assertEqual(added.json()["employee_count"], 0)


if __name__ == "__main__":
    unittest.main()
