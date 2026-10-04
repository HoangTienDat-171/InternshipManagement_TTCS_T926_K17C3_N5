# Internship Management System

Ứng dụng quản lý thực tập sinh với frontend React/Vite, backend FastAPI và MySQL.

## Cấu trúc

- frontend/src/: giao diện React; views/ chứa màn hình, components/ chứa phần dùng lại.
- backend/app/main.py: khởi tạo FastAPI, middleware và router.
- backend/app/routes/: API xác thực/tài khoản, hồ sơ thực tập, tài liệu, Mentor, chương trình và danh mục.
- backend/app/schemas.py: mô hình yêu cầu và phản hồi Pydantic.
- backend/app/database.py: backend MySQL mặc định, lớp tương thích truy vấn và khởi tạo schema; SQLite chỉ dùng cho bản dữ liệu cũ hoặc kiểm thử cô lập.
- backend/app/internship.db: dữ liệu SQLite cũ, được giữ làm nguồn dự phòng khi chuyển dữ liệu.
- migrations/: migration SQL cho MySQL.
- intership_management.sql: SQL dump hiện có; tên file đang thiếu chữ n.

## Cấu hình MySQL local trên Windows

Tạo `backend/.env` từ `backend/.env.example`, rồi điền thông tin kết nối MySQL local. Không commit `.env` hoặc đưa mật khẩu vào mã nguồn. `IMS_DATABASE_BACKEND=mysql` là cấu hình chạy hiện tại (cũng là giá trị mặc định); ứng dụng kết nối schema `internship_management` và tự đảm bảo các bảng/chỉ mục cần thiết khi khởi động.

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

Kiểm thử API Sprint 1 chạy với SQLite tạm, không ghi vào MySQL hoặc tệp `backend/app/internship.db`:

    cd backend
    .\.venv\Scripts\python -m unittest discover -s tests -v

Quá trình kiểm thử cần virtualenv Backend và khởi chạy API trên một cổng trống. Có thể định tuyến Vite sang một backend khác bằng `VITE_API_PROXY_TARGET`; mặc định vẫn là `http://127.0.0.1:8000`.

## Lưu ý bảo mật và kỹ thuật

- Backend cấp token ngẫu nhiên, lưu bản băm phiên hiện hành trong MySQL và xác minh phiên trên mọi API. Mỗi tài khoản chỉ có một phiên; đăng nhập mới thu hồi token cũ.
- Quyền được đọc từ tài khoản trong DB; không tin các header x-user-role/x-user-id từ client. Tạo/sửa hồ sơ thực tập được giới hạn cho Admin và HR.
- WebSocket phát thông báo thu hồi phiên cho Admin, HR, Mentor và TTS; backend cần gói `wsproto` trong `backend/requirements.txt`. Frontend kết nối lại và gọi API với token. Frontend vẫn lưu token trong localStorage.
- Tài liệu được lưu metadata trong `TAI_LIEU_HO_SO`; PDF/DOCX/PNG tối đa 15 MB nằm dưới `uploads/documents/` cạnh CSDL đang chọn. Admin/HR quản lý mọi tệp, Mentor chỉ tải tệp của TTS được phân công, TTS chỉ tải tệp thuộc hồ sơ của mình. TTS tự nộp CV hoặc đơn xin thực tập.
- Hồ sơ Mentor mở rộng ở `MENTOR_PROFILE`; chương trình thực tập ở `CHUONG_TRINH_THUC_TAP`. Đơn ứng tuyển theo chương trình nằm ở `UNG_TUYEN_CHUONG_TRINH`, có trạng thái chờ duyệt/đã duyệt/từ chối riêng và không khóa tài khoản đăng nhập của sinh viên.
- Duyệt hồ sơ thực tập đồng bộ trạng thái tài khoản: Chờ duyệt → Chờ duyệt, Đã duyệt → Hoạt động, Từ chối → Khóa. Khóa tài khoản quản trị vẫn là thao tác độc lập, không tự từ chối hồ sơ đã duyệt.
- CORS cho phép mọi origin cùng credentials. Rà lại origin theo môi trường.
- API đọc danh sách/chi tiết hồ sơ yêu cầu phiên đăng nhập; kiểm tra quyền truy cập theo từng hồ sơ/người dùng vẫn cần được rà soát theo ma trận nghiệp vụ.
- `20260927_consistency_modules_mysql.sql` dành cho MySQL. SQLite cũ không bị ghi đè trong quá trình chuyển đổi; bài test dùng `IMS_DATABASE_BACKEND=sqlite` cùng `IMS_SQLITE_PATH` trỏ đến tệp tạm riêng.
- Thông tin hồ sơ/TTS, Mentor, tài liệu, chương trình, ứng tuyển, tài khoản và phiên đăng nhập dùng chung MySQL; nội dung tệp tài liệu nằm trong `backend/app/uploads/`.
- Thao tác dữ liệu phát sự kiện thông báo/WebSocket sau khi ghi MySQL thành công; giao diện tải lại danh sách qua API hiện hành.

