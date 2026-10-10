Tài liệu này kết hợp các nguyên tắc làm việc chung với thông tin kỹ thuật của hệ thống Internship Management. Hãy xem yêu cầu trực tiếp của người dùng và cấu trúc hiện có trong repository là căn cứ chính; không tự đưa quy chuẩn của dự án khác vào đây.

Tài liệu này quy định các nguyên tắc làm việc chung cho AI Coding Agent trong mọi dự án phần mềm. Hãy xem yêu cầu trực tiếp của người dùng, hướng dẫn riêng của repository và cấu trúc mã nguồn hiện có là căn cứ chính. Không tự áp dụng công nghệ, quy tắc nghiệp vụ, cấu hình hoặc giả định từ dự án khác.

Mục tiêu là triển khai chính xác, đơn giản, an toàn, bảo vệ dữ liệu, tôn trọng quy trình Git và chỉ công bố kết quả khi có bằng chứng kiểm chứng.

## 1. Trước khi thay đổi

- Đọc `AGENTS.md`, README, tài liệu liên quan và các hướng dẫn riêng của repository trước khi thực hiện.
- Kiểm tra cấu trúc dự án, các module, route, component, service, schema, migration, API và những nơi gọi có liên quan đến yêu cầu.
- Kiểm tra Git history, branch hiện tại, các commit và Pull Request liên quan để hiểu trạng thái mới nhất, những gì đã hoàn thành và công việc đang dang dở.
- Không mặc định nhánh hiện tại là nhánh mới nhất hoặc chứa đầy đủ mã nguồn cần thiết.
- Kiểm tra `git status` trước khi sửa. Giữ nguyên mọi thay đổi có sẵn, tệp chưa theo dõi, cấu hình cục bộ, cơ sở dữ liệu và repository lồng nhau.
- Không sử dụng `git reset --hard`, `git clean`, ghi đè, xóa dữ liệu hoặc thay đổi lịch sử Git khi chưa được cho phép rõ ràng.
- Nêu rõ giả định nếu yêu cầu còn điểm chưa chắc chắn. Hỏi khi có nhiều cách hiểu làm thay đổi đáng kể phạm vi, dữ liệu, bảo mật hoặc kết quả.
- Với lựa chọn nhỏ, có thể đảo ngược và không ảnh hưởng nghiệp vụ quan trọng, chọn giải pháp đơn giản nhất và giải thích ngắn gọn lý do.
- Với thay đổi qua nhiều module hoặc làm thay đổi hành vi hệ thống, xác định mục tiêu, phạm vi, tiêu chí chấp nhận và cách kiểm chứng trước khi triển khai.
- Chuyển yêu cầu thành kết quả có thể xác minh: lỗi cần có cách tái hiện, tính năng cần đáp ứng acceptance criteria, refactor cần giữ nguyên hành vi đã được chấp nhận.
- Không bắt đầu sửa mã nguồn khi chưa hiểu luồng dữ liệu và tác động của thay đổi.

## 2. Nguyên tắc triển khai

- Ưu tiên thay đổi nhỏ nhất đáp ứng đầy đủ yêu cầu.
- Triển khai theo từng phần chức năng có thể kiểm chứng, theo dõi luồng dữ liệu từ đầu vào đến kết quả cuối.
- Giữ nguyên kiến trúc, phong cách lập trình, naming convention và các quy ước hiện có nếu chúng phù hợp.
- Tái sử dụng component, service, utility, validation và cơ chế xử lý đã có thay vì tạo phiên bản trùng lặp.
- Không tự thêm tính năng, dependency, công cụ, file sinh tự động, lớp trừu tượng hoặc cấu hình tổng quát khi chưa có lợi ích cụ thể.
- Không thiết kế hệ thống phức tạp để giải quyết một yêu cầu đơn giản.
- Không tự refactor toàn bộ dự án, đổi cấu trúc thư mục hoặc định dạng lại file ngoài phạm vi.
- Không sửa các lỗi không liên quan chỉ vì tình cờ phát hiện. Báo cáo riêng nếu cần.
- Chỉ xóa import, biến, hàm hoặc mã trở nên không còn sử dụng do chính thay đổi đang thực hiện.
- Không xóa mã cũ chỉ vì có vẻ không được sử dụng; phải xác minh các nơi gọi và tác động trước.
- Không tạo API, database table, UI component hoặc service trùng với chức năng đã tồn tại.
- Mọi dòng thay đổi phải phục vụ yêu cầu, tiêu chí chấp nhận hoặc tính an toàn trực tiếp của giải pháp.
- Nếu giải pháp trở nên quá dài hoặc phức tạp, xem xét liệu có cách đơn giản hơn mà vẫn đáp ứng đầy đủ yêu cầu hay không.
- Không thay đổi business rule đã được nghiệm thu nếu người dùng không yêu cầu.

## 3. Kiến trúc và dữ liệu

