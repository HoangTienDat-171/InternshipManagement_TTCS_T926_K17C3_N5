# Đối chiếu dữ liệu giữa các màn hình

Ngày kiểm tra: 27/09/2026. Mã nguồn: `50b6b1d`.

## Phạm vi và cách kiểm tra

Mục tiêu: xác định dữ liệu các màn hình có cùng nguồn, lưu bền vững và liên kết đúng không; giải thích trường hợp Lê Minh Tuấn / Hoàng Lan Anh.

Đã rà các view, component/caller, API, schema, kết nối/seed SQLite, SQL dump, migration, cấu hình chạy và lịch sử 7 commit của repo chính. Đối chiếu GitHub bằng `git ls-remote origin`. Không coi nội dung mô tả tính năng hay tên commit là bằng chứng tính năng đã hoàn thành. Không rà từng byte của thư viện cài đặt, build output hay ảnh/SVG vì không chứa luồng dữ liệu nghiệp vụ.

Tiêu chí: tên/ID và trạng thái có nguồn xác định; thao tác thành công phải ghi dữ liệu đúng; các màn hình liên quan phải đọc cùng quan hệ; không có liên kết mồ côi.

Xác minh: mở SQLite bằng URI `mode=ro`, đặt `PRAGMA query_only=ON`; kiểm tra bảng, khóa ngoại, truy vấn danh sách/chi tiết; thử các hàm xử lý trạng thái/xóa/đổi vai trò trên bản sao `:memory:`. Không khởi chạy startup/init_db, không đăng nhập mới, không gọi API ghi trên server thật. Hash DB không đổi trước/sau lượt thử nghiệm trong RAM.

Trạng thái có sẵn được giữ nguyên: `backend/app/internship.db` vốn đã modified; thư mục `InternshipManagement_TTCS_T926_K17C3_N5/` vốn untracked và chứa repo riêng ở commit `457b10c`. Repo lồng được để nguyên. Sau audit, mã nguồn và báo cáo này được cập nhật theo yêu cầu sửa lỗi; không commit hoặc push.

## Kết luận trực tiếp về hai ảnh

**Dữ liệu chưa đồng bộ toàn bộ. Tài liệu là giao diện mô phỏng; danh sách thực tập sinh đọc dữ liệu SQLite thật.**

| Người | Mã hồ sơ thật | Xét duyệt hồ sơ thật | Tài khoản thật | Tài liệu hiển thị trên UI |
|---|---:|---|---|---|
| Lê Minh Tuấn | 1 | Đã duyệt | Hoạt động | CV đã duyệt, đơn xin thực tập chờ duyệt — đều viết sẵn |
| Hoàng Lan Anh | 2 | Từ chối | Khóa | Giấy giới thiệu chờ duyệt — viết sẵn |

Hai người vẫn xuất hiện trong kết quả hàm danh sách không lọc. API sắp `ma_ho_so DESC`, nên họ là hai dòng cuối. Ảnh quản lý thực tập sinh chỉ chụp đoạn #14–#10; chưa phải bằng chứng hai hồ sơ biến mất. Đặt lại bộ lọc, tìm tên rồi nhấn Enter, hoặc cuộn cuối danh sách để kiểm tra. Nếu chọn lọc “Chờ duyệt” thì cả hai không xuất hiện vì trạng thái hồ sơ hiện tại không phải Chờ duyệt.

`DocumentManagementView.jsx:5` khởi tạo ba tài liệu bằng `useState`; dòng 109–110 viết sẵn hai lựa chọn tên. `handleSimulatedUpload` ở dòng 39 chỉ thêm object vào state, không gửi file; nút Xem ở dòng 206 chỉ hiện toast. Bảng `TAI_LIEU_HO_SO` thật có **0 dòng**. Chuyển sang tab khác rồi quay lại sẽ khởi tạo lại danh sách mẫu, do App mount/unmount các view theo tab.

“Chờ duyệt tài liệu”, “Chờ duyệt hồ sơ” và “Chờ duyệt tài khoản” là ba trường riêng. Chúng không bắt buộc giống nhau về nghiệp vụ. Tuy nhiên hiện chưa có API tài liệu hoặc quy tắc liên kết việc duyệt tài liệu với duyệt hồ sơ, nên trạng thái tài liệu trên ảnh không thể dùng để suy ra trạng thái hồ sơ.

