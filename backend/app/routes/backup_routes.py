from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import backup_service
from ..database import get_db
from ..security import require_role


router = APIRouter(prefix="/api/admin/backups", tags=["Backup and Recovery - US41"])


class BackupSettingsUpdate(BaseModel):
    schedule_enabled: bool
    interval_hours: int = Field(ge=1, le=8760)
    retention_count: int = Field(ge=0, le=365)


def _admin(request: Request) -> dict:
    return require_role(request, "Admin")


def _raise_backup_error(exc: backup_service.BackupError) -> None:
    messages = {
        "FEATURE_MIGRATION_REQUIRED": (503, "Chưa có schema US38/41/42. Hãy áp dụng migration 20261017_us38_us41_us42.sql trên database UAT rồi khởi động lại."),
        "BACKUP_ALREADY_RUNNING": (409, "Một bản sao lưu đang chạy. Chờ hoàn tất rồi thử lại."),
        "BACKUP_NOT_FOUND": (404, "Không tìm thấy bản sao lưu."),
        "BACKUP_ARTIFACT_NOT_FOUND": (409, "Bản ghi này là kết quả restore drill, không phải file backup để kiểm tra checksum."),
        "MYSQLDUMP_NOT_FOUND": (503, "Không tìm thấy mysqldump. Cài MySQL Server Client hoặc đặt IMS_MYSQLDUMP_BIN trong backend/.env."),
        "MYSQLDUMP_EVENT_PRIVILEGE_MISSING": (503, "Tài khoản MySQL của backend thiếu quyền EVENT trên schema UAT. Nhờ DBA cấp quyền này để bản backup giữ đầy đủ database events."),
        "MYSQLDUMP_PRIVILEGE_MISSING": (503, "Tài khoản MySQL của backend thiếu quyền cần thiết để sao lưu schema UAT. Kiểm tra quyền đọc metadata, view, trigger, routine và event."),
        "MYSQLDUMP_TIMEOUT": (504, "Lệnh sao lưu MySQL quá thời gian cho phép. Job đã được đánh dấu thất bại; kiểm tra log backend đã ẩn thông tin nhạy cảm."),
        "MYSQLDUMP_EXECUTION_FAILED": (503, "Không thể khởi chạy mysqldump trên máy chủ backend. Kiểm tra đường dẫn và quyền chạy chương trình."),
        "MYSQLDUMP_UNSUPPORTED_OPTION": (503, "Phiên bản mysqldump không hỗ trợ tùy chọn sao lưu hiện tại. Cài MySQL Server Client tương thích."),
        "MYSQLDUMP_CONNECTION_FAILED": (503, "mysqldump không kết nối được MySQL UAT. Kiểm tra máy chủ và cấu hình kết nối backend."),
        "MYSQL_CREDENTIALS_MISSING": (503, "Thiếu cấu hình MySQL của backend. Kiểm tra MYSQL_USER và MYSQL_PASSWORD trong môi trường local."),
        "INSUFFICIENT_DISK_SPACE": (507, "Ổ đĩa lưu backup còn dưới 50 MB. Hãy giải phóng dung lượng hoặc đổi IMS_BACKUP_DIRECTORY."),
        "UNSAFE_BACKUP_DIRECTORY": (500, "Đường dẫn backup nằm trong vùng public/build. Hãy đặt IMS_BACKUP_DIRECTORY ngoài thư mục frontend."),
        "MYSQL_DATABASE_INVALID": (500, "Tên database MySQL không hợp lệ cho backup."),
        "BACKUP_DIRECTORY_PERMISSIONS_FAILED": (500, "Không thiết lập được quyền riêng tư cho thư mục backup. Hãy chọn thư mục do tài khoản chạy backend sở hữu hoặc nhờ quản trị viên Windows cấp quyền."),
        "BACKUP_UPLOAD_CHANGED": (409, "Tệp tải lên thay đổi trong lúc sao lưu. Hãy thử lại khi không có tiến trình cập nhật tệp."),
    }
    status_code, detail = messages.get(exc.code, (500, f"Backup thất bại ({exc.code}). Kiểm tra log backend; log không chứa thông tin đăng nhập."))
    raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/settings")
def get_backup_settings(request: Request, db=Depends(get_db)):
    _admin(request)
    try:
        return backup_service.get_settings(db)
    except backup_service.BackupError as exc:
        _raise_backup_error(exc)


@router.put("/settings")
def update_backup_settings(data: BackupSettingsUpdate, request: Request, db=Depends(get_db)):
    actor = _admin(request)
    try:
        return backup_service.update_settings(
            db,
            schedule_enabled=data.schedule_enabled,
            interval_hours=data.interval_hours,
            retention_count=data.retention_count,
            actor=actor,
        )
    except backup_service.BackupError as exc:
        _raise_backup_error(exc)


@router.get("")
def list_backup_jobs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    _admin(request)
    try:
        return backup_service.list_backups(db, page=page, page_size=page_size)
    except backup_service.BackupError as exc:
        _raise_backup_error(exc)


@router.post("")
def run_backup(request: Request):
    actor = _admin(request)
    try:
        return backup_service.create_backup(actor=actor)
    except backup_service.BackupError as exc:
        _raise_backup_error(exc)


@router.post("/{job_id}/verify")
def verify_backup(job_id: int, request: Request):
    actor = _admin(request)
    try:
        return backup_service.verify_backup(job_id, actor=actor)
    except backup_service.BackupError as exc:
        _raise_backup_error(exc)
