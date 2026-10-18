# US38 — Quyết định phạm vi

Theo quyết định của chủ dự án, QR và CARD không thuộc phạm vi triển khai hiện tại. Không có giao diện, route, endpoint hoặc service nào được dùng để tạo/scan credential chấm công QR; chưa tích hợp thiết bị thẻ hoặc vân tay.

Luồng check-in/check-out bằng tài khoản hiện có, quy tắc US21/US23, nghỉ phép, báo cáo và lịch sử chấm công được giữ nguyên. Đường dẫn frontend QR cũ chuyển về `/attendance`; endpoint API QR cũ không còn tồn tại nên không thể ghi chấm công.

Migration, bảng và cột QR đã tồn tại được giữ nguyên để không xóa dữ liệu hoặc thay đổi schema database. Việc dọn schema vật lý, nếu cần, phải được đề xuất trong migration riêng và không thuộc task này.
