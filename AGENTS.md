Tài liệu này kết hợp các nguyên tắc làm việc chung với thông tin kỹ thuật của hệ thống Internship Management. Hãy xem yêu cầu trực tiếp của người dùng và cấu trúc hiện có trong repository là căn cứ chính; không tự đưa quy chuẩn của dự án khác vào đây.

1. Trước khi thay đổi

- Đọc hướng dẫn này, sau đó kiểm tra đúng các route, component, schema, migration, câu lệnh SQL và nơi gọi liên quan đến yêu cầu.
- Kiểm tra git status trước khi sửa. Giữ nguyên mọi thay đổi có sẵn, tệp chưa theo dõi, cơ sở dữ liệu cục bộ và repository lồng nhau. Không dùng lệnh reset, clean, ghi đè hoặc xóa dữ liệu người dùng.
- Nêu rõ giả định nếu yêu cầu còn điểm chưa chắc chắn. Hỏi khi có nhiều cách hiểu làm thay đổi đáng kể phạm vi, dữ liệu hoặc kết quả; với lựa chọn nhỏ, có thể đảo ngược, hãy chọn cách đơn giản và nói ngắn gọn lý do.
- Với thay đổi qua nhiều module hoặc làm đổi hành vi, xác định ngắn gọn mục tiêu, phạm vi, tiêu chí chấp nhận và cách kiểm chứng trước khi triển khai.
- Chuyển yêu cầu thành kết quả có thể xác minh. Ví dụ: lỗi cần có cách tái hiện; tính năng cần đối chiếu tiêu chí chấp nhận; refactor cần xác nhận hành vi hiện tại vẫn đúng.

2. Nguyên tắc triển khai

- Ưu tiên thay đổi nhỏ nhất đáp ứng yêu cầu. Làm từng lát chức năng, theo luồng dữ liệu và kiểm tra các nơi gọi liên quan.
- Không thêm tính năng, dependency, công cụ, tệp sinh tự động, lớp trừu tượng hay cấu hình tổng quát nếu chưa có lợi ích cụ thể.
- Giữ phong cách và quy ước hiện có. Không tiện tay sửa, định dạng lại hoặc refactor phần ngoài phạm vi; nếu phát hiện vấn đề không liên quan, báo lại thay vì tự xử lý.
- Chỉ dọn import, biến hoặc hàm trở nên không còn dùng do chính thay đổi này. Không xóa mã cũ chỉ vì có vẻ không dùng.
- Mọi dòng thay đổi phải phục vụ yêu cầu hoặc tiêu chí chấp nhận. Nếu giải pháp trở nên dài hoặc phức tạp, xem lại xem có cách đơn giản hơn không.

3. Kiến trúc và dữ liệu của dự án

- Frontend hiện dùng React + Vite; backend dùng FastAPI. Trước khi chỉnh sửa, xác nhận cấu trúc và quy ước thực tế trong repository vì chúng có thể thay đổi.
- Runtime được cấu hình dùng MySQL (IMS_DATABASE_BACKEND=mysql). backend/app/internship.db là bản SQLite cục bộ cũ; SQLite cũng được dùng cho các bài kiểm thử cô lập.
- Xem mã nguồn, migration và schema của từng môi trường là những căn cứ riêng. Đọc migration và xác nhận môi trường trước khi thay đổi schema hoặc dữ liệu.
- Không chạy bộ test vào MySQL đang chạy hoặc cơ sở dữ liệu SQLite cục bộ nói trên. Không sửa, xóa hoặc nạp dữ liệu vào cơ sở dữ liệu thật/cục bộ nếu yêu cầu chưa cho phép rõ ràng.
- Dùng transaction khi một thao tác nghiệp vụ cần nhiều thay đổi dữ liệu phải thành công hoặc rollback cùng nhau. Chọn cơ chế khóa/chống tranh chấp dựa trên nghiệp vụ và cơ sở dữ liệu hiện có; không thêm khóa máy móc cho mọi thao tác.

4. Bảo mật và quyền truy cập

- Xem danh tính, phân quyền, dữ liệu đầu vào, thay đổi cơ sở dữ liệu và bí mật cấu hình là vùng nhạy cảm.
- Backend phải xác thực quyền dựa trên danh tính đáng tin cậy ở phía server. Header hoặc vai trò do client tự gửi không chứng minh người dùng có quyền.
- Kiểm tra quyền tại API/service trước khi đọc hoặc thay đổi dữ liệu; ẩn nút trên giao diện không thay thế kiểm soát phía server.
- Không ghi mật khẩu, token, khóa bí mật hoặc dữ liệu nhạy cảm vào mã nguồn, log, thông báo lỗi hay kết quả kiểm thử. Không nới lỏng xác thực hoặc phân quyền để làm test chạy qua.
- Với migration hoặc thay đổi dữ liệu có nguy cơ mất mát, kiểm tra tác động và cách rollback trước khi thực hiện.

5. Git và phối hợp thay đổi

- Làm theo branch, commit và pull request conventions đang có trong repository. Nếu chưa có quy ước, dùng tên nhánh ngắn, mô tả đúng phạm vi và kiểu commit rõ ràng.
- Không commit, push, tạo release, merge hoặc triển khai trừ khi người dùng yêu cầu rõ việc đó. Khi được yêu cầu, kiểm tra diff và trạng thái nhánh trước; không ghi đè thay đổi của người khác.
- Không dùng git push --force trên nhánh dùng chung. Chỉ dùng --force-with-lease trên nhánh cá nhân khi thật sự cần và người dùng đã yêu cầu thao tác liên quan.
- Không khẳng định đã review, merge, deploy hoặc nghiệm thu nếu chưa thực hiện và chưa có bằng chứng tương ứng.

6. Kiểm thử và xác minh

- Với lỗi, tái hiện và thêm kiểm tra hồi quy tập trung khi phù hợp. Với thay đổi nhỏ, ít rủi ro, có thể xác minh trực tiếp thay vì tạo test hình thức.
- Thay đổi frontend: từ frontend/, chạy npm run lint và npm run build.
- Thay đổi backend: từ backend/, dùng Python trong virtualenv của repository để chạy python -m compileall -q app và test cô lập python -m unittest discover -s tests -v.
- Trước khi chạy test backend, xác nhận cấu hình kiểm thử không trỏ tới MySQL đang chạy hay backend/app/internship.db. Nếu chưa thể xác nhận, không chạy test có nguy cơ ghi dữ liệu vào các nguồn đó; báo rõ giới hạn xác minh.
- Chạy các kiểm tra phù hợp với phần đã đổi. Chỉ nói lệnh nào đã pass nếu lệnh đó thực sự chạy thành công; ghi rõ kiểm tra nào chưa chạy và lý do.

7. Hoàn tất công việc

- Rà soát diff cuối về phạm vi, hành vi, bảo mật, mã thừa do thay đổi, trùng lặp và tên gọi.
- Xác nhận tiêu chí chấp nhận bằng test hoặc bằng chứng kiểm tra cụ thể. Không xem “đã viết code” là đồng nghĩa với “đã hoàn tất”.
- Báo ngắn gọn những gì đã đổi, lý do, lệnh kiểm tra và kết quả thực tế; nêu giới hạn còn lại nếu có.
