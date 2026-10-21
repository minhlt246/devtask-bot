TASK ƯU TIÊN CAO: TỰ NÂNG CẤP DEVTask BOT ĐỂ TỐI ƯU TỐC ĐỘ THỰC THI TASK VÀ TỰ BÁO CÁO TELEGRAM.

Hãy trực tiếp triển khai trên code của dự án `devtask-bot` đang được chọn. Không chỉ phân tích hoặc đưa ra kế hoạch. Phải kiểm tra code hiện tại, chỉnh sửa file, chạy test và báo cáo kết quả.

1. GIỮ NGUYÊN 3 PROMPT HIỆN CÓ
- Prompt 1: Phân tích và hiểu dự án.
- Prompt 2: Thực thi task.
- Prompt 3: Kiểm toán sau task.
- Tìm đúng file chứa prompt và toàn bộ vị trí gọi chúng. Không tự ý xóa, thay thế hoặc làm mất các yêu cầu nghiệp vụ hiện tại.

2. TỰ ĐỘNG ĐIỀU CHỈNH QUY TRÌNH THEO ĐỘ KHÓ
- Task đơn giản: dùng Prompt 2, chỉ đọc phần code liên quan, sửa đúng phạm vi yêu cầu, kiểm tra nhanh và chạy Prompt 3 ở mức kiểm toán phù hợp với rủi ro.
- Task trung bình: phân tích có mục tiêu khi cần, thực thi và kiểm toán sau task.
- Task phức tạp: thực hiện đầy đủ Prompt 1 → Prompt 2 → Prompt 3.
- Không bỏ hoàn toàn Prompt 3 ở bất kỳ task nào.
- Không bắt task đơn giản phải phân tích toàn bộ dự án hoặc lặp lại các bước không cần thiết.

3. TÌM VÀ XỬ LÝ NGUYÊN NHÂN CHẬM
Kiểm tra toàn bộ luồng: Telegram handler → database/queue → worker → chuẩn bị context → coding agent → kiểm thử → audit → gửi báo cáo Telegram.
Đo thời gian từng giai đoạn nếu có thể. Xác định nguyên nhân thực tế trước khi tối ưu. Giảm đọc file trùng lặp, phân tích lặp lại, gọi model không cần thiết và thời gian chờ queue. Không đánh đổi độ chính xác, bảo mật hoặc tính ổn định để lấy tốc độ.

4. BẮT BUỘC BÁO CÁO MỌI TASK
Sau mỗi task, dù thành công, thất bại, thực hiện một phần hay bị chặn, bot phải gửi báo cáo về đúng Telegram chat đã giao task.
Báo cáo gồm: trạng thái; nội dung đã thực hiện; file đã tạo/chỉnh sửa; test và kết quả thực tế; kết quả Prompt 3; thời gian thực thi; phần còn thiếu hoặc nguyên nhân thất bại.
Xử lý trường hợp gửi báo cáo lỗi và tránh gửi trùng báo cáo. Không được đánh dấu thành công nếu chưa thực hiện xong.

5. THEO DÕI THỜI GIAN
Bổ sung log nhẹ cho các mốc nhận task, đưa vào queue, bắt đầu worker, chuẩn bị context, bắt đầu/kết thúc agent, test, audit và gửi báo cáo.

6. QUY TẮC AN TOÀN
- Chỉ sửa những file cần thiết; không sửa lan man hoặc xóa dữ liệu dự án.
- Không ghi token, mật khẩu hoặc secret vào log.
- Không tạo worker chạy trùng gây xung đột.
- Không tự ý thay đổi kiến trúc hoặc dependency lớn nếu chưa có lý do rõ ràng.
- Bảo toàn các tính năng hiện có.
- Kiểm tra cách restart service hiện tại trước khi áp dụng thay đổi.

7. TRIỂN KHAI VÀ XÁC MINH
- Đọc cấu trúc dự án, README, cấu hình và các file prompt liên quan.
- Xác định đúng entry point, worker, executor và nơi gửi kết quả Telegram.
- Lập kế hoạch ngắn rồi trực tiếp chỉnh sửa code.
- Chạy compile, test và kiểm tra lỗi phù hợp với dự án.
- Kiểm tra cả nhánh thành công và lỗi của luồng báo cáo nếu có thể.
- Không giả lập kết quả test hoặc tuyên bố đã test nếu chưa chạy.
- Không tự động chạy lại task đang thực thi hoặc restart service một cách không an toàn.

8. KẾT THÚC
Gửi báo cáo cuối cùng qua Telegram cho người giao task, gồm nguyên nhân chậm tìm được, file đã sửa, cách tối ưu, test thực tế, thời gian trước/sau nếu đo được và vấn đề còn tồn tại.

BẮT ĐẦU TRIỂN KHAI NGAY. Không dừng ở bước phân tích hay đề xuất. Nếu thiếu quyền truy cập hoặc công cụ cần thiết, báo chính xác trở ngại qua Telegram.
