# US41 — Backup và restore drill

## Mặc định an toàn

- Backup thủ công chỉ chạy khi đã áp dụng migration `20261017_us38_us41_us42.sql` trên **database UAT được chọn**.
- Lịch định kỳ mặc định tắt; retention mặc định `0` nghĩa là không tự xóa bản backup nào.
- File ZIP nằm ngoài repository và `frontend/public`, mặc định trong `%LOCALAPPDATA%\IMS-Backups` để kế thừa ACL riêng tư của hồ sơ Windows đang chạy backend. Thư mục cấu hình tùy chỉnh phải chỉ cấp quyền cho tài khoản dịch vụ/backend và quản trị viên.
- Archive gồm MySQL dump, thư mục `uploads/`, manifest schema/tên bảng/số dòng và SHA-256. Password MySQL đi qua file cấu hình tạm có ACL riêng; không nằm trong command line hoặc log.
- `mysqldump --single-transaction` cho snapshot nhất quán của bảng InnoDB. Để manifest đối chiếu số dòng chính xác khi restore drill, tạm dừng thao tác ghi dữ liệu trong lúc tạo backup. Tệp uploads được hash trước và sau khi ghi ZIP; nếu đổi trong lúc backup, job sẽ thất bại.

## Tạo và kiểm tra backup

1. Đăng nhập IMS bằng Admin → **Sao lưu & khôi phục**.
2. Nhấn **Tạo bản sao lưu**. Kết quả `SUCCESS` hiển thị tên file, dung lượng và SHA-256.
3. Nhấn **Kiểm tra** để tính lại checksum từ archive. Chỉ tiếp tục restore drill khi trạng thái `VALID`.

## Restore drill Windows (schema riêng)

Chạy PowerShell ở thư mục repository. Script đọc riêng các biến MySQL từ `%LOCALAPPDATA%\IMS-US37-CLEAN-UAT\runtime.env` (hoặc `backend/.env` nếu runtime file không tồn tại), không in giá trị bí mật và không nạp SMTP/HRM secrets. Nó xác nhận backup là một job `SUCCESS` trong schema UAT nguồn, xác nhận SHA-256, kiểm tra đường dẫn trong ZIP, yêu cầu tên đích mới `ims_restore_drill_*`, không ghi đè schema có sẵn, import dump, đối chiếu số dòng và khóa ngoại, rồi xác minh hash từng upload. Uploads giải nén vào thư mục riêng `restore-drills/<schema>`; schema thử và báo cáo JSON được giữ lại. Khi hoàn tất, script ghi job `RESTORE_VERIFICATION` và audit event vào UAT nguồn.

```powershell
Set-Location 'D:\Codex_file\ims-sprint4-us38-us41-us42'
.\scripts\verify_us41_backup_restore.ps1 `
  -BackupPath "$env:LOCALAPPDATA\IMS-Backups\ims_backup_YYYYMMDD_HHMMSS_xxxxxxxx.zip" `
  -ExpectedSha256 'SHA256_HIEN_THI_TREN_IMS' `
  -BackupJobId 123 `
  -RestoreDatabase 'ims_restore_drill_20261017a' `
  -ActorUserId 22 `
  -UsePrecreatedRestoreDatabase
```

Để tránh cấp quyền `CREATE DATABASE` toàn cục, DBA có thể tạo trước một schema thử chưa tồn tại và chỉ cấp quyền trên schema đích cho tài khoản backend. Khi chạy với `-UsePrecreatedRestoreDatabase`, script chỉ nhận schema rỗng; schema có bảng sẽ bị từ chối. `ActorUserId` phải là Admin đang hoạt động; script xác minh ID trước khi ghi audit. Không dùng database nguồn làm đích. Nếu import lỗi, schema một phần được giữ nguyên để kiểm tra.

Mẫu lệnh DBA (thay account/schema theo UAT được xác minh; không cấp `CREATE DATABASE` toàn cục):

```sql
GRANT EVENT ON `ims_uat_database`.* TO 'ims_backend_user'@'127.0.0.1';
CREATE DATABASE `ims_restore_drill_yyyymmdd` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
GRANT ALL PRIVILEGES ON `ims_restore_drill_yyyymmdd`.* TO 'ims_backend_user'@'127.0.0.1';
```

Sau `RESTORE DRILL PASS`, mở schema đích trong MySQL Workbench và đối chiếu các bảng/file trước khi đánh dấu kiểm tra khôi phục hoàn tất. Đây là restore drill UAT; nó không phải nút restore production và không thay thế một bản sao lưu ở thiết bị/ổ khác.
