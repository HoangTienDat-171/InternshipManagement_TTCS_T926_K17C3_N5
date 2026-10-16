import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.hrm_sandbox import app


class US37SandboxManagementApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patch = patch.dict(os.environ, {
            "HRM_SANDBOX_DATABASE_PATH": os.path.join(self.temp_dir.name, "sandbox.sqlite3"),
            "HRM_SANDBOX_API_KEY": "us37-sandbox-management-test-key",
        }, clear=False)
        self.env_patch.start()
        self.client = TestClient(app)
        self.client.__enter__()
        self.headers = {"Authorization": "Bearer us37-sandbox-management-test-key"}

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

        listed = self.client.get("/api/v1/employees?q=NV001&employment_status=ACTIVE", headers=self.headers)
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
        self.assertEqual(update["before"]["department_code"], "DATA")
        self.assertEqual(update["after"]["department_code"], "OPS")

        delete = self.client.delete("/api/v1/employees/NV099", headers=self.headers)
        self.assertEqual(delete.status_code, 405)

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
