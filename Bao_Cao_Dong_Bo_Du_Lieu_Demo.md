# Báo cáo đồng bộ dữ liệu demo Internship Management

Ngày kiểm tra: 28/09/2026. Dữ liệu được tạo qua API đang chạy tại `127.0.0.1:8000`, kết nối MySQL hiện tại. Không đổi schema, không chạy migration và không sửa hoặc xóa các hồ sơ đã có. Dùng tài khoản Admin dự phòng để giữ nguyên phiên Admin đang mở trên trình duyệt.

## Kết quả dữ liệu

| Chỉ số | Kết quả |
|---|---:|
| Hồ sơ thực tập sinh | 60 |
| Mentor | 10 |
| Chương trình thực tập | 6 |
| Hồ sơ ứng tuyển | 64 |
| Tài liệu | 64 |
| CV | 57 |
| Phân công Mentor–TTS | 20 |

Phân bổ ứng tuyển: PREVIEW-01 có 9; DEMO-2026-BE có 10; DEMO-2026-DATA có 11; DEMO-2026-QA có 10; DEMO-2026-SEC và DEMO-2026-FE mỗi chương trình có 12. Tổng cộng có 11 hồ sơ đã duyệt và 53 hồ sơ chờ xử lý. 25 sinh viên demo có CV; 8 hồ sơ TTS demo khác được giữ trống ứng tuyển và tài liệu để thử trạng thái rỗng. Dữ liệu cũng có hồ sơ chờ duyệt, hoàn thành và thôi học.

## Bổ sung chương trình và ứng viên demo

Theo yêu cầu mở rộng danh sách ứng viên, đã tạo qua API hai chương trình đang mở: `DEMO-2026-SEC` (Thực tập An ninh mạng & Cloud, phòng ban 2) và `DEMO-2026-FE` (Thực tập Frontend React & UI/UX, phòng ban 1). Mỗi chương trình có chỉ tiêu 12 và 12 hồ sơ TTS riêng đang chờ duyệt. 24 hồ sơ được nộp qua luồng ứng tuyển chính thức, kèm CV PDF riêng, vì vậy dữ liệu liên kết đầy đủ với hồ sơ sinh viên và tài liệu.

Đối chiếu sau khi bổ sung: 6 chương trình, 64 ứng tuyển, 64 tài liệu (57 CV), 60 hồ sơ TTS; cả 24 tệp CV mới đều tồn tại, khớp kích thước metadata và được `pdfinfo` đọc thành công. Không thay đổi schema hoặc sửa/xóa dữ liệu hiện hữu.

## Báo cáo kiểm tra đồng bộ

| Kiểm tra | Kết quả |
|---|---|
| Admin API: KPI và danh sách TTS, Mentor, chương trình, tài liệu | PASS |
| Mentor: hồ sơ cá nhân và số TTS trong workspace khớp phân công | PASS, kiểm tra 5 tài khoản |
| TTS: hồ sơ, ứng tuyển, Mentor và tài liệu cá nhân | PASS, kiểm tra 6 tài khoản |
| Ứng tuyển thuộc đúng hồ sơ và chương trình | PASS |
| KPI TTS đã ghép Mentor bằng số phân công thực tế | PASS, 20 = 20 |
| Sức chứa Mentor | PASS, không Mentor nào vượt sức chứa |
| Đổi Mentor qua API: profile #33 từ Mentor #30 sang Mentor #79 | PASS |
| Mở PDF qua API: HTTP 200, MIME `application/pdf`, tên tệp đúng | PASS |
| Phân quyền file: chủ hồ sơ và Mentor được phân công xem được; tài khoản khác nhận 404 | PASS |
| File vật lý và metadata MySQL | PASS, 40/40 tệp tồn tại; pdfinfo đọc được cả 40, chữ ký PDF, EOF và dung lượng khớp; một CV đã render và kiểm tra trực quan |
| TTS có trạng thái rỗng | PASS |

## Năm trường hợp đối chiếu xuyên hệ thống

Danh sách Admin, ứng tuyển chương trình, tài liệu, workspace TTS và workspace Mentor đều được gọi qua API thật. Mã hồ sơ, mã ứng tuyển, mã chương trình, Mentor và CV được so khớp.

| # | Sinh viên | Profile ID | Application ID | Chương trình / trạng thái | Mentor | Admin | Sinh viên | Mentor |
|---:|---|---:|---:|---|---|---|---|---|
| 1 | Nguyễn Thành Hưng | 33 | 11 | PREVIEW-01 / Đã duyệt | Nguyễn Thanh Hương (#79) | PASS | PASS | PASS |
| 2 | Trần Minh Anh | 34 | 13 | DEMO-2026-BE / Đã duyệt | Lê Thu Hà (#31) | PASS | PASS | PASS |
| 3 | Lê Hoàng Nam | 35 | 15 | DEMO-2026-DATA / Đã duyệt | Phạm Quốc Việt (#32) | PASS | PASS | PASS |
| 4 | Phạm Ngọc Mai | 36 | 17 | DEMO-2026-QA / Đã duyệt | Phạm Quốc Việt (#32) | PASS | PASS | PASS |
| 5 | Đỗ Quốc Bảo | 37 | 19 | PREVIEW-01 / Đã duyệt | Nguyễn Ngọc Mai (#33) | PASS | PASS | PASS |

## Tải Mentor sau phân công

| Mentor | TTS / sức chứa |
|---|---:|
| Nguyễn Thanh Hương | 3/3 |
| Đỗ Thành Nam | 3/3 |
| Nguyễn Ngọc Mai | 3/3 |
| Phạm Quốc Việt | 3/3 |
| Lê Thu Hà | 3/3 |
| Trần Minh Đức | 2/3 |
| Nguyễn Văn Test | 2/3 |
| Nguyễn Văn Hướng | 1/3 |
| Trần Quốc Bảo | 0/3 |
| Nguyễn Hải Đăng | 0/3 |

Đủ các mức tải `0/3`, `1/3`, `2/3`, `3/3`. Tổng 20 phân công trong MySQL khớp KPI Mentor và TTS đã ghép. Mentor mới Nguyễn Thanh Hương có chuyên môn Quản lý sản phẩm/Agile, 12 năm kinh nghiệm và đang phụ trách 3 TTS.

## Tài liệu và tài khoản demo

Tệp nằm trong `backend/app/uploads/documents/`. Backend chỉ hỗ trợ các loại `CV`, `DonXinThucTap`, `GiayGioiThieu`; dữ liệu đã dùng đúng các loại này. 33 CV được tạo từ luồng ứng tuyển thật; 7 tài liệu khác được tải qua API tài liệu. PDF có thông tin sinh viên, trường, chuyên ngành, kỹ năng và chương trình.

Tài khoản TTS mới theo mẫu `demo.seed.tts.01@internship.vn` đến `demo.seed.tts.37@internship.vn`; Mentor mới là `demo.seed.mentor10@internship.vn`. Mật khẩu khởi tạo là `123456`, theo cấu hình demo local của dự án. Đổi mật khẩu trước khi đưa môi trường ra ngoài máy local.

Ứng tuyển và tài liệu trong schema hiện liên kết qua cùng `ma_ho_so`; bảng ứng tuyển không có `document_id` trực tiếp. API workspace và file đã được kiểm tra để xác nhận CV thuộc đúng hồ sơ sinh viên.

Đã kiểm tra trực tiếp API, MySQL, file và quyền truy cập. Không tự động thao tác giao diện trình duyệt; các màn hình sử dụng các API này sẽ đọc cùng dữ liệu sau khi tải lại.
