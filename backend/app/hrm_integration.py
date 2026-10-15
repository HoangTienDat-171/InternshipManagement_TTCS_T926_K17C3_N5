"""Canonical HRM records and deterministic, reviewable synchronization rules."""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class HRMEmployeeRecord(BaseModel):
    """Canonical record an explicitly implemented vendor adapter must return."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_employee_id: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    work_email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    department_code: str | None = Field(default=None, max_length=128)
    department: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    employment_status: Literal["active", "inactive"]
    source_updated_at: str | None = Field(default=None, max_length=64)

    @field_validator("external_employee_id", "full_name")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized or any(ord(char) < 32 for char in normalized):
            raise ValueError("Giá trị bắt buộc không hợp lệ.")
        return normalized

    @field_validator("work_email", "phone", "department_code", "department", "job_title", "source_updated_at", mode="before")
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

    @field_validator("department_code")
    @classmethod
    def normalize_department_code(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("source_updated_at")
    @classmethod
    def validate_source_updated_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Thời gian cập nhật nguồn không hợp lệ.") from exc
        return value

    @field_validator("employment_status", mode="before")
    @classmethod
    def normalize_employment_status(cls, value: Any) -> Any:
        return value.casefold() if isinstance(value, str) else value


class HRMProvider(Protocol):
    """Interface for a vendor-specific adapter after its contract is approved."""

    provider_name: str

    async def test_connection(self) -> None:
        """Raise a safe, non-secret-bearing error if the provider is unavailable."""

    async def fetch_employees(self) -> Sequence[Mapping[str, Any]]:
        """Return paginated source records for per-record preview validation."""


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


def build_sync_preview(
    records: Sequence[Mapping[str, Any]],
    existing_by_external_id: Mapping[str, Mapping[str, Any]],
    department_mappings: Mapping[str, Mapping[str, Any]],
    ims_user_ids_by_email: Mapping[str, Sequence[int]],
) -> list[dict[str, Any]]:
    """Classify source rows without writing accounts, roles, or assignments."""
    parsed: list[tuple[Mapping[str, Any], HRMEmployeeRecord | None, str | None]] = []
    for raw in records:
        try:
            employee = HRMEmployeeRecord.model_validate(raw)
            parsed.append((raw, employee, None))
        except ValidationError as exc:
            errors = exc.errors(include_input=False)
            detail = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in errors[:3]
            )
            parsed.append((raw, None, detail or "Bản ghi HRM không hợp lệ."))

    id_counts = Counter(
        employee.external_employee_id.casefold()
        for _, employee, _ in parsed if employee is not None
    )
    email_counts = Counter(
        employee.work_email for _, employee, _ in parsed
        if employee is not None and employee.work_email
    )
    existing = {key.casefold(): dict(value) for key, value in existing_by_external_id.items()}
    mappings = {key.casefold(): dict(value) for key, value in department_mappings.items()}
    ims_emails = {key.strip().casefold(): list(value) for key, value in ims_user_ids_by_email.items()}
    preview: list[dict[str, Any]] = []

    for raw, employee, validation_error in parsed:
        external_id = employee.external_employee_id if employee else str(raw.get("external_employee_id") or "")
        row: dict[str, Any] = {
            "external_employee_id": external_id or None,
            "full_name": employee.full_name if employee else str(raw.get("full_name") or ""),
            "work_email": employee.work_email if employee else str(raw.get("work_email") or "") or None,
            "phone": employee.phone if employee else str(raw.get("phone") or "") or None,
            "department_code": employee.department_code if employee else str(raw.get("department_code") or "") or None,
            "department": employee.department if employee else str(raw.get("department") or "") or None,
            "job_title": employee.job_title if employee else str(raw.get("job_title") or "") or None,
            "employment_status": employee.employment_status if employee else str(raw.get("employment_status") or "").casefold() or None,
            "source_updated_at": employee.source_updated_at if employee else str(raw.get("source_updated_at") or "") or None,
            "mapped_department_id": None,
            "mapped_department_name": None,
            "action": "INVALID",
            "reason": validation_error or "Bản ghi HRM không hợp lệ.",
            "warnings": [],
            "candidate_user_ids": [],
        }
        if employee is None:
            preview.append(row)
            continue

        id_key = employee.external_employee_id.casefold()
        email_key = employee.work_email or ""
        department = mappings.get((employee.department_code or "").casefold())
        existing_record = existing.get(id_key)
        row["mapped_department_id"] = department.get("ma_phong_ban") if department else None
        row["mapped_department_name"] = department.get("ten_phong_ban") if department else None

        if id_counts[id_key] > 1:
            row.update(action="INVALID", reason="Mã nhân viên ngoài bị lặp trong dữ liệu HRM.")
        elif email_key and email_counts[email_key] > 1:
            row.update(action="CONFLICT", reason="Email công việc bị lặp trong lô HRM; cần đối chiếu thủ công.")
        elif employee.department and not employee.department_code:
            row.update(action="CONFLICT", reason="Có tên phòng ban nhưng thiếu mã phòng ban ổn định.")
        elif employee.department_code and not department:
            row.update(action="CONFLICT", reason="Mã phòng ban HRM chưa được ánh xạ sang danh mục IMS.")
        elif email_key and ims_emails.get(email_key):
            row["candidate_user_ids"] = ims_emails[email_key]
            row.update(action="CONFLICT", reason="Email khớp tài khoản IMS; cần xác nhận liên kết thủ công, không tự ghép tài khoản.")
        else:
            expected = {
                "full_name": employee.full_name,
                "work_email": employee.work_email,
                "phone": employee.phone,
                "department_code": employee.department_code,
                "department": employee.department,
                "ma_phong_ban": department.get("ma_phong_ban") if department else None,
                "job_title": employee.job_title,
                "employment_status": employee.employment_status,
                "source_updated_at": employee.source_updated_at,
            }
            if existing_record is None:
                row.update(action="NEW", reason="Nhân viên HRM chưa có trong danh bạ đồng bộ IMS.")
            else:
                changed = any(existing_record.get(key) != value for key, value in expected.items())
                row.update(
                    action="UPDATE" if changed else "UNCHANGED",
                    reason="Thông tin nguồn thay đổi; cập nhật bản ghi HRM đã đồng bộ." if changed else "Không có thay đổi so với lần đồng bộ trước.",
                )

        if employee.employment_status == "inactive":
            row["warnings"].append("Nhân viên đã nghỉ việc; chỉ cập nhật trạng thái hồ sơ HRM, không khóa tài khoản hoặc gỡ phân công IMS.")
        if employee.department_code:
            row["warnings"].append("Phòng ban được xác định bằng mã HRM đã ánh xạ; không sửa lịch sử chương trình hoặc phân công Mentor.")
        preview.append(row)
    return preview


HRM_SETUP_REQUIREMENTS = [
    "Đặt HRM_PROVIDER=sandbox và HRM_SANDBOX_BASE_URL trỏ tới dịch vụ loopback.",
    "Cấp HRM_SANDBOX_API_KEY qua environment; không nhập hoặc hiển thị trong giao diện.",
    "Chạy migration US37 trên database IMS thử nghiệm trước khi đồng bộ.",
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