- Trước khi triển khai, xác định framework, ngôn ngữ, database, cấu trúc thư mục và cơ chế cấu hình thực tế của repository.
- Không giả định dự án sử dụng một công nghệ cụ thể.
- Xem source code, migration, schema, configuration và tài liệu là những nguồn thông tin cần đối chiếu; không mặc định chúng luôn đồng bộ.
- Khi thay đổi API, database hoặc cấu trúc dữ liệu, kiểm tra tất cả module và nơi sử dụng có liên quan.
- Bảo đảm dữ liệu nhất quán giữa database, backend, frontend và các service liên quan.
- Không sử dụng dữ liệu giả hoặc hardcode kết quả để thay thế chức năng thực tế khi yêu cầu cần dữ liệu thật.
- Không tự tạo hoặc sửa dữ liệu nghiệp vụ nhằm làm cho giao diện có vẻ hoạt động.
- Trước khi chạy migration, xác định database và môi trường thực tế đang được kết nối.
- Không chạy test có khả năng ghi vào production database hoặc database chứa dữ liệu người dùng.
- Không tự xóa, reset, truncate, reseed hoặc ghi đè database khi chưa được cho phép rõ ràng.
- Với migration hoặc thao tác có nguy cơ mất dữ liệu, đánh giá tác động, sao lưu và chuẩn bị phương án phục hồi phù hợp.
- Migration phải bảo đảm tương thích với dữ liệu hiện có và tránh tạo trùng schema khi chạy lại.
- Sử dụng transaction khi nhiều thay đổi dữ liệu phải thành công hoặc rollback cùng nhau.
- Xử lý concurrency, race condition và duplicate khi nghiệp vụ có nguy cơ phát sinh tranh chấp.
- Không thêm locking hoặc transaction phức tạp một cách máy móc khi không cần thiết.
- Không thay đổi cấu hình production hoặc secret chỉ để làm môi trường local chạy được.

## 4. Bảo mật và quyền truy cập

- Xem authentication, authorization, dữ liệu đầu vào, file upload, database mutation và secret là các vùng nhạy cảm.
- Không tin tưởng danh tính, vai trò hoặc quyền truy cập do client tự gửi.
- Backend hoặc tầng xử lý đáng tin cậy phải xác thực người dùng và kiểm tra quyền trước khi đọc, tạo, sửa hoặc xóa dữ liệu.
- Kiểm tra ownership và phạm vi truy cập theo business rule thực tế.
- Không chỉ ẩn nút trên frontend để thay thế kiểm soát quyền ở backend.
- Chống IDOR, mass assignment, truy cập trái phép và thao tác vượt quyền khi có liên quan.
- Validate dữ liệu đầu vào ở đúng tầng xử lý.
- Với file upload, kiểm tra loại file, dung lượng, đường dẫn lưu trữ và quyền truy cập khi chức năng yêu cầu.
- Không để dữ liệu riêng tư hoặc file nhạy cảm truy cập công khai ngoài phạm vi cho phép.
- Không hardcode mật khẩu, token, API key hoặc thông tin bí mật.
- Không ghi secret vào source code, log, thông báo lỗi, test output hoặc báo cáo.
- Không commit `.env` chứa secret, database dump, private key hoặc dữ liệu nhạy cảm.
- Không vô hiệu hóa authentication, authorization hoặc validation để khiến test chạy thành công.
- Không tự mở rộng quyền của một role nếu chưa có căn cứ từ yêu cầu hoặc business rule.
- Với thay đổi bảo mật quan trọng, phải kiểm tra cả trường hợp được phép và bị từ chối.

## 5. Git và phối hợp thay đổi

- Trước khi thực hiện, kiểm tra branch, worktree, remote, commit history và Pull Request liên quan.
- Xác định chính xác baseline mới nhất trước khi tạo branch.
- Với workflow phát triển sử dụng `develop`, luôn lấy `origin/develop` mới nhất làm nền cho feature mới.
- Mỗi tính năng hoặc nhóm tính năng liên quan phải được triển khai trên nhánh riêng như `feature/*`, `fix/*` hoặc `chore/*`.
- Không code, commit hoặc push trực tiếp lên `develop`.
- Không code, commit hoặc push trực tiếp lên `main`.
- `develop` là nhánh tích hợp các tính năng đã hoàn thành và được review.
- Chỉ tích hợp feature vào `develop` thông qua Pull Request sau khi kiểm thử và được phép merge.
- `main` phải được giữ nguyên trong suốt quá trình phát triển; chỉ xem xét tích hợp `develop` vào `main` khi toàn bộ dự án hoàn tất, kiểm thử đầy đủ và được owner phê duyệt.
- Nếu repository có workflow khác, phải đối chiếu với hướng dẫn dự án và yêu cầu trực tiếp của người dùng trước khi áp dụng.
- Không commit, push, tạo PR, merge, release hoặc deploy nếu chưa được yêu cầu hoặc cho phép rõ ràng.
- Khi được phép commit, kiểm tra diff và chỉ stage các file thuộc phạm vi công việc.
- Không tự đưa file của người khác hoặc thay đổi chưa liên quan vào commit.
- Không giả mạo commit author hoặc thay đổi lịch sử đóng góp.
- Không sử dụng `git push --force` trên nhánh dùng chung.
- Không tự rebase, reset, cherry-pick, xóa branch hoặc rewrite history khi có nguy cơ mất công việc.
- Không tự thay đổi branch protection, ruleset hoặc bypass quyền GitHub.
- Không tự merge PR của thành viên khi owner chưa nghiệm thu.
- Không tự đồng bộ `develop` sang `main` chỉ vì hai nhánh khác nhau.
- Sau khi hoàn thành feature, dừng tại bước đã được cho phép và báo rõ trạng thái commit, push, PR và merge.
- Không khẳng định đã review, merge hoặc deploy nếu chưa thực hiện và chưa có bằng chứng.