## Khắc phục đã áp dụng sau lượt audit

- Module tài liệu, Mentor và chương trình đã chuyển từ mảng mẫu sang API đọc/ghi SQLite. Tài liệu có upload PDF/DOCX/PNG tối đa 15 MB, metadata, duyệt/từ chối, thông báo cho chủ hồ sơ và mở tệp đã lưu. Khi chưa tải tệp thật, màn hình báo danh sách rỗng thay vì tự dựng ba dòng.
- Quyết định duyệt hồ sơ từ cả quản lý hồ sơ lẫn quản trị tài khoản dùng chung quy tắc: `ChoDuyet → ChoDuyet`, `DaDuyet → HoatDong`, `TuChoi → Khoa`. Thao tác khóa thủ công giữ riêng trạng thái khóa; chỉnh sửa thông tin của hồ sơ đã duyệt không tự mở khóa tài khoản. Trường hợp dữ liệu tài khoản/hồ sơ cũ lệch sẽ được sửa khi trạng thái hồ sơ được đổi hoặc khi trạng thái tài khoản lệch mà không phải khóa thủ công.
- Danh sách và chi tiết TTS chỉ nhận tài khoản có vai trò `ThucTapSinh`; API chi tiết dùng duy nhất `ma_ho_so`. Danh sách Mentor lấy tài khoản vai trò Mentor. Đổi vai trò không xóa hồ sơ lịch sử; các view lọc theo vai trò hiện tại.
- Bật khóa ngoại cho connection ghi mới, tạo schema Mentor/chương trình và các cột metadata tài liệu theo hướng bổ sung; thêm migration tương ứng dành riêng cho MySQL. Không sửa dữ liệu mồ côi có sẵn.
- Thêm API thông báo bền vững theo người nhận và hộp thông báo trong navbar; trạng thái duyệt tài khoản/hồ sơ/tài liệu phát thông báo khi có thay đổi. Các view Mentor, chương trình và tài liệu có nút làm mới để tải lại dữ liệu từ DB.
- Bỏ đổi vai trò giả ở giao diện; chức năng quản lý hồ sơ/tài liệu/Mentor/chương trình chỉ hiện và chỉ được API cho Admin/HR. Tùy chọn giao diện gọn và toast được áp dụng thay vì chỉ lưu trong localStorage.
- Khôi phục thanh tìm kiếm/bộ lọc TTS và giữ thanh này trong vùng nhìn khi cuộn; cố định độ rộng cột, giảm padding hàng và cho bảng cuộn ngang ở màn hình hẹp. Khung upload được đưa về luồng dọc bên dưới hai ô chọn với lớp xếp chồng tách biệt. Bảng Mentor có độ rộng cột ổn định cho phòng ban, chuyên môn, kinh nghiệm và sức chứa.
- Các request danh mục phòng ban/trường đại học kiểm tra HTTP status và kiểu mảng trước khi ghi state. Phiên cũ trả 401 vì vậy không còn biến state thành object rồi làm ứng dụng trắng trang khi đăng nhập lại.
- Chương trình thực tập có form Admin đầy đủ, API xem/sửa/đóng đợt và bảng ứng tuyển riêng. TTS chỉ thấy chương trình đang mở, mỗi hồ sơ chỉ được ứng tuyển một lần; trạng thái đơn bắt đầu ở `ChoDuyet`, còn tài khoản vẫn `HoatDong` để sinh viên tiếp tục theo dõi kết quả. Admin xem danh sách ứng viên và duyệt/từ chối theo chỉ tiêu.

Đối chiếu chỉ đọc lại SQLite sau thay đổi: Lê Minh Tuấn ở hồ sơ #1 đang `DaDuyet` / tài khoản `HoatDong`; Hoàng Lan Anh ở hồ sơ #2 đang `TuChoi` / tài khoản `Khoa`; bảng tài liệu vẫn có 0 dòng. Hai hồ sơ thực sự đang `ChoDuyet` là Lê Quang Huy #9 và Đỗ Khánh Linh #14. Vì vậy dòng tài liệu mang tên Tuấn/Lan Anh trong ảnh cũ là dữ liệu React giả lập, không phải tệp lưu trong DB; sau chuyển sang API thật, hai dòng đó không được tự chép vào DB. Trong danh sách hồ sơ đầy đủ, #1 và #2 vẫn tồn tại ở cuối; khi bật lọc “Chờ duyệt” chúng không xuất hiện vì trạng thái hồ sơ hiện tại đã duyệt/từ chối.

