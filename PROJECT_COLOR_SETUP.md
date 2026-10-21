# Danh sách dự án và quy tắc màu

Danh sách chọn dự án trong Telegram dùng inline keyboard 3 cột, 24 dự án/trang, có nút Trước/Sau, Làm mới và Hủy. `/task`, `/readproject`, `/projects` (luồng chọn task như bản hiện tại) và `/open` dùng cùng cách phân loại.

## Chỉnh màu và nhận diện

Sửa `config/project_colors.json`. Mỗi rule có:
- `id`: định danh duy nhất.
- `label`: tên công nghệ hiển thị trong chú giải.
- `emoji`: biểu tượng màu hiển thị cạnh tên dự án trong Telegram.
- `color`: mã HEX lưu để có thể dùng lại nếu sau này làm Telegram Web App.
- `markers`: tên file/thư mục tại thư mục gốc.
- `extensions`: phần mở rộng file được dò trong mẫu tối đa 2500 file.
- `name_contains`: chuỗi trong tên dự án để nhận diện.

Quy tắc mặc định:
- WordPress/PHP: xanh dương.
- Flutter/Dart: đỏ theo yêu cầu.
- TypeScript: xanh dương.
- JavaScript: vàng.
- Python: xanh dương.
- Java: cam.
- Go: xanh cyan.
- Rust: màu đồng.
- C#: tím.
- Ruby: đỏ.
- Không xác định: xám.

Đặt rule đặc thù phía trên rule chung. Ví dụ, TypeScript phải đứng trước JavaScript; WordPress/PHP và Flutter phải đứng trước các rule ngôn ngữ chung.

**Giới hạn Telegram:** Telegram Bot API không cho đặt màu nền tùy ý cho từng inline button. Bot dùng emoji màu để thể hiện màu trong danh sách. Trường `color` giữ HEX cho cấu hình và khả năng mở rộng sang Telegram Web App.
