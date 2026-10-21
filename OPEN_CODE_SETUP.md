# Mở dự án từ Telegram trong Cursor/VS Code

1. Trong `.env`, thêm `CODE_EDITOR=Cursor` (hoặc `CODE_EDITOR=Visual Studio Code`).
2. Dừng bot và thay thư mục `app` bằng bản trong ZIP này.
3. Giữ nguyên `.env` và `data`.
4. Khởi động lại bot.
5. Gửi `/open`, bấm tên dự án; bot sẽ yêu cầu macOS mở đúng thư mục trong IDE.

Giới hạn: lệnh mở IDE được thực thi trên chính máy Mac đang chạy bot. Nếu bot chạy trên server/cloud thì nó không thể mở cửa sổ IDE trên Mac từ xa bằng lệnh này. Không dùng shell command do người dùng Telegram nhập; chỉ mở đường dẫn dự án đã phát hiện trong thư mục home.
