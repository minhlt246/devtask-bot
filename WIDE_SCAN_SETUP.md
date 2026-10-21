# Quét nhiều thư mục người dùng trên macOS

Mặc định tìm trong Desktop, Documents, Downloads và các thư mục thông thường bên trong `/Users/<user>` (bao gồm thư mục dự án riêng và thư mục con), tối đa 12 cấp sâu và 1000 dự án.

## Cập nhật
1. Dừng bot bằng Ctrl+C.
2. Sao lưu thư mục hiện tại.
3. Giải nén ZIP này.
4. Thay toàn bộ thư mục `app` trong `/Users/min/Desktop/devtask-bot/app` bằng thư mục `app` mới.
5. Giữ nguyên `.env` và `data`.
6. Nếu `.env` có `PROJECT_SCAN_ROOT=/Users/min`, xoá dòng đó hoặc comment bằng `#` để dùng chế độ tự quét nhiều thư mục.
7. Chạy lại `python -m app.main`, gửi `/scanprojects`, rồi `/projects`.

## Quyền macOS
macOS có thể chặn Terminal/Cursor truy cập Desktop, Documents hoặc Downloads. Mở System Settings → Privacy & Security → Files & Folders để cấp quyền cho ứng dụng chạy bot. Chỉ bật Full Disk Access nếu thật sự cần và bạn chấp nhận phạm vi quyền rộng hơn.

## Giới hạn
Không quét toàn bộ ổ đĩa hệ thống. Bỏ qua Library, thư mục hệ thống, cache, dependency và build output; không đi theo symlink. Chỉ phát hiện dự án và lưu task, chưa chạy coding agent.
