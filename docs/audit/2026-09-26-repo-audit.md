# Báo cáo audit repo

Ngày: 2026-09-26
Repo: D:\antigravity_file\InternshipManagement_TTCS_T926_K17C3_N5
Phạm vi: kiểm tra cấu trúc và mã nguồn; không sửa logic, schema hoặc dữ liệu.

## Tóm tắt

Ứng dụng nhỏ với frontend React 19 + Vite 8, backend FastAPI + Pydantic + SQLite, chưa cấu hình framework kiểm thử. Cấu trúc chính tương đối dễ nhận biết. Rủi ro lớn nằm ở xác thực/phân quyền giả lập, side effect khi khởi tạo DB và thiếu test bảo vệ behavior. Graft/Graphify chưa phù hợp quy mô hiện tại.

Trạng thái Git trước khi làm:
- Branch feature/US01-auth.
- backend/app/internship.db đang modified.
- InternshipManagement_TTCS_T926_K17C3_N5/ đang untracked và chứa một .git riêng.
Hai vùng này được giữ nguyên.

## Stack và lệnh

- UI: React 19, JavaScript/JSX, Vite 8, oxlint, lucide-react.
- API: FastAPI, Starlette, Pydantic 2, SQLite, bcrypt, uvicorn.
- Vite proxy /api tới 127.0.0.1:8000.
- Backend từ repo root: .\backend\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
- Frontend từ frontend/: npm run dev -- --host 127.0.0.1 --port 3000
- Checks: npm run lint, npm run build (frontend/); .\.venv\Scripts\python -m compileall -q app (backend/).
- Không có test script frontend hoặc backend test suite. Không chạy migration hay thao tác DB trong audit.

## Bản đồ kiến trúc

    frontend/src/main.jsx
      └─ App.jsx: đăng nhập local state, điều hướng
          ├─ views/: màn hình intern, mentor, program, account, document, profile, login
          └─ components/: sidebar, navbar, modal, form controls

    backend/app/main.py
      ├─ database.py: SQLite schema, seed, password helpers
      └─ routes/
          ├─ auth_routes.py: đăng nhập, tài khoản, profile
          ├─ intern_routes.py: CRUD hồ sơ thực tập
          └─ master_routes.py: danh mục

## Phát hiện theo mức ưu tiên

### P0 — Không triển khai công khai khi chưa sửa auth/authorization

1. auth_routes.py: endpoint đặc quyền lấy role từ x-user-role. Client tự gửi header nên có thể giả làm Admin/HR. Không thấy backend xác minh token/session trước khi cấp quyền.
2. login() dựng token từ ID và chuỗi hash nhưng không lưu phiên, ký bằng secret hoặc xác minh ở endpoint khác. localStorage chỉ là state giao diện, không phải identity tin cậy.
3. intern_routes.py cho phép list/create/read/update hồ sơ mà không có dependency xác thực/quyền. Có nguy cơ lộ PII và sửa dữ liệu.
4. update_profile/change_password nhận user_id trên URL; cần xác minh người gọi được sửa tài khoản đó khi có auth thực.
5. App.jsx dựng profile đổi vai trò demo ở client; không phải quyền server.

Bước riêng nên là xác định mô hình phiên/token và ma trận quyền; thêm auth dependency tập trung, kiểm tra ownership và regression tests anonymous/spoofed role/cross-user; rồi sửa route và UI theo lát cắt. Đây là thay đổi an ninh/behavior lớn, chưa tự động làm trong lượt audit để tránh phá luồng demo hoặc tạo cảm giác bảo mật giả.

### P1 — CORS và môi trường

- main.py cho mọi origin cùng credentials; production cần allowlist origin.
- Middleware thêm HSTS cả khi chạy local HTTP. Cấu hình production nên gắn với HTTPS/reverse proxy.
- Tài khoản demo dùng chung mật khẩu 123456 và quick-login UI; chỉ phù hợp dữ liệu demo.
- init_db() tạo schema, seed và đổi mọi mật khẩu không bcrypt thành hash 123456. Đây là side effect lớn trên DB hiện hữu; cần migration rõ ràng, backup và test.
- Lockout theo email có thể bị lạm dụng để khóa tài khoản mục tiêu; xem xét kết hợp IP/rate limit.
- Log audit lưu email/IP/lý do; cần giới hạn truy cập và retention.

### P2 — Test, kiến trúc, nhất quán

