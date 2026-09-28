# Báo cáo hoàn tất và nghiệm thu Sprint 1

**Ngày rà soát:** 28/09/2026<br>
**Phạm vi:** US39, US01, US02, US03, US29, US11, US04 và phần UI/UX liên quan.<br>
**Kết luận:** Các luồng Sprint 1 và phân trang danh sách quản lý đã được kiểm thử API trên SQLite cô lập và trên schema MySQL tạm có cấu trúc lấy từ schema hiện hành (chỉ sao chép định nghĩa bảng, không sao chép dữ liệu). CRUD, upload CV, phân công Mentor–TTS và thu hồi phiên trên MySQL đều đạt. CSDL MySQL đang sử dụng chỉ được truy vấn đọc, không ghi dữ liệu.

## 1. Kết quả theo User Story

| User Story | Kết quả | Bằng chứng và giới hạn |
|---|---|---|
| US39 – Tạo tài khoản và đăng nhập | Đã kiểm thử API trên SQLite và MySQL cô lập | Với Admin, HR/Quản lý, Mentor và TTS: đăng nhập thiết bị thứ hai làm token cũ nhận HTTP 401, token mới còn hiệu lực. Trên SQLite, WebSocket cũ nhận `FORCE_LOGOUT`. Trên MySQL cô lập, đã xác nhận thu hồi token cho cả bốn vai trò. Không chạy phép thử ghi phiên trên CSDL MySQL đang dùng. |
| US01 – Tạo hồ sơ thực tập sinh | Đã kiểm thử API trên SQLite và MySQL cô lập | Tạo, đọc và cập nhật hồ sơ thành công trên cả hai backend cô lập; quyền tạo vai trò TTS/Mentor bị từ chối trong bộ test SQLite. |
| US02 – Cập nhật hồ sơ thực tập sinh | Đã kiểm thử API trên SQLite và MySQL cô lập | Cập nhật họ tên/email, trường, ngành và đọc lại dữ liệu sau cập nhật trên cả hai backend cô lập. |
| US03 – Tìm kiếm, lọc và phân trang | Đã triển khai và kiểm thử | API dùng `page`, `pageSize`, `COUNT`, `LIMIT/OFFSET`; kết quả tìm kiếm và bộ lọc được tính trước khi phân trang. Kiểm thử 15 hồ sơ, trang đầu/trang giữa/trang vượt tổng số, trang rỗng và kích thước không hợp lệ. Đã kiểm tra phản hồi phân trang MySQL; giao diện đã kiểm tra chuyển từ 1–10 sang 11–12 hồ sơ. |
| US29 – Thêm Mentor | Đã kiểm thử API trên SQLite và MySQL cô lập | Tạo, sửa chuyên môn/kinh nghiệm/sức chứa và đọc lại danh sách. Trên MySQL cô lập, tạo Mentor và phân công TTS thành công; số lượng TTS phụ trách khớp giữa danh sách Mentor và hồ sơ TTS. |
| US11 – Tạo chương trình thực tập | Đã kiểm thử API trên SQLite và MySQL cô lập | Tạo, sửa và đọc lại chương trình; không ghi vào dữ liệu MySQL đang dùng. |
| US04 – Upload CV/đơn xin thực tập | Đã triển khai và kiểm thử | Kiểm tra quyền sở hữu, loại tài liệu, định dạng, tệp rỗng, giới hạn 15 MB và tải tệp của TTS khác trên SQLite cô lập. Trên MySQL cô lập, xác nhận upload CV, gắn đúng hồ sơ và xuất hiện trong danh sách tài liệu. Giao diện có bộ chọn loại tài liệu và đổi nhãn nút theo lựa chọn. |
| Phân trang danh sách quản lý | Đã triển khai và kiểm thử | Đã thêm phân trang máy chủ cho Quản trị Người dùng, Mentor, Chương trình, Ứng viên của chương trình và Tài liệu; giữ phân trang/tìm kiếm/lọc hiện có của TTS. Bộ xuất CSV tải đủ mọi trang. API vẫn giữ phản hồi mảng cũ nếu client không gửi tham số phân trang. |
| UI/UX Light/Dark và bố cục | Đã rà soát một phần | Đã xem giao diện sáng/tối, tương phản mục đang chọn, bảng, phân trang và bộ chọn tài liệu. Ở chiều rộng trình duyệt 1270 px, thanh lọc bị tràn; đã cho các bộ lọc xuống dòng và xác nhận lại không còn tràn khung. Chưa mô phỏng riêng màn hình điện thoại và chưa kiểm tra lưu theme qua reload trong lượt này. |

## 2. Các thay đổi đã thực hiện