Để kiểm tra runtime mà không làm thay đổi SQLite trong workspace, backend được khởi động từ một bản sao tạm của `backend/app` và frontend chạy từ workspace. File SQLite thật đã có bảng `MENTOR_PROFILE`, `CHUONG_TRINH_THUC_TAP` và hai cột metadata tài liệu `ten_file`, `kich_thuoc`; lượt kiểm tra này chỉ mở DB thật bằng `mode=ro`/`query_only` và không gọi API ghi lên DB thật.

Các giới hạn còn lại có chủ ý: hồ sơ #6 trỏ tới user #9 đã mất và không có căn cứ an toàn để gán lại/xóa; tệp gốc của ba dòng UI cũ không tồn tại; chưa có quan hệ phân công TTS-Mentor. Quan hệ ứng tuyển chương trình đã có nhưng không được dùng thay cho quan hệ Mentor hướng dẫn. SQLite local và MySQL dump vẫn là hai nguồn triển khai riêng, không tự đồng bộ dữ liệu giữa hai hệ quản trị.

## Nguồn dữ liệu từng phần

| Phần | Nguồn hiện tại | Kết quả |
|---|---|---|
| Quản lý thực tập sinh | `/api/interns`, JOIN hồ sơ + người dùng + trường + phòng ban | Đọc/ghi DB thật; còn lỗi quan hệ và trạng thái bên dưới |
| Quản trị người dùng | `/api/auth/users` và các API role/status | Đọc/ghi cùng bảng người dùng; hành vi duyệt khác màn hình thực tập sinh |
| Hồ sơ cá nhân, mật khẩu | `/api/auth/users/{id}/profile`, `/password` | Ghi DB thật; profile dùng chung người dùng với danh sách hồ sơ |
| Trường và phòng ban | `/api/master/*` | Đọc DB thật; mỗi bảng 4 dòng |
| Tài liệu | `/api/documents` + `TAI_LIEU_HO_SO` | Upload/lưu metadata/duyệt/mở tệp thật; DB hiện có 0 dòng nên UI đúng là rỗng |
| Mentor | `/api/mentors` + `NGUOI_DUNG`/`MENTOR_PROFILE` | UI đang đọc 4 tài khoản Mentor trong DB; thêm mới ghi bền vững |
| Chương trình | `/api/programs` + `CHUONG_TRINH_THUC_TAP` + `UNG_TUYEN_CHUONG_TRINH` | Admin quản lý đợt và ứng viên; TTS xem đợt mở, ứng tuyển và theo dõi trạng thái riêng |
| Số TTS/mentor, số ứng viên/chương trình | Ứng viên đếm từ đơn; Mentor chưa có bảng phân công | Số ứng viên là dữ liệu thật; số TTS Mentor phụ trách vẫn chờ mô hình phân công |
| Thông báo nghiệp vụ | `/api/notifications` + `THONG_BAO` | Hộp thông báo đọc DB; các quyết định duyệt tạo thông báo cho người liên quan |
| Tùy chọn thông báo/giao diện gọn | `ims_preferences` trong localStorage | Được navbar/toast/layout tiêu thụ trong cùng trình duyệt |

Runtime trên bản sao tạm đã tải thành công các màn hình intern, tài liệu, Mentor và chương trình qua API mới. Phiên cũ trả 401 vẫn được xử lý đúng; frontend không còn crash do gán payload lỗi vào state danh mục.

## Lỗi tại mã nguồn baseline `50b6b1d` đã xác minh

Các mục dưới đây là trạng thái trước khi áp dụng phần khắc phục ở trên; không mô tả trạng thái mã nguồn hiện tại.

### 1. Duyệt khác nhau tùy điểm thao tác

Nguồn: `auth_routes.py:293`, `auth_routes.py:403`, `intern_routes.py:94`; caller ở `AccountManagementView.jsx:154` và `InternManagementView.jsx:116`.

Thử riêng từng thao tác trên bản sao DB với user #17 / hồ sơ #14, ban đầu đều Chờ duyệt:

| Thao tác | Tài khoản sau thao tác | Hồ sơ sau thao tác |
|---|---|---|
| Nút Duyệt trong quản trị người dùng → `/status` | Hoạt động | Chờ duyệt |
| Nút Duyệt trong quản lý thực tập sinh → `/approve` | Hoạt động | Đã duyệt |
| Sửa hồ sơ, chọn Đã duyệt → `PUT /interns/14` | Chờ duyệt | Đã duyệt |

Đây là hành vi không thống nhất giữa các thao tác được trình bày như duyệt. Cần xác định rõ duyệt tài khoản và duyệt hồ sơ độc lập hay liên kết, rồi dùng quy tắc nhất quán. Việc khóa một tài khoản đã duyệt hồ sơ có thể hoàn toàn hợp lệ; không nên tự ép mọi trạng thái trùng nhau. Luồng tạo intern cũng khởi tạo tài khoản Hoạt động trong khi hồ sơ mặc định Chờ duyệt.

### 2. Hồ sơ mồ côi do khóa ngoại chưa được thực thi

DB có 16 hồ sơ nhưng truy vấn JOIN danh sách chỉ trả 15. Hồ sơ **#6 trỏ tới người dùng #9 không còn tồn tại**. `PRAGMA integrity_check` trả `ok`, nhưng `PRAGMA foreign_key_check` trả một vi phạm này: kiểm tra toàn vẹn cấu trúc không thay thế kiểm tra quan hệ.

`database.py:35` và `:43` mở connection nhưng không bật `PRAGMA foreign_keys=ON`. `auth_routes.py:451` chỉ xóa session và người dùng, trông chờ ON DELETE CASCADE. Thử xóa user #17 trên bản sao RAM vẫn còn hồ sơ #14, tái hiện cơ chế tạo hồ sơ mồ côi. Chưa có bằng chứng lịch sử thao tác cụ thể đã tạo ra hồ sơ mồ côi #6.

Cần sao lưu, chốt cách xử lý hồ sơ mồ côi và kiểm thử cascade trước khi sửa dữ liệu thật. Không tự xóa hoặc gán lại hồ sơ #6.

### 3. Mentor vẫn nằm trong danh sách thực tập sinh

Người dùng #8 “Nguyễn Văn Test” có vai trò Mentor nhưng vẫn có hồ sơ #5 và xuất hiện trong danh sách intern. `assign_role` ở `auth_routes.py:349` chỉ tự tạo hồ sơ khi chuyển sang ThucTapSinh, không thay đổi hồ sơ khi chuyển ra. `list_interns` không lọc vai trò.

Đổi user #17 sang Mentor trên RAM cũng giữ hồ sơ. Cần chốt việc bảo lưu hồ sơ lịch sử và danh sách nào được phép hiển thị; không nên tự xóa lịch sử chỉ để khớp nhãn vai trò. Màn hình Mentor hiện dùng dữ liệu mẫu nên cũng không phản ánh các lần đổi vai trò này.

### 4. Endpoint chi tiết dùng hai loại ID lẫn nhau

`intern_routes.py:82`: `WHERE h.ma_ho_so = ? OR h.ma_nguoi_dung = ?`. Modal sửa truyền mã hồ sơ, PUT cũng dùng mã hồ sơ, nhưng GET lại chấp nhận cả mã người dùng.

