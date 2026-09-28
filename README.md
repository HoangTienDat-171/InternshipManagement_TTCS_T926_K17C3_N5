# Internship Management System

Ứng dụng quản lý thực tập sinh với frontend React/Vite, backend FastAPI và MySQL.

## Cấu trúc

- frontend/src/: giao diện React; views/ chứa màn hình, components/ chứa phần dùng lại.
- backend/app/main.py: khởi tạo FastAPI, middleware và router.
- backend/app/routes/: API xác thực/tài khoản, hồ sơ thực tập, tài liệu, Mentor, chương trình và danh mục.
- backend/app/schemas.py: mô hình yêu cầu và phản hồi Pydantic.
- backend/app/database.py: kết nối MySQL, lớp tương thích truy vấn và khởi tạo schema.
- backend/app/internship.db: dữ liệu SQLite cũ, được giữ làm nguồn dự phòng khi chuyển dữ liệu.
- migrations/: migration SQL cho MySQL.
- intership_management.sql: SQL dump hiện có; tên file đang thiếu chữ n.

## Cấu hình MySQL local trên Windows

Tạo `backend/.env` từ `backend/.env.example`, rồi điền thông tin kết nối MySQL local. Không commit `.env` hoặc đưa mật khẩu vào mã nguồn. Mặc định ứng dụng dùng schema `internship_management` và tự đảm bảo các bảng/chỉ mục cần thiết khi khởi động.

Backend cần MySQL 8 và PyMySQL (có trong `backend/requirements.txt`). Dùng `mysql.exe` để kiểm tra đăng nhập trước khi chạy ứng dụng.

## Chạy local trên Windows

Chạy backend từ thư mục gốc repo:

    .\backend\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

Chạy frontend trong terminal khác:

    cd frontend
    npm run dev -- --host 127.0.0.1 --port 3000

Mở http://127.0.0.1:3000; API docs local ở http://127.0.0.1:8000/docs. Vite chuyển tiếp /api tới backend cục bộ. run_servers.bat là launcher Windows và phụ thuộc backend/.venv.

Có thể chạy `run_servers.bat` ở thư mục gốc để khởi động cả hai cổng. Launcher kiểm tra Node/npm, virtualenv, cấu hình MySQL và cổng 3000/8000; nếu thiếu thư viện Frontend/Backend thì cài theo manifest trước khi chạy. Backend gọi `init_db()` khi khởi động để đảm bảo schema/dữ liệu danh mục mặc định trong database đã cấu hình.

Tài khoản demo hiện dùng mật khẩu chung 123456; chỉ dùng với dữ liệu demo local. `database.init_db()` tạo các bảng/module còn thiếu và đảm bảo hồ sơ Mentor/TTS. Sao lưu MySQL trước khi chạy migration trên dữ liệu quan trọng.

## Lệnh kiểm tra

Từ frontend/:

    npm run lint
    npm run build

Từ backend/:

    .\.venv\Scripts\python -m compileall -q app

Chưa có script test frontend hoặc bộ test backend. compileall chỉ kiểm tra cú pháp Python, không thay thế test hành vi.

## Lưu ý bảo mật và kỹ thuật

- Backend cấp token ngẫu nhiên, lưu bản băm phiên hiện hành trong MySQL và xác minh phiên trên mọi API. Mỗi tài khoản chỉ có một phiên; đăng nhập mới thu hồi token cũ.
- Quyền được đọc từ tài khoản trong DB; không tin các header x-user-role/x-user-id từ client. Tạo/sửa hồ sơ thực tập được giới hạn cho Admin và HR.
- WebSocket phát thông báo thu hồi phiên, cập nhật hồ sơ/vai trò; frontend kết nối lại và gọi API với token. Frontend vẫn lưu token trong localStorage.
- Tài liệu được lưu metadata trong `TAI_LIEU_HO_SO`; nội dung PDF/DOCX/PNG tối đa 15 MB nằm trong `backend/app/uploads/` (đã được Git bỏ qua). API file chỉ cho Admin/HR truy cập.
- Hồ sơ Mentor mở rộng ở `MENTOR_PROFILE`; chương trình thực tập ở `CHUONG_TRINH_THUC_TAP`. Đơn ứng tuyển theo chương trình nằm ở `UNG_TUYEN_CHUONG_TRINH`, có trạng thái chờ duyệt/đã duyệt/từ chối riêng và không khóa tài khoản đăng nhập của sinh viên.
- Duyệt hồ sơ thực tập đồng bộ trạng thái tài khoản: Chờ duyệt → Chờ duyệt, Đã duyệt → Hoạt động, Từ chối → Khóa. Khóa tài khoản quản trị vẫn là thao tác độc lập, không tự từ chối hồ sơ đã duyệt.
- CORS cho phép mọi origin cùng credentials. Rà lại origin theo môi trường.
- API đọc danh sách/chi tiết hồ sơ yêu cầu phiên đăng nhập; kiểm tra quyền truy cập theo từng hồ sơ/người dùng vẫn cần được rà soát theo ma trận nghiệp vụ.
- `20260927_consistency_modules_mysql.sql` dành cho MySQL. SQLite cũ không bị ghi đè trong quá trình chuyển đổi.
- Thông tin hồ sơ/TTS, Mentor, tài liệu, chương trình, ứng tuyển, tài khoản và phiên đăng nhập dùng chung MySQL; nội dung tệp tài liệu nằm trong `backend/app/uploads/`.
- Thao tác dữ liệu phát sự kiện thông báo/WebSocket sau khi ghi MySQL thành công; giao diện tải lại danh sách qua API hiện hành.

Xem docs/audit/2026-09-26-repo-audit.md và AGENTS.md trước khi thay đổi cấu trúc hoặc bảo mật.
