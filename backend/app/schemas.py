from pydantic import BaseModel, Field
from typing import Optional, List, Literal

class UserLogin(BaseModel):
    email: str
    mat_khau: str

class UserRegister(BaseModel):
    ho_ten: str
    email: str
    mat_khau: str
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
    mat_khau: Optional[str] = "123456"
    ma_phong_ban: Optional[int] = None
    ma_truong: Optional[int] = None
    chuyen_nganh: Optional[str] = None
    trang_thai_xet_duyet: Optional[Literal["ChoDuyet", "DaDuyet", "TuChoi"]] = "ChoDuyet"
    trang_thai_thuc_tap: Optional[Literal["DangThucTap", "HoanThanh", "ThoiHoc"]] = "DangThucTap"

class InternUpdate(BaseModel):
    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    ma_phong_ban: Optional[int] = None
    ma_truong: Optional[int] = None
    chuyen_nganh: Optional[str] = None
    trang_thai_xet_duyet: Literal["ChoDuyet", "DaDuyet", "TuChoi"]
    trang_thai_thuc_tap: Literal["DangThucTap", "HoanThanh", "ThoiHoc"]

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
    trang_thai_thuc_tap: str
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
    mat_khau: str = Field(min_length=6, max_length=128)
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

class MentorAssignmentDetail(InternAssignmentCandidate):
    ngay_phan_cong: Optional[str] = None

class MentorBatchAssignment(BaseModel):
    ma_ho_so_list: List[int] = Field(min_length=1, max_length=50)

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
    trang_thai_duyet: Literal["DaDuyet", "TuChoi"]

class DocumentDetail(BaseModel):
    ma_tai_lieu: int
    ma_ho_so: int
    ten_file: str
    loai_tai_lieu: str
    kich_thuoc: Optional[int] = None
    ngay_tai_len: Optional[str] = None
    trang_thai_duyet: str
    thuc_tap_sinh: str