## Sprint 2: US08 email kết quả xét duyệt

Khi tạo tài khoản, backend sinh mật khẩu tạm, gửi qua email và buộc người dùng đổi mật khẩu ngay lần đăng nhập đầu tiên. Khi Admin/HR duyệt hoặc từ chối hồ sơ thực tập hay đơn ứng tuyển chương trình, backend ghi thông báo trong app và email vào `EMAIL_OUTBOX` trong cùng transaction. Worker nền gửi SMTP và chống claim đồng thời. Email mới được thử tối đa 4 lần (lần đầu và 3 lần gửi lại); các lần gửi lại cách nhau 1, 5 và 15 phút, sau đó chuyển sang `FAILED`. Notification và outbox có khóa deduplication theo hồ sơ/đơn và kết quả. HR/Admin xem trạng thái, số lần gửi và lỗi gần nhất ở màn Quản lý thực tập sinh; trạng thái email không nằm trong menu thông báo.

Để gửi email bằng Gmail cá nhân, mở `backend/.env` (tạo từ `backend/.env.example` nếu chưa có) và thêm hoặc cập nhật cấu hình dưới đây. Giữ nguyên các dòng cấu hình MySQL đang dùng:

    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USERNAME=your-address@gmail.com
    SMTP_PASSWORD=<Google App Password>
    SMTP_FROM=your-address@gmail.com
    SMTP_USE_SSL=false
    SMTP_USE_STARTTLS=true
    SMTP_TIMEOUT_SECONDS=15
    EMAIL_WORKER_INTERVAL_SECONDS=5
    IMS_COMPANY_NAME=Ten cong ty
    IMS_PORTAL_URL=https://dia-chi-portal-cua-ban

Thay cả hai giá trị `your-address@gmail.com` bằng cùng địa chỉ Gmail của bạn. Bật [Xác minh 2 bước](https://support.google.com/accounts/answer/10956730) cho Google Account, tạo [App Password](https://support.google.com/mail/answer/185833) riêng cho ứng dụng này, rồi đặt App Password vào `SMTP_PASSWORD`; không dùng mật khẩu đăng nhập Gmail. Google có thể không cung cấp App Password cho một số tài khoản được quản lý, bật Advanced Protection hoặc chỉ dùng security key cho Xác minh 2 bước. Sau khi lưu `.env`, khởi động lại backend để worker nạp cấu hình. Không commit `.env` hoặc chia sẻ App Password.

`SMTP_HOST` là máy chủ SMTP của Gmail; địa chỉ Gmail cá nhân được dùng làm tài khoản xác thực và địa chỉ người gửi. `IMS_COMPANY_NAME` và `IMS_PORTAL_URL` được dùng trong email kết quả ứng tuyển; nếu bỏ trống, công ty hiển thị là `IMS Portal` và email hướng dẫn mở địa chỉ portal đã được cung cấp. Với MySQL hiện có, rà soát và áp dụng `migrations/20260930_us08_email_notifications.sql` để đặt giới hạn bốn lần thử cho cả mặc định lẫn hàng đợi cũ; áp dụng `migrations/20260930_temporary_passwords.sql` trước khi tạo tài khoản để thêm cột đổi mật khẩu. Backend không tự chạy các migration này.

Các unit test `tests/test_us08_email_outbox.py` giả lập SMTP thành công, mất kết nối, hết retry, deduplication, rollback và hai worker claim đồng thời mà không gọi SMTP thật. Migration MySQL nằm ở `migrations/20260930_us08_email_notifications.sql`; `init_db()` cũng tạo/cập nhật các bảng US08 theo cơ chế khởi động hiện tại.

## Các tính năng và cập nhật mới

- Sửa lại lỗi đăng kí, Thêm quên mật khẩu, khi hồ sơ được duyệt thì sẽ có email gửi về gmail để xác nhận cho thực tập sinh đã đăng kì thành công và gửi cho mật khẩu để thực tập sinh đăng nhập và đổi mật khẩu mới
- Thêm Chức năng cho gửi email (gửi ảnh, file tài liệu)
- Thêm tránh thư trùng lặp cùng một nội dung và không cho gửi

Xem docs/audit/2026-09-26-repo-audit.md và AGENTS.md trước khi thay đổi cấu trúc hoặc bảo mật.