Trong DB hiện tại, ID 4 khớp hai hồ sơ (#4/user #7 và #1/user #4). Thử GET bằng hàm route với ID 6 trả hồ sơ #3 của Trần Đại Nghĩa, do hồ sơ #6 bị mất user còn user #6 có hồ sơ #3. Với 15 hồ sơ hiện đang hiển thị, kiểm tra GET theo mã hồ sơ chưa phát hiện trả sai. Đây là hợp đồng ID mơ hồ đã tái hiện ở ID 6, không phải bằng chứng mọi lần mở Sửa đều sai. Nên thống nhất GET/PUT theo `ma_ho_so`, tách truy vấn theo user ID nếu cần.

### 5. SQL dump/migration không phải schema SQLite đang chạy

`intership_management.sql` và migration dùng MySQL. Chúng có `avatar_url`, `updated_at`, UNIQUE số điện thoại; SQLite hiện không có các cột/ràng buộc này. SQLite có các bảng phiên và audit riêng. Không có cơ chế tự đồng bộ hai hệ quản trị. Dữ liệu seed MySQL cũng không hoàn toàn giống SQLite: seed tài khoản không gán phòng ban như Python và không tạo đủ cùng bộ hồ sơ ban đầu.

Trong DB local hiện không có nhóm email trùng sau lowercase/trim hoặc số điện thoại không rỗng trùng nhau. Tuy nhiên kiểm tra email khi tạo dùng so sánh nguyên chuỗi, còn login dùng lowercase; đây là điểm cần thống nhất để tránh tài khoản khác chữ hoa/thường trong tương lai.

### 6. Cập nhật giữa các phiên và hiển thị vai trò chưa thống nhất

Danh sách tài khoản/intern tải khi mount hoặc bấm làm mới; chưa nhận sự kiện thay đổi dữ liệu danh sách. WebSocket chỉ xử lý phiên và `ACCOUNT_UPDATED` của chính người dùng. Vì vậy cùng DB không có nghĩa mọi màn hình đang mở ở thiết bị khác sẽ cập nhật tức thì.

`App.jsx:153` và Navbar còn chức năng đổi góc nhìn bằng cách thay user/role mẫu ở client, không đổi token. `/auth/me` có thể kéo lại user thật sau đó; giao diện có thể lệch tạm thời so với phiên. Quyền backend hiện đọc identity từ DB qua token, không tin góc nhìn client này. Đây không phải bằng chứng có thể nâng quyền server bằng dropdown.

API danh sách/chi tiết intern yêu cầu đăng nhập qua middleware nhưng chưa giới hạn theo người sở hữu hoặc mentor phụ trách. Điều này cần được chốt cùng ma trận quyền khi nối các module, vì liên kết dữ liệu đúng vẫn phải đi kèm phạm vi truy cập đúng.

## Lịch sử GitHub

`git ls-remote origin` xác nhận HEAD remote, `main` và `feature/US01-auth` đều là `50b6b1d112014ec9276e39c2a82d4a51331600fd`, cùng HEAD local đang kiểm tra. Nhánh `main` local còn ở `d42e65d`, nhưng checkout hiện tại là `feature/US01-auth` ở commit mới. Repo lồng là checkout khác, không phải nguồn app chính.

| Commit | Ngày | Thay đổi liên quan |
|---|---|---|
| `457b10c` | 22/09 | README ban đầu |
| `0fff04e` | 24/09 | SQL MySQL ban đầu |
| `d42e65d` | 24/09 | Thêm app; tài liệu, Mentor, chương trình đã là giao diện mẫu ở đây |
| `1da2621` | 26/09 | Luồng tài khoản/UI, seed thêm dữ liệu, migration; Mentor đổi validation điện thoại, chương trình chỉ bỏ import thừa |
| `3afbb67` | 26/09 | Phiên đăng nhập và WebSocket; không nối ba module mẫu với DB |
| `0ad52c0` | 26/09 | AGENTS, README và báo cáo audit; không có thay đổi nghiệp vụ |
| `50b6b1d` | 26/09 | CSS và LoginView; không sửa đồng bộ dữ liệu |

`git log -- frontend/src/views/DocumentManagementView.jsx` chỉ có `d42e65d`: module tài liệu chưa được triển khai tiếp kể từ lúc đưa vào repo. Đây không phải lỗi thiếu pull bản mới nhất.

DB được Git theo dõi nhưng bản local đã thay đổi. Đọc bản DB của HEAD vào RAM cho thấy 9 người dùng, 6 hồ sơ, 0 tài liệu; DB local có 22 người dùng, 16 hồ sơ, 0 tài liệu. Lan Anh trong DB commit còn Chờ duyệt/Hoạt động, còn local là Từ chối/Khóa. Đồng bộ mã nguồn bằng Git không đồng bộ trạng thái DB đang chạy giữa các máy.

## Xác minh đã chạy

- `git status --short`, `git remote -v`, `git log --all`, `git show`, `git diff`, `git ls-remote origin`: đã đối chiếu lịch sử và trạng thái. Lần ls-remote trong sandbox không kết nối được; chạy lại với quyền mạng thành công.
- Các script Python qua `.\backend\.venv\Scripts\python -B -X utf8 -`: truy vấn DB chỉ đọc và gọi hàm route với connection được truyền tường minh. Thử ghi chỉ trên bản sao RAM, không gọi startup hoặc chạy background task trên DB thật.
- Ở snapshot audit: `PRAGMA integrity_check`: `ok`; `PRAGMA foreign_key_check`: một lỗi, hồ sơ #6 → user #9. Đọc lại chỉ-đọc sau khắc phục vẫn thấy đúng hồ sơ mồ côi này.
- Danh sách không lọc: 15 dòng, hai dòng cuối là Lan Anh #2 và Tuấn #1. Có 14 tài khoản ThucTapSinh, cả 14 đều có hồ sơ; dòng thứ 15 là tài khoản Mentor #8.
- Đã tái hiện ba kết quả duyệt khác nhau, xóa để lại hồ sơ, đổi role vẫn giữ hồ sơ và GET chi tiết ID 6 trả hồ sơ #3 trên các connection nêu trên.
- Backend OpenAPI: HTTP 200. Proxy danh mục không có token: HTTP 401 như dự kiến.
- Sau thay đổi: `npm run lint` và `npm run build` từ `frontend/`; `compileall -q app` từ `backend/`; cả ba chạy thành công. `git diff --check` cũng sạch sau khi bỏ khoảng trắng cuối dòng. Không có bộ test backend cấu hình sẵn.
- Kiểm tra luồng duyệt trên bản sao `:memory:`: khóa thủ công vẫn được giữ khi sửa thông tin hồ sơ đã duyệt; quyết định hồ sơ đổi trạng thái được truyền sang tài khoản; trạng thái tài khoản lệch không do khóa thủ công được đồng bộ và tạo thông báo. Không ghi vào SQLite local.
- Đọc lại DB bằng `mode=ro`/`query_only`: integrity `ok`, vẫn còn 1 vi phạm FK ở hồ sơ #6 → user #9; bảng tài liệu vẫn 0 dòng. Có thêm một lệch trạng thái chắc chắn ở Lê Quang Huy #9: hồ sơ `ChoDuyet`, tài khoản `HoatDong`; hồ sơ #5 thuộc tài khoản hiện mang vai trò Mentor nên không còn xuất hiện ở danh sách TTS.
- Chạy runtime với backend dùng bản sao DB tạm: trang TTS hiển thị lại đủ tìm kiếm và bốn bộ lọc; chọn `ChoDuyet` giảm bảng từ 14 xuống 2 dòng. Khung upload không còn đè lên select; trang Mentor hiển thị 4 dòng DB và cuộn ngang đúng ở viewport hẹp.
- Kiểm tra HTTP luồng chương trình trên bản sao DB tạm: tạo `201`, TTS xem danh sách `200`, ứng tuyển `201`, ứng tuyển trùng `400`, Admin đọc ứng viên `200`, duyệt `200`, đóng đợt `200`, ứng tuyển vào đợt đóng `400`, chỉnh sửa `200`; duyệt lặp trả `400`. HR/TTS gọi API tạo và TTS đọc danh sách ứng viên đều bị chặn `403`. Tài khoản TTS vẫn `HoatDong` sau khi đơn chuyển sang `ChoDuyet`.

## Việc còn lại cần xử lý riêng

- Quyết định chủ sở hữu đúng cho hồ sơ mồ côi #6 → user #9; không thể suy ra chỉ từ DB hiện tại.
- Sao lưu rồi quyết định cách sửa Lê Quang Huy #9 (`ChoDuyet`/`HoatDong`) và hồ sơ lịch sử #5 của tài khoản Mentor. Không tự sửa hai trường hợp này trong lượt UI vì yêu cầu giữ nguyên database.
- Tài liệu giả lập trong UI cũ không có tệp nguồn trong DB; nếu cần lưu trữ, người dùng phải tải lại các file thật qua màn hình upload mới.
- Nếu cần tính số TTS đang được Mentor hướng dẫn, cần chốt quy trình phân công và bổ sung bảng quan hệ Mentor–TTS; số ứng viên chương trình đã được tính từ đơn ứng tuyển thật.
- SQLite là DB ứng dụng local; dump/migration MySQL là triển khai riêng. Chúng không đồng bộ hàng dữ liệu tự động. Các cột MySQL không được app SQLite sử dụng chưa được thêm chỉ để tạo parity bề ngoài.
