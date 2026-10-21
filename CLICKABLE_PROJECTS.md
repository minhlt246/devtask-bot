# Danh sách dự án bấm chọn trong Telegram

Bản này đổi `/projects` thành danh sách nút bấm. Bấm vào tên dự án sẽ chọn dự án đó và bot hỏi mô tả task; gửi mô tả là task được tạo trong SQLite.

- `/projects`: mở danh sách dự án có thể bấm.
- `/task`: cùng giao diện chọn dự án.
- Danh sách chia trang 25 dự án/trang.
- `PROJECT_SCAN_ROOT` nếu được đặt trong `.env` sẽ giới hạn quét vào đường dẫn đó; nếu không đặt, dùng cơ chế tự quét nhiều thư mục người dùng.

Lưu ý: đây là nút chọn dự án trong Telegram, không phải URL mở thư mục Mac từ điện thoại. Bản này vẫn chỉ tạo task trong SQLite; chưa gọi coding agent.
