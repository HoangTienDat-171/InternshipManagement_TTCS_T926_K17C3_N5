# Bàn giao Sprint 2 → Sprint 3

Ngày ghi nhận: 2026-10-06. Tài liệu này chốt tiến độ đã tích hợp và các việc cần nhớ khi tiếp tục dự án; đối chiếu thêm lịch sử Git và backlog/PO khi bắt đầu Sprint 3.

## Mốc Git đã xác minh

- `origin/main`: `47d513f` — PR #16 đã merge nhánh `fix/us23-shift-creation-ux`. Commit tính năng `92c503a` nằm trong lịch sử của `main`.
- `origin/develop`: `af26bcd` — là tổ tiên của `origin/main`, nhưng chưa chứa PR #16/mốc `main` mới nhất.
- Vì vậy, phát biểu “PR main → develop đã merge” chưa khớp với refs đang có trên GitHub tại thời điểm ghi tài liệu này. Cần đồng bộ bằng PR có base `develop`, compare `main`; không reset hoặc force-push.
- Nhánh tài liệu `docs/sprint2-handoff` được tạo từ `origin/main`, để PR vào `develop` có thể đồng bộ baseline Sprint 2 cùng ghi chú này.

## Tiến độ tính năng

Sprint 1 là baseline trước Sprint 2. Các US Sprint 2 dưới đây đã có implementation trong lịch sử tích hợp `origin/main` theo phạm vi backlog đã thống nhất:

| US | Tiến độ / phạm vi đã ghi nhận |
| --- | --- |
| US08 | Thông báo kết quả xét duyệt và email qua outbox/worker; trạng thái gửi được theo dõi trong ứng dụng. |
| US09 | Hỗ trợ nhiều hợp đồng thực tập. |
| US10 | Xác nhận hợp đồng và lưu quyết định/lịch sử. |
| US14 | Lịch cá nhân của thực tập sinh. Guest Portal không phải luồng đang hoạt động. |
| US15 | Mentor giao nhiệm vụ cho thực tập sinh. |
| US16 | Thực tập sinh cập nhật tiến độ nhiệm vụ và lịch sử thay đổi. |
| US17 | Thực tập sinh nộp báo cáo tuần. |
| US18 | Mentor xem xét, nhận xét và phản hồi báo cáo; có kiểm tra quyền theo phân công. |
| US19 | Mentor đánh giá thực tập sinh; bộ lọc chương trình hiển thị chương trình thực tập sinh đã đăng ký. |
| US21 | Chấm công vào/ra và xem lịch sử chấm công. |
| US23 | Quản lý ca làm việc linh hoạt và liên kết phạm vi/chương trình. |

### Phần hoàn thiện gần nhất — PR #16

Các thay đổi ở `92c503a` (đã nằm trong `origin/main` qua PR #16):

- HR được phép tạo chương trình thực tập và phân công thực tập sinh cho Mentor; quyền được kiểm tra ở API/backend.
- HR có thao tác gỡ phân công Mentor–thực tập sinh, kèm hộp xác nhận theo giao diện thay cho hộp thoại trình duyệt thô.
- Hoàn thiện luồng tạo ca làm việc và một số căn chỉnh/feedback UI liên quan.
- Bổ sung/cập nhật kiểm thử backend cho các luồng này.

## Kết quả kiểm tra gần nhất

Trên source `92c503a`, trước khi PR #16 được merge:

- Backend `compileall`: PASS.
- Backend unit tests: **113/113 PASS**; test dùng SQLite cô lập, không ghi vào MySQL runtime hay `backend/app/internship.db`.
- Frontend `npm run lint`: PASS.
- Frontend `npm run build`: PASS.

Đây là kết quả kiểm tra source trước PR #16; tài liệu này không thay đổi mã chạy. Chạy lại kiểm tra phù hợp trên baseline mới khi thực hiện thay đổi tiếp theo.

## Việc còn phải xác minh / lưu ý vận hành

1. **Email thật:** US08 đã có luồng outbox/worker, nhưng người dùng đã báo email thực tế không gửi được. Chưa đánh dấu SMTP end-to-end là đạt. Khi tiếp tục, kiểm tra cấu hình SMTP local và trạng thái outbox/worker bằng tài khoản demo thật đã có; không đưa `.env`, App Password, token hay email nhạy cảm vào Git/log. Không dùng dữ liệu ảo thay cho dữ liệu người dùng yêu cầu kiểm tra.
2. **Database:** runtime local dùng MySQL schema `internship_management`; `backend/app/internship.db` là SQLite cũ. Tuyệt đối không chạy test/migration vào DB runtime hoặc file SQLite này. Test backend phải giữ cấu hình SQLite tạm/cô lập.
3. **Mailbox / Guest Portal:** không thấy route/entry point hoạt động trong source hiện tại. Đường dẫn cũ `/mailbox` được chuyển về `/`; bộ lọc loại thông báo `mailbox_message` còn lại là tương thích dữ liệu. Không xóa phần tương thích nếu chưa có yêu cầu.
4. **Dữ liệu demo:** giữ nguyên dữ liệu MySQL và file upload hiện có; không seed/reset/xóa dữ liệu để kiểm thử.

## Cách tiếp tục Sprint 3

1. Merge PR đồng bộ `main → develop` với base `develop`; refs hiện tại cho thấy `develop` chưa có PR #16.
2. Sau khi đồng bộ xong, tạo nhánh từng US từ `develop` mới nhất; không làm Sprint 3 trực tiếp trên `main`.
3. Mỗi PR nên ghi US, tiêu chí PO, API/UI/schema bị ảnh hưởng, kiểm tra đã chạy và việc còn mở; chỉ promote `develop → main` khi đã review/verify hoàn chỉnh.
4. Khi người dùng yêu cầu bắt đầu Sprint 3, đọc lại `AGENTS.md`, tài liệu dự án, file handoff này, trạng thái Git/backlog mới nhất; không giả định refs hoặc trạng thái runtime vẫn như ngày ghi nhận.
