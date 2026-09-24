from pydantic import BaseModel
from typing import Optional, List

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
    trang_thai_xet_duyet: Optional[str] = "ChoDuyet"  # 'ChoDuyet', 'DaDuyet', 'TuChoi'
    trang_thai_thuc_tap: Optional[str] = "DangThucTap" # 'DangThucTap', 'HoanThanh', 'ThoiHoc'

class InternUpdate(BaseModel):
    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    ma_phong_ban: Optional[int] = None
    ma_truong: Optional[int] = None
    chuyen_nganh: Optional[str] = None
    trang_thai_xet_duyet: str
    trang_thai_thuc_tap: str

class InternDetail(BaseModel):
    ma_ho_so: int
    ma_nguoi_dung: int
    ho_ten: str
    email: str
    so_dien_thoai: Optional[str] = None
    ma_phong_ban: Optional[int] = None
    ten_phong_ban: Optional[str] = None
    ma_truong: Optional[int] = None
    ten_truong: Optional[str] = None
    chuyen_nganh: Optional[str] = None
    trang_thai_xet_duyet: str
    trang_thai_thuc_tap: str
    ngay_tao: Optional[str] = None

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
