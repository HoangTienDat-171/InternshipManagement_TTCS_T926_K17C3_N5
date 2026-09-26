# Internship Management System

Ứng dụng quản lý thực tập sinh với frontend React/Vite, backend FastAPI và SQLite.

## Cấu trúc

- frontend/src/: giao diện React; views/ chứa màn hình, components/ chứa phần dùng lại.
- backend/app/main.py: khởi tạo FastAPI, middleware và router.
- backend/app/routes/: API xác thực/tài khoản, thực tập sinh và danh mục.
- backend/app/schemas.py: mô hình yêu cầu và phản hồi Pydantic.
- backend/app/database.py: kết nối, khởi tạo schema và dữ liệu demo SQLite.
- backend/app/internship.db: cơ sở dữ liệu local được ứng dụng sửa khi chạy.
- migrations/: migration SQL cho MySQL; backend hiện dùng SQLite.
- intership_management.sql: SQL dump hiện có; tên file đang thiếu chữ n.

## Chạy local trên Windows

Chạy backend từ thư mục gốc repo:

    .\backend\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

Chạy frontend trong terminal khác:

    cd frontend
    npm run dev -- --host 127.0.0.1 --port 3000

Mở http://127.0.0.1:3000; API docs local ở http://127.0.0.1:8000/docs. Vite chuyển tiếp /api tới backend cục bộ. run_servers.bat là launcher Windows và phụ thuộc backend/.venv.

Tài khoản demo hiện dùng mật khẩu chung 123456; chỉ dùng với dữ liệu demo local. database.init_db() tạo bảng/seed khi khởi động và có nhánh nâng cấp mật khẩu legacy. Sao lưu DB trước khi thử trên dữ liệu quan trọng.

## Lệnh kiểm tra

Từ frontend/:

    npm run lint
    npm run build

Từ backend/:

    .\.venv\Scripts\python -m compileall -q app

Chưa có script test frontend hoặc bộ test backend. compileall chỉ kiểm tra cú pháp Python, không thay thế test hành vi.

## Lưu ý bảo mật và kỹ thuật

- Backend cấp token ngẫu nhiên, lưu bản băm phiên hiện hành trong SQLite và xác minh phiên trên mọi API. Mỗi tài khoản chỉ có một phiên; đăng nhập mới thu hồi token cũ.
- Quyền được đọc từ tài khoản trong DB; không tin các header x-user-role/x-user-id từ client. Tạo/sửa hồ sơ thực tập được giới hạn cho Admin và HR.
- WebSocket phát thông báo thu hồi phiên, cập nhật hồ sơ/vai trò; frontend kết nối lại và gọi API với token. Frontend vẫn lưu token trong localStorage.
- CORS cho phép mọi origin cùng credentials. Rà lại origin theo môi trường.
- API đọc danh sách/chi tiết hồ sơ yêu cầu phiên đăng nhập; kiểm tra quyền truy cập theo từng hồ sơ/người dùng vẫn cần được rà soát theo ma trận nghiệp vụ.
- Migration dùng cú pháp MySQL trong khi backend dùng SQLite. Không chạy migration này trên SQLite.
- Database là file local có thể chứa trạng thái người dùng; không xóa, thay thế hoặc commit thay đổi file này như một phần sửa code thông thường.

Xem docs/audit/2026-09-26-repo-audit.md và AGENTS.md trước khi thay đổi cấu trúc hoặc bảo mật.