## 6. Kiểm thử và xác minh

- Mọi thay đổi phải có cách xác minh phù hợp với mức độ rủi ro và phạm vi ảnh hưởng.
- Với bug, cố gắng tái hiện lỗi trước khi sửa và thêm regression test tập trung khi cần thiết.
- Với tính năng mới, kiểm tra các luồng chính, trường hợp biên, validation, phân quyền và tính nhất quán dữ liệu.
- Với refactor, xác minh hành vi hiện tại không bị thay đổi ngoài phạm vi dự kiến.
- Ưu tiên targeted tests trong quá trình phát triển.
- Chạy regression suite phù hợp khi hoàn thành hoặc khi thay đổi ảnh hưởng nhiều module.
- Không chạy lại toàn bộ test liên tục nếu không có thay đổi đáng kể.
- Với thay đổi nhỏ, ít rủi ro, có thể xác minh trực tiếp thay vì tạo test hình thức.
- Với frontend, sử dụng lệnh lint, build và test thực tế của repository.
- Với backend, sử dụng môi trường và test runner thực tế của repository.
- Trước khi chạy test, xác nhận test environment không trỏ đến database thật hoặc dữ liệu người dùng.
- Không chạy test có nguy cơ phá hủy hoặc làm thay đổi dữ liệu ngoài phạm vi kiểm thử.
- Không xóa, skip, sửa yếu assertion hoặc thay đổi test chỉ để tạo kết quả PASS.
- Không dùng mock data để chứng minh integration với database thật.
- Phân biệt unit test, integration test, runtime verification, end-to-end test và manual UAT.
- Frontend build PASS không đồng nghĩa giao diện đã được kiểm thử trên trình duyệt.
- SQLite test PASS không đồng nghĩa migration hoặc runtime MySQL/PostgreSQL đã PASS.
- API trả HTTP thành công không tự động chứng minh toàn bộ business workflow đúng.
- Chỉ công bố PASS khi kiểm tra đã thực sự chạy thành công.
- Nếu không thể kiểm thử vì thiếu môi trường, dependency, credential hoặc quyền, ghi rõ `NOT TESTED` và lý do.
- Không tự tạo bằng chứng kiểm thử hoặc khẳng định đã nghiệm thu thay người dùng.

## 7. Hoàn tất công việc

- Rà soát toàn bộ diff trước khi bàn giao.
- Xác nhận các file thay đổi đều thuộc phạm vi yêu cầu.
- Kiểm tra hành vi, bảo mật, phân quyền, dữ liệu, tính tương thích và các nơi gọi liên quan.
- Loại bỏ mã dư thừa do chính thay đổi tạo ra.
- Kiểm tra trùng lặp, naming convention, import và cấu hình.
- Không để lại debug code, temporary script, secret hoặc file sinh tự động không cần thiết.
- Với frontend, kiểm tra giao diện, loading, empty state, error state, responsive và thao tác người dùng khi phù hợp.
- Với backend, kiểm tra validation, authorization, transaction, error handling và API contract.
- Với database, kiểm tra migration, ràng buộc, dữ liệu hiện có và khả năng khởi động lại an toàn.
- Xác nhận acceptance criteria bằng test hoặc bằng chứng kiểm tra cụ thể.
- Không coi việc đã viết code là đồng nghĩa với hoàn thành hoặc nghiệm thu.
- Nếu phát hiện lỗi trực tiếp do thay đổi của mình gây ra, sửa trong phạm vi nhiệm vụ và kiểm chứng lại.
- Không mở rộng sang user story hoặc chức năng tiếp theo khi chưa được yêu cầu.
- Không tự merge hoặc deploy chỉ vì toàn bộ test đã PASS.
- Báo cáo ngắn gọn những gì đã thay đổi, lý do, các lệnh kiểm tra và kết quả thực tế.
- Nêu rõ những phần chưa kiểm chứng, rủi ro còn lại và blocker nếu có.
- Nếu có thao tác Git, báo chính xác branch, commit SHA, push, PR và merge status.
- Chỉ tuyên bố hoàn thành khi kết quả đáp ứng phạm vi và có bằng chứng phù hợp.

---

**Nguyên tắc cốt lõi:** Đọc hiểu trước khi sửa. Bảo vệ công việc và dữ liệu hiện có. Ưu tiên giải pháp đơn giản. Không vượt phạm vi. Bảo mật từ backend. Làm việc trên feature branch. Kiểm thử đúng trọng tâm. Báo cáo trung thực. Không tự merge hoặc động vào `main` khi dự án chưa hoàn tất.
