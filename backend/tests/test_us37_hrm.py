"""Provider-neutral US37 contract and readiness checks; no live HRM/MySQL calls."""
import unittest
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError

from app.hrm_integration import HRMEmployeeRecord, build_import_preview, get_hrm_status, validate_employee_batch
from app.routes.hrm_routes import get_status


def request_for(role):
    return SimpleNamespace(state=SimpleNamespace(current_user={"vai_tro": role}))


class US37HRMContractTests(unittest.TestCase):
    def employee(self, **changes):
        record = {
            "external_employee_id": " EMP-001 ",
            "full_name": "  Nguyen   An  ",
            "work_email": " AN@EXAMPLE.TEST ",
            "phone": " 0900 000 000 ",
            "department": " Data  Platform ",
            "job_title": " Analyst ",
            "employment_status": "active",
        }
        record.update(changes)
        return record

    def test_contract_normalizes_values_and_rejects_unknown_fields(self):
        record = HRMEmployeeRecord.model_validate(self.employee())
        self.assertEqual(record.external_employee_id, "EMP-001")
        self.assertEqual(record.full_name, "Nguyen An")
        self.assertEqual(record.work_email, "an@example.test")
        with self.assertRaises(ValidationError):
            HRMEmployeeRecord.model_validate(self.employee(password="must-not-enter-IMS"))
        with self.assertRaises(ValidationError):
            HRMEmployeeRecord.model_validate(self.employee(external_employee_id="   "))

    def test_batch_rejects_duplicate_external_ids_case_insensitively(self):
        with self.assertRaisesRegex(ValueError, "mã nhân viên ngoài bị trùng"):
            validate_employee_batch([
                self.employee(external_employee_id="EMP-001"),
                self.employee(external_employee_id="emp-001"),
            ])

    def test_email_only_match_is_review_suggestion_not_automatic_link(self):
        preview = build_import_preview(
            [self.employee()],
            linked_users_by_external_id={},
            user_ids_by_email={"an@example.test": [42]},
        )[0]
        self.assertEqual(preview["action"], "MANUAL_LINK_REVIEW")
        self.assertEqual(preview["candidate_user_id"], 42)
        self.assertTrue(preview["requires_confirmation"])
        self.assertFalse(preview["applied"])

    def test_linked_inactive_record_does_not_revoke_access_or_assignments(self):
        preview = build_import_preview(
            [self.employee(employment_status="inactive")],
            linked_users_by_external_id={"EMP-001": 42},
            user_ids_by_email={},
        )[0]
        self.assertEqual(preview["action"], "REVIEW_LINKED_PROFILE")
        self.assertTrue(any("không tự khóa" in warning for warning in preview["warnings"]))
        self.assertFalse(preview["applied"])

    def test_repeated_email_or_link_target_is_flagged_as_conflict(self):
        duplicate_email = build_import_preview(
            [
                self.employee(external_employee_id="EMP-001"),
                self.employee(external_employee_id="EMP-002"),
            ],
            linked_users_by_external_id={},
            user_ids_by_email={"an@example.test": [42]},
        )
        self.assertEqual([item["action"] for item in duplicate_email], ["CONFLICT", "CONFLICT"])

        duplicate_link = build_import_preview(
            [self.employee(work_email=None)],
            linked_users_by_external_id={"EMP-001": 42, "EMP-OTHER": 42},
            user_ids_by_email={},
        )[0]
        self.assertEqual(duplicate_link["action"], "CONFLICT")

    def test_unconfigured_status_is_honest_and_contains_no_configuration_values(self):
        result = get_hrm_status()
        self.assertEqual(result["state"], "NOT_CONFIGURED")
        self.assertFalse(result["can_test_connection"])
        self.assertFalse(result["can_preview"])
        self.assertFalse(result["can_sync"])
        self.assertIsNone(result["provider_name"])
        self.assertGreater(len(result["missing_requirements"]), 0)
        self.assertNotIn("top-secret-test-token", str(result))

    def test_status_route_is_admin_only(self):
        self.assertEqual(get_status(request_for("Admin"))["state"], "NOT_CONFIGURED")
        for role in ("HR", "Mentor", "ThucTapSinh"):
            with self.subTest(role=role), self.assertRaises(HTTPException) as denied:
                get_status(request_for(role))
            self.assertEqual(denied.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
