"""Provider-neutral HRM contract and safe, non-mutating import preview rules.

No HRM vendor or API contract is configured in this application yet. This module
deliberately contains no network client or write path; a vendor adapter must be
implemented and reviewed before connection or synchronization can be enabled.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HRMEmployeeRecord(BaseModel):
    """Canonical record an explicitly implemented vendor adapter must return."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_employee_id: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    work_email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    department: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    employment_status: Literal["active", "inactive"]

    @field_validator("external_employee_id", "full_name")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized or any(ord(char) < 32 for char in normalized):
            raise ValueError("Giá trị bắt buộc không hợp lệ.")
        return normalized

    @field_validator("work_email", "phone", "department", "job_title", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        return normalized or None

    @field_validator("work_email")
    @classmethod
    def validate_work_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Email công việc không hợp lệ.")
        return value.casefold()


class HRMProvider(Protocol):
    """Interface for a vendor-specific adapter after its contract is approved."""

    provider_name: str

    async def test_connection(self) -> None:
        """Raise a safe, non-secret-bearing error if the provider is unavailable."""

    async def fetch_employees(self) -> Sequence[HRMEmployeeRecord]:
        """Return validated canonical records, including stable external IDs."""


def validate_employee_batch(records: Sequence[HRMEmployeeRecord | Mapping[str, Any]]) -> list[HRMEmployeeRecord]:
    """Validate a provider batch and reject duplicate external IDs before preview."""
    employees = [record if isinstance(record, HRMEmployeeRecord) else HRMEmployeeRecord.model_validate(record)
                 for record in records]
    seen_ids: set[str] = set()
    for employee in employees:
        normalized_id = employee.external_employee_id.casefold()
        if normalized_id in seen_ids:
            raise ValueError("HRM trả về mã nhân viên ngoài bị trùng.")
        seen_ids.add(normalized_id)
    return employees


def build_import_preview(
    records: Sequence[HRMEmployeeRecord | Mapping[str, Any]],
    linked_users_by_external_id: Mapping[str, int],
    user_ids_by_email: Mapping[str, Sequence[int]],
) -> list[dict[str, Any]]:
    """Build review-only actions; email matches are never linked automatically."""
    employees = validate_employee_batch(records)
    linked_ids = {key.casefold(): value for key, value in linked_users_by_external_id.items()}
    email_index = {key.strip().casefold(): list(value) for key, value in user_ids_by_email.items()}
    linked_user_counts = Counter(linked_ids.values())
    batch_email_counts = Counter(employee.work_email for employee in employees if employee.work_email)
    preview: list[dict[str, Any]] = []

    for employee in employees:
        linked_user_id = linked_ids.get(employee.external_employee_id.casefold())
        email_matches = email_index.get(employee.work_email or "", [])
        if linked_user_id is not None and linked_user_counts[linked_user_id] > 1:
            action = "CONFLICT"
            candidate_user_id = linked_user_id
            reason = "Nhiều mã nhân viên HRM đang trỏ tới cùng một tài khoản IMS; cần xử lý thủ công."
        elif employee.work_email and batch_email_counts[employee.work_email] > 1:
            action = "CONFLICT"
            candidate_user_id = None
            reason = "Nhiều hồ sơ HRM trong lô dùng cùng email; cần đối chiếu mã nhân viên."
        elif linked_user_id is not None:
            action = "REVIEW_LINKED_PROFILE"
            candidate_user_id = linked_user_id
            reason = "Đã liên kết bằng mã nhân viên ngoài ổn định; cần xem trước và xác nhận thay đổi."
        elif len(email_matches) == 1:
            action = "MANUAL_LINK_REVIEW"
            candidate_user_id = email_matches[0]
            reason = "Email khớp một tài khoản IMS; chỉ gợi ý đối chiếu, không tự ghép tài khoản."
        elif len(email_matches) > 1:
            action = "CONFLICT"
            candidate_user_id = None
            reason = "Email khớp nhiều tài khoản IMS; cần xử lý thủ công."
        else:
            action = "NEW_RECORD_REVIEW"
            candidate_user_id = None
            reason = "Chưa có liên kết mã nhân viên; cần xác nhận quy tắc tạo/liên kết tài khoản."

        warnings = []
        if employee.employment_status == "inactive":
            warnings.append("Trạng thái nghỉ việc không tự khóa tài khoản IMS hoặc gỡ phân công Mentor.")
        if employee.department:
            warnings.append("Thay đổi phòng ban cần chính sách được duyệt; không viết lại lịch sử phân công.")

        preview.append({
            "external_employee_id": employee.external_employee_id,
            "full_name": employee.full_name,
            "work_email": employee.work_email,
            "department": employee.department,
            "job_title": employee.job_title,
            "employment_status": employee.employment_status,
            "action": action,
            "candidate_user_id": candidate_user_id,
            "reason": reason,
            "warnings": warnings,
            "requires_confirmation": True,
            "applied": False,
        })
    return preview


HRM_SETUP_REQUIREMENTS = [
    "Tên nhà cung cấp HRM và tài liệu API chính thức (endpoint, schema, phân trang, giới hạn gọi).",
    "Tenant sandbox/test và danh sách hostname HTTPS được phép kết nối.",
    "Phương thức xác thực và bí mật được cấp qua secret store, không nhập/lưu trong giao diện IMS.",
    "Mã nhân viên ngoài ổn định cùng ánh xạ trường và quyền sở hữu dữ liệu đã được duyệt.",
    "Quy tắc xử lý trùng, đổi email/phòng ban và nhân viên nghỉ việc đã được HR duyệt.",
    "Provider adapter đã triển khai, kiểm thử bảo mật và xác minh với sandbox của nhà cung cấp.",
]

HRM_SYNC_SCOPE = [
    "Mã nhân viên HRM ổn định",
    "Họ tên, email công việc, số điện thoại",
    "Phòng ban và chức danh công việc để đối chiếu hồ sơ nhân viên",
    "Trạng thái nhân sự chỉ đưa vào xem xét thủ công",
]

HRM_EXCLUDED_SCOPE = [
    "Mật khẩu, thông tin đăng nhập, vai trò và quyền IMS",
    "Phân công Mentor/TTS và lịch sử chương trình thực tập",
    "Đánh giá, chấm công, nghỉ phép và phụ cấp",
    "Hồ sơ TTS và mọi thao tác xóa/khóa tài khoản tự động",
]


def get_hrm_status() -> dict[str, Any]:
    """Return current repository readiness without exposing credentials."""
    return {
        "state": "NOT_CONFIGURED",
        "configured": False,
        "provider_name": None,
        "can_test_connection": False,
        "can_preview": False,
        "can_sync": False,
        "sync_history_available": False,
        "missing_requirements": list(HRM_SETUP_REQUIREMENTS),
        "sync_scope": list(HRM_SYNC_SCOPE),
        "excluded_scope": list(HRM_EXCLUDED_SCOPE),
        "message": "Chưa cấu hình HRM: Product Backlog/source chưa cung cấp nhà cung cấp, API contract hoặc sandbox.",
    }
