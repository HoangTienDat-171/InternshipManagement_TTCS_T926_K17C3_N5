from datetime import date, time
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from typing import Optional, List, Literal


class AllowanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ky: str = Field(pattern=r"^[1-9][0-9]{3}-(0[1-9]|1[0-2])$")
    so_tien: Decimal = Field(ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
    ghi_chu: str = Field(default="", max_length=1000)

    @field_validator("so_tien", mode="before")
    @classmethod
    def exact_amount(cls, value):
        if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
            raise ValueError("Số tiền phải là chuỗi thập phân hoặc số nguyên, tối đa 2 chữ số lẻ.")
        return value

    @field_validator("ghi_chu")
    @classmethod
    def trim_note(cls, value):
        return value.strip()


class AllowanceCreate(AllowanceUpdate):
    ma_ung_tuyen: StrictInt = Field(gt=0)


class AllowanceReceiptReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    noi_dung: str = Field(min_length=1, max_length=2000)

    @field_validator("noi_dung")
    @classmethod
    def trim_report(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Vui lòng nhập nội dung phản ánh.")
        return value


class AllowanceReportUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trang_thai_xu_ly: Literal["DangXuLy", "DaXuLy"]
    ghi_chu_xu_ly: str = Field(default="", max_length=1000)

    @field_validator("ghi_chu_xu_ly")
    @classmethod
    def trim_resolution_note(cls, value):
        return value.strip()

    @model_validator(mode="after")
    def completed_report_requires_note(self):
        if self.trang_thai_xu_ly == "DaXuLy" and not self.ghi_chu_xu_ly:
            raise ValueError("Vui lòng ghi rõ kết quả xử lý để thực tập sinh xem lại.")
        return self

class UserLogin(BaseModel):
    email: str
    mat_khau: str

class UserRegister(BaseModel):
    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    vai_tro: Optional[str] = "ThucTapSinh"  # Mặc định là Thực tập sinh
    ma_phong_ban: Optional[int] = None

class RoleAssign(BaseModel):
    vai_tro: str  # 'Admin' | 'HR' | 'Mentor' | 'ThucTapSinh'
    ma_phong_ban: Optional[int] = None

class UserStatusUpdate(BaseModel):
    trang_thai: str  # 'HoatDong' | 'Khoa' | 'ChoDuyet'


class UserProfileUpdate(BaseModel):
    ho_ten: str
    so_dien_thoai: Optional[str] = None

class PasswordChange(BaseModel):
    mat_khau_hien_tai: str
    mat_khau_moi: str

class ForgotPasswordRequest(BaseModel):
    email: str

class UserResponse(BaseModel):
    ma_nguoi_dung: int
    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    vai_tro: str
    ma_phong_ban: Optional[int] = None
    ten_phong_ban: Optional[str] = None
    trang_thai: str
    created_at: Optional[str] = None

class InternCreate(BaseModel):
    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    ma_phong_ban: Optional[int] = None
    ma_truong: Optional[int] = None
    chuyen_nganh: Optional[str] = None
    trang_thai_thuc_tap: Optional[Literal["DangThucTap", "HoanThanh", "ThoiHoc"]] = "DangThucTap"

class InternUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    ma_phong_ban: Optional[int] = None
    ma_truong: Optional[int] = None
    chuyen_nganh: Optional[str] = None
    trang_thai_thuc_tap: Optional[Literal["DangThucTap", "HoanThanh", "ThoiHoc"]] = None

class InternDetail(BaseModel):
    ma_ho_so: int
    ma_nguoi_dung: int
    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    ma_phong_ban: Optional[int] = None
    ten_phong_ban: Optional[str] = None
    trang_thai_tai_khoan: Optional[str] = None
    ma_truong: Optional[int] = None
    ten_truong: Optional[str] = None
    chuyen_nganh: Optional[str] = None
    trang_thai_xet_duyet: str
    trang_thai_thuc_tap: Optional[str] = None
    ngay_tao: Optional[str] = None
    mentor_ma_nguoi_dung: Optional[int] = None
    mentor_ho_ten: Optional[str] = None
    mentor_email: Optional[str] = None
    mentor_so_dien_thoai: Optional[str] = None
    mentor_phong_ban: Optional[str] = None
    mentor_chuyen_mon: Optional[str] = None
    mentor_kinh_nghiem: Optional[int] = None

class Department(BaseModel):
    ma_phong_ban: int
    ten_phong_ban: str
    mo_ta: Optional[str] = None

class University(BaseModel):
    ma_truong: int
    ten_truong: str
    dia_chi: Optional[str] = None
    nguoi_lien_he: Optional[str] = None
    email_lien_he: Optional[str] = None

class MentorCreate(BaseModel):
    ho_ten: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    so_dien_thoai: Optional[str] = None
    ma_phong_ban: Optional[int] = None
    chuyen_mon: Optional[str] = None
    kinh_nghiem: Optional[int] = Field(default=None, ge=0)
    so_tts_toi_da: int = Field(default=3, ge=0)

class MentorDetail(BaseModel):
    ma_nguoi_dung: int
    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    ma_phong_ban: Optional[int] = None
    phong_ban: Optional[str] = None
    chuyen_mon: Optional[str] = None
    kinh_nghiem: Optional[int] = None
    so_tts_toi_da: Optional[int] = None
    so_tts_dang_huong_dan: int = 0

class MentorProfileUpdate(BaseModel):
    chuyen_mon: Optional[str] = Field(default=None, max_length=255)
    kinh_nghiem: Optional[int] = Field(default=None, ge=0)
    so_tts_toi_da: Optional[int] = Field(default=None, ge=0)

class InternAssignmentCandidate(BaseModel):
    ma_ho_so: int
    ma_nguoi_dung: int
    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    ten_truong: Optional[str] = None
    chuyen_nganh: Optional[str] = None
    ma_chuong_trinh: Optional[int] = None
    ten_ct: Optional[str] = None
    ma_ct: Optional[str] = None
    ma_ung_tuyen: Optional[int] = None
    timeline_status: Optional[str] = None

class MentorAssignmentDetail(InternAssignmentCandidate):
    ngay_phan_cong: Optional[str] = None
    ma_phan_cong: Optional[int] = None

class MentorBatchAssignment(BaseModel):
    ma_ho_so_list: List[int] = Field(min_length=1, max_length=50)
    ma_chuong_trinh: Optional[int] = None

class ProgramMentorAssignment(BaseModel):
    mentor_id: int = Field(gt=0)


TaskPriority = Literal["LOW", "MEDIUM", "HIGH", "URGENT"]


class MentorTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internship_profile_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    due_date: date
    priority: TaskPriority = "MEDIUM"

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Tiêu đề không được chỉ chứa khoảng trắng.")
        return title

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        description = value.strip()
        return description or None


class MentorTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    due_date: Optional[date] = None
    priority: Optional[TaskPriority] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        title = value.strip()
        if not title:
            raise ValueError("Tiêu đề không được chỉ chứa khoảng trắng.")
        return title

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        description = value.strip()
        return description or None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("Cần cung cấp ít nhất một trường để cập nhật.")
        return self


TaskStatus = Literal["TODO", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
InternProgressStatus = Literal["TODO", "IN_PROGRESS", "COMPLETED"]


class InternTaskProgressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    progress_percent: int = Field(ge=0, le=100)
    status: InternProgressStatus
    note: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        note = value.strip()
        return note or None

    @model_validator(mode="after")
    def validate_completed_progress(self):
        if self.progress_percent == 100 and self.status != "COMPLETED":
            raise ValueError("Tiến độ 100% phải có trạng thái COMPLETED.")
        if self.status == "COMPLETED" and self.progress_percent != 100:
            raise ValueError("Trạng thái COMPLETED yêu cầu tiến độ bằng 100%.")
        return self


class WeeklyReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: int = Field(gt=0)
    week_start: date
    work_content: str = Field(default="", max_length=10000)
    results: str = Field(default="", max_length=10000)
    difficulties: str = Field(default="", max_length=10000)

    @field_validator("work_content", "results", "difficulties")
    @classmethod
    def normalize_report_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("week_start")
    @classmethod
    def require_monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("Ngày bắt đầu tuần phải là thứ Hai.")
        return value


class WeeklyReportUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_content: Optional[str] = Field(default=None, max_length=10000)
    results: Optional[str] = Field(default=None, max_length=10000)
    difficulties: Optional[str] = Field(default=None, max_length=10000)

    @field_validator("work_content", "results", "difficulties")
    @classmethod
    def normalize_optional_report_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_report_change(self):
        if not self.model_fields_set:
            raise ValueError("Cần cung cấp ít nhất một trường để cập nhật.")
        return self


class WeeklyReportReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=1, max_length=10000)

    @field_validator("comment")
    @classmethod
    def normalize_review_comment(cls, value: str) -> str:
        comment = value.strip()
        if not comment:
            raise ValueError("Nhận xét không được chỉ chứa khoảng trắng.")
        return comment


class InternEvaluationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internship_profile_id: int = Field(gt=0)
    program_id: int = Field(gt=0)
    evaluation_period: Literal["MIDTERM", "FINAL"]
    professional_skill_score: StrictInt = Field(ge=1, le=5)
    work_quality_score: StrictInt = Field(ge=1, le=5)
    initiative_score: StrictInt = Field(ge=1, le=5)
    communication_teamwork_score: StrictInt = Field(ge=1, le=5)
    attitude_discipline_score: StrictInt = Field(ge=1, le=5)
    overall_comment: str = Field(min_length=1, max_length=10000)

    @field_validator("overall_comment")
    @classmethod
    def normalize_evaluation_comment(cls, value: str) -> str:
        comment = value.strip()
        if not comment:
            raise ValueError("Nhận xét tổng kết không được chỉ chứa khoảng trắng.")
        return comment


class InternEvaluationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    professional_skill_score: Optional[StrictInt] = Field(default=None, ge=1, le=5)
    work_quality_score: Optional[StrictInt] = Field(default=None, ge=1, le=5)
    initiative_score: Optional[StrictInt] = Field(default=None, ge=1, le=5)
    communication_teamwork_score: Optional[StrictInt] = Field(default=None, ge=1, le=5)
    attitude_discipline_score: Optional[StrictInt] = Field(default=None, ge=1, le=5)
    overall_comment: Optional[str] = Field(default=None, min_length=1, max_length=10000)

    @field_validator("overall_comment")
    @classmethod
    def normalize_optional_evaluation_comment(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        comment = value.strip()
        if not comment:
            raise ValueError("Nhận xét tổng kết không được chỉ chứa khoảng trắng.")
        return comment

    @model_validator(mode="after")
    def require_evaluation_change(self):
        if not self.model_fields_set:
            raise ValueError("Cần cung cấp ít nhất một trường để cập nhật.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Các trường cập nhật không được để trống.")
        return self


class InternAttendanceCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def normalize_attendance_note(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class InternAttendanceCheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")


WorkShiftScope = Literal["GLOBAL", "PROGRAM"]
WorkShiftStatus = Literal["ACTIVE", "INACTIVE"]


class WorkShiftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    start_time: time
    end_time: time
    scope_type: WorkShiftScope
    program_id: Optional[StrictInt] = Field(default=None, gt=0)
    effective_from: date
    effective_to: Optional[date] = None
    status: WorkShiftStatus = "ACTIVE"

    @field_validator("name")
    @classmethod
    def normalize_shift_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Tên ca làm việc không được để trống.")
        return name

    @field_validator("start_time", "end_time")
    @classmethod
    def require_local_time(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("Giờ ca phải là giờ địa phương, không kèm múi giờ.")
        return value

    @model_validator(mode="after")
    def validate_shift_window(self):
        if self.start_time >= self.end_time:
            raise ValueError("Ca qua đêm không được hỗ trợ; giờ bắt đầu phải trước giờ kết thúc.")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("Ngày kết thúc hiệu lực phải sau hoặc bằng ngày bắt đầu.")
        if (self.scope_type == "GLOBAL") != (self.program_id is None):
            raise ValueError("Ca GLOBAL không gắn chương trình; ca PROGRAM phải chọn chương trình.")
        return self


class WorkShiftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    scope_type: Optional[WorkShiftScope] = None
    program_id: Optional[StrictInt] = Field(default=None, gt=0)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    status: Optional[WorkShiftStatus] = None

    @field_validator("name")
    @classmethod
    def normalize_shift_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        name = value.strip()
        if not name:
            raise ValueError("Tên ca làm việc không được để trống.")
        return name

    @field_validator("start_time", "end_time")
    @classmethod
    def require_local_time(cls, value: Optional[time]) -> Optional[time]:
        if value is not None and value.tzinfo is not None:
            raise ValueError("Giờ ca phải là giờ địa phương, không kèm múi giờ.")
        return value

    @model_validator(mode="after")
    def require_valid_patch(self):
        if not self.model_fields_set:
            raise ValueError("Cần cung cấp ít nhất một trường để cập nhật.")
        nullable_fields = {"program_id", "effective_to"}
        if any(getattr(self, field) is None and field not in nullable_fields for field in self.model_fields_set):
            raise ValueError("Các trường cập nhật không được để trống.")
        return self

class ProgramCreate(BaseModel):
    ma_ct: str = Field(min_length=1, max_length=40)
    ten_ct: str = Field(min_length=1, max_length=200)
    ma_phong_ban: int
    ngay_bat_dau: str
    ngay_ket_thuc: str
    chi_tieu: int = Field(default=10, ge=1)
    mo_ta_cong_viec: str = Field(min_length=1)
    yeu_cau: str = Field(min_length=1)
    quyen_loi: Optional[str] = None

class ProgramDetail(BaseModel):
    ma_chuong_trinh: int
    ma_ct: str
    ten_ct: str
    ma_phong_ban: Optional[int] = None
    phong_ban: Optional[str] = None
    ngay_bat_dau: Optional[str] = None
    ngay_ket_thuc: Optional[str] = None
    chi_tieu: int
    mo_ta_cong_viec: Optional[str] = None
    yeu_cau: Optional[str] = None
    quyen_loi: Optional[str] = None
    trang_thai: str
    so_ung_vien: int = 0
    so_cho_duyet: int = 0
    trang_thai_ung_tuyen: Optional[str] = None

class ProgramApplicationReview(BaseModel):
    trang_thai: Literal["DaDuyet", "TuChoi"]
    reject_reason: Optional[str] = Field(default=None, max_length=1000)

class ProgramApplicationDetail(BaseModel):
    ma_ung_tuyen: int
    ma_chuong_trinh: int
    ma_ho_so: int
    ma_nguoi_dung: int
    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    ten_truong: Optional[str] = None
    chuyen_nganh: Optional[str] = None
    trang_thai: str
    ngay_ung_tuyen: Optional[str] = None
    ngay_xet_duyet: Optional[str] = None

class DocumentReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trang_thai_duyet: Literal["DaDuyet", "TuChoi"]
    review_reason: Optional[str] = Field(default=None, max_length=2000)

class ContractRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

class DocumentDetail(BaseModel):
    ma_tai_lieu: int
    ma_ho_so: int
    ten_file: str
    loai_tai_lieu: str
    kich_thuoc: Optional[int] = None
    ngay_tai_len: Optional[str] = None
    trang_thai_duyet: str
    thuc_tap_sinh: str
    reviewed_by: Optional[int] = None
    reviewer_name: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_reason: Optional[str] = None


class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ma_ung_tuyen: int = Field(gt=0)
    start_date: date
    end_date: date
    ly_do: str = Field(min_length=1, max_length=1000)

    @field_validator("ly_do")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Lý do nghỉ phép không được để trống.")
        return trimmed

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("Ngày bắt đầu không được sau ngày kết thúc.")
        return self


class LeaveRequestReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trang_thai: Literal["DaDuyet", "TuChoi"]
    ly_do_tu_choi: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("ly_do_tu_choi")
    @classmethod
    def validate_reject_reason(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            trimmed = value.strip()
            return trimmed if trimmed else None
        return None

    @model_validator(mode="after")
    def validate_rejection(self):
        if self.trang_thai == "TuChoi" and not self.ly_do_tu_choi:
            raise ValueError("Cần cung cấp lý do từ chối đơn nghỉ phép.")
        return self


# ==================== US27 & US28 - YÊU CẦU HỖ TRỢ ====================

SupportRequestType = Literal["CERTIFICATE", "DOCUMENT", "OTHER"]
SupportRequestStatus = Literal["PENDING", "RESOLVED", "REJECTED"]


class SupportRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loai_yeu_cau: SupportRequestType
    noi_dung: str = Field(min_length=1, max_length=2000)
    ma_ho_so: Optional[int] = Field(default=None, gt=0)

    @field_validator("noi_dung")
    @classmethod
    def validate_content(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Nội dung yêu cầu không được để trống.")
        return trimmed


class SupportRequestResolve(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phan_hoi_hr: Optional[str] = Field(default=None, max_length=2000)
    noi_dung_phan_hoi: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def resolve_note(self):
        note = (self.phan_hoi_hr or self.noi_dung_phan_hoi or "").strip()
        self.phan_hoi_hr = note or "Đã giải quyết yêu cầu hỗ trợ."
        return self


class SupportRequestReject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ly_do_tu_choi: Optional[str] = Field(default=None, max_length=2000)
    noi_dung_phan_hoi: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_reason(self):
        reason = (self.ly_do_tu_choi or self.noi_dung_phan_hoi or "").strip()
        if not reason:
            raise ValueError("Vui lòng nhập lý do từ chối yêu cầu.")
        self.ly_do_tu_choi = reason
        return self