- Chưa có test backend/frontend; auth, duyệt, profile/password và CRUD không có regression net.
- auth_routes.py lớn (khoảng 510 dòng), gom auth, quản trị user, profile/password và security logs. Chỉ tách khi có task cụ thể và test.
- Validation điện thoại lặp ở auth và intern routes; frontend utils/phone.js có regex riêng, dễ drift. Hợp nhất sau khi có tests.
- init_db() trộn schema, seed và migration behavior; chuyển dần sang migration versioned/idempotent có tests.
- migrations/20260926_sprint1_user_profile.sql ghi MySQL và dùng syntax MySQL; backend đang dùng SQLite. Xác định rõ DB mục tiêu trước khi chạy.
- run_servers.bat Windows-only và phụ thuộc venv path; README cũ là mẫu Vite.
- SQL dump intership_management.sql sai chính tả; không đổi tên khi chưa xác minh tham chiếu của nhóm.
- Repo lồng đang untracked; có thể là artifact quan trọng. Không di chuyển/xóa/commit khi chưa xác nhận.
- SQLite DB được Git theo dõi và đang modified. Không ignore hoặc xóa khỏi Git tự động vì có thể mất trạng thái người dùng.

## Dead code/điểm rối cần xác minh

- frontend/src/assets/react.svg và vite.svg giống asset template và không thấy import trong src; có thể tham chiếu tĩnh nên chỉ là ứng viên xóa.
- LoginModal.jsx, VisionBanner.jsx và App.css cần kiểm tra import/runtime trước khi dọn. Tên file đơn lẻ không chứng minh dead code.
- Tìm kiếm nhanh không thấy TODO/FIXME/debugger.
- Chưa thấy duplication đủ lớn để biện minh refactor trước khi có tests; validation điện thoại là phần trùng rõ nhất.

## Workflow Codex áp dụng

Đã thêm AGENTS.md: kiểm tra Git trước khi sửa; lấy context theo route/component/schema/caller; lập objective/scope/acceptance/verification cho thay đổi lớn; chia nhỏ, source-driven, regression check cho bug; chạy checks phù hợp; review explicit simplicity/security/duplication/dead code; không commit, chạy production migration hoặc sửa DB khi chưa được yêu cầu.

Đã thay README mẫu bằng bản đồ repo, lệnh chạy/kiểm tra và lưu ý vận hành/bảo mật.

Không cài skill packs hoặc công cụ ngoài, không cài Graft/Graphify. Repo có vài chục source files và một số router/view; tìm kiếm, import/caller inspection và AGENTS.md hiện đủ. Graph generator/MCP làm tăng dependency và chi phí cập nhật index mà chưa có lợi ích chứng minh. Đánh giá lại khi repo lớn và cần caller/dependency tracing thường xuyên.

## Kiểm tra

Baseline trước khi đổi tài liệu:
- npm run lint (frontend/): PASS.
- npm run build (frontend/): PASS sau khi cấp quyền ghi file tạm/build.
- .\.venv\Scripts\python -m compileall -q app (backend/): PASS.
- Không có test hành vi được cấu hình.
- Build tạo/cập nhật frontend/dist/ (ignored); DB và repo lồng không bị đụng.

Sau khi đổi tài liệu, chạy lại lint/build/compileall để xác nhận không ảnh hưởng app.

## Cập nhật sau audit (2026-09-26)

Phần auth được triển khai sau thời điểm audit:
- Bảng ACTIVE_SESSIONS lưu một token hash cho mỗi tài khoản; middleware kiểm tra phiên và trạng thái tài khoản trên mỗi API.
- Vai trò/identity lấy từ DB, profile/password xác minh ownership; thao tác tạo/sửa hồ sơ thực tập giới hạn Admin/HR.
- WebSocket báo thu hồi phiên cũ, thay đổi profile/vai trò/trạng thái; client tự reconnect.
- Xác minh trên SQLite tạm: login mới thay token cũ; API cũ trả 401; x-user-role giả không đổi role server; thông báo nhắm đúng socket phiên cũ.
- Sau triển khai: lint/build/compileall đều pass. Chưa xác minh hai trình duyệt end-to-end; broadcast WebSocket hiện ở trong một tiến trình, cần pub/sub nếu chạy nhiều worker.

Các phát hiện audit khác về CORS, DB startup/seed, HTTPS/HSTS, demo credentials và test suite vẫn cần xử lý riêng.

## Chưa tự động thực hiện

1. Thiết kế và triển khai xác thực server-side cùng ma trận quyền.
2. Test auth, giả mạo role, ownership, CRUD, profile, password và lockout.
3. Tách side effect khỏi startup và thiết kế SQLite migrations/backup.
4. CORS theo môi trường, xác nhận HTTPS/HSTS.
5. Chốt DB mục tiêu và tên SQL dump.
6. Xác nhận mục đích repo lồng và DB modified với chủ repo.
7. Dọn asset/component ứng viên sau khi xác minh mọi tham chiếu.
