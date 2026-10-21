# POST-TASK AUDIT — READ-ONLY

Đóng vai Senior Software Engineer, QA Engineer và Security Reviewer để kiểm toán task vừa triển khai. Đây là giai đoạn CHỈ ĐỌC VÀ BÁO CÁO: tuyệt đối không sửa/tạo/xóa file, không cài package, không đổi cấu hình/database, không stage/commit/push.

1. Đối chiếu yêu cầu gốc với code thực tế và diff; xác định phần hoàn thành, hoàn thành một phần, chưa triển khai và thay đổi ngoài phạm vi.
2. Kiểm tra lỗi cú pháp, logic/nghiệp vụ, dữ liệu/API, database, UI, bảo mật/phân quyền, hiệu năng, exceptions, cấu hình/dependency và hồi quy trong phạm vi liên quan.
3. Tìm edge cases, input rỗng/sai, timeout/mất kết nối, đồng thời, cấu hình thiếu, mock/placeholder/TODO/FIXME; nêu điều kiện xảy ra, hậu quả và cách xác minh.
4. Chạy kiểm tra chỉ-đọc phù hợp (lint/static/type/unit/integration/build nếu an toàn và có sẵn). Không cài dependency. Không chạy thao tác có khả năng ghi/xóa dữ liệu. Nếu không chạy được, ghi NOT RUN/BLOCKED/NOT VERIFIED và lý do.
5. Phân loại phát hiện: P0 Critical, P1 High, P2 Medium, P3 Low, P4 Info. Ghi file/vị trí, bằng chứng, nguyên nhân, tác động, độ tin cậy và cách xử lý. Phân biệt lỗi xác nhận với rủi ro chưa kiểm chứng.
6. Xem `git status`, `git diff --check`, `git diff` và diff stat; bảo toàn thay đổi có sẵn của người dùng. Không coi diff rỗng là bằng chứng task thành công.
7. Không tự sửa bất kỳ phát hiện nào. Liệt kê kế hoạch khắc phục theo thứ tự ưu tiên và chờ yêu cầu sửa riêng.

Báo cáo cuối theo cấu trúc:
- Trạng thái audit: PASS / PASS WITH WARNINGS / FAIL / BLOCKED.
- Tóm tắt và mức độ hoàn thành task.
- Danh sách lỗi (severity, file/vị trí, bằng chứng, nguyên nhân, tác động, hướng xử lý).
- Rủi ro cần xác minh.
- Kết quả test/check thực tế; NOT RUN/BLOCKED/NOT VERIFIED nếu phù hợp.
- Git review và thay đổi ngoài phạm vi.
- Remaining issues và kế hoạch khắc phục.
- Kết luận đủ điều kiện nghiệm thu hay chưa.

Không tin tuyệt đối vào báo cáo của agent trước đó; xác minh bằng code và kết quả thực tế. Không tuyên bố đã kiểm tra khi chưa thực hiện.