- API các danh sách hồ sơ TTS, người dùng, Mentor, chương trình, ứng viên và tài liệu trả cấu trúc phân trang gồm `items`, `page`, `pageSize`, `totalItems`, `totalPages`. Trang vượt quá trang cuối được đưa về trang hợp lệ; tìm kiếm/bộ lọc được tính trước khi phân trang.
- Các bảng quản lý có điều khiển số dòng, trang trước/sau và chỉ báo khoảng bản ghi. Bộ xuất CSV tài khoản tải đủ mọi trang; bộ chọn hồ sơ TTS trong biểu mẫu tài liệu vẫn đọc mọi trang để không thiếu lựa chọn.
- Cho phép TTS nộp `CV` hoặc `DonXinThucTap`, đồng thời giữ kiểm tra vai trò, chủ sở hữu hồ sơ, chữ ký định dạng tệp và giới hạn dung lượng hiện có.
- Thêm `IMS_SQLITE_PATH` để bài kiểm thử tạo CSDL riêng. Mặc định runtime MySQL không thay đổi. Thêm `VITE_API_PROXY_TARGET` để chạy giao diện với API kiểm thử cục bộ.
- Cập nhật hướng dẫn để nêu rõ MySQL là backend runtime; SQLite là bản dữ liệu cũ hoặc dùng cho kiểm thử cô lập. Cập nhật tên schema trong phần đầu migration cho khớp schema MySQL `internship_management`. Migration không được chạy.
- Thêm `backend/tests/test_sprint1_completion.py` làm bộ hồi quy tích hợp tối thiểu; cập nhật `backend/requirements.txt` với `wsproto==1.2.0`.

## 3. Kết quả kiểm tra

Các bài kiểm thử API khởi chạy Uvicorn trên cổng tạm. Bộ hồi quy chính dùng SQLite riêng; kiểm thử bổ sung chạy backend trên schema MySQL tạm được tạo từ 13 định nghĩa bảng của schema hiện hành, không sao chép dữ liệu. Hồ sơ, tài khoản và tài liệu kiểm thử chỉ tồn tại trong môi trường tạm.

| Lệnh | Kết quả |
|---|---|
| `npm run lint` từ `frontend/` | Đạt, không có cảnh báo. |
| `npm run build` từ `frontend/` | Đạt; Vite tạo bản build. |
| `.\.venv\Scripts\python -m compileall -q app tests` từ `backend/` | Đạt. |
| `.\.venv\Scripts\python -m unittest discover -s tests -v` từ `backend/` | Đạt: 6 ca kiểm thử. |

Kiểm tra chỉ đọc trên MySQL đang dùng xác nhận schema `internship_management`; số liệu gần nhất là 36 tài khoản, 23 hồ sơ thực tập và 0 tài liệu. Kiểm thử đầu-cuối chạy trên schema tạm riêng: thêm fixture, kiểm tra CRUD, upload, phân công Mentor–TTS và session; sau đó xóa đúng schema tạm do lượt kiểm thử tạo. Không chạy migration, không ghi/xóa bản ghi trên MySQL đang dùng, không sửa tệp SQLite cũ.

## 4. Phần còn cần quyết định trước khi xác nhận nghiệm thu hoàn toàn

1. **Kiểm thử giao diện CRUD trên trình duyệt:** API được kiểm tra qua MySQL cô lập và SQLite cô lập; chưa thao tác form trên trình duyệt cho tất cả vai trò để xác nhận thông báo, lỗi và điều hướng thực tế.
2. **Kiểm thử kích thước điện thoại và ghi nhớ theme sau tải lại:** Đã kiểm tra hai theme và bố cục hẹp ở 1270 px; chưa kiểm tra viewport điện thoại và việc lưu theme sau reload trong lượt nghiệm thu này.
3. **Khởi tạo MySQL từ schema trắng:** `init_mysql_db()` cần các bảng lõi như `NGUOI_DUNG` tồn tại trước khi tạo bảng phụ có khóa ngoại. Môi trường hiện hành đã có schema; để dựng mới, cần nạp DDL/migration theo quy trình riêng trước khi khởi động backend.
4. **Đồng bộ file Product Backlog:** Báo cáo này không sửa workbook Product Backlog bên ngoài thư mục dự án. Cập nhật trạng thái các ô trong workbook cần thực hiện riêng sau khi thống nhất quy ước trạng thái nghiệm thu.

Các API và xử lý dữ liệu đạt kiểm thử kỹ thuật trên SQLite và MySQL cô lập; để ký nghiệm thu sản phẩm hoàn toàn, còn cần xác nhận UI qua trình duyệt và kiểm tra màn hình điện thoại/theme reload. CSDL MySQL đang dùng không bị thay đổi.
