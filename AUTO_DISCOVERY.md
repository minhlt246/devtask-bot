# Tự phát hiện dự án trên máy Mac

Bản này quét thư mục home của tài khoản chạy bot (mặc định `Path.home()`, ví dụ `/Users/min`), tìm các thư mục có dấu hiệu dự án như `.git`, `package.json`, `pyproject.toml`, `pom.xml`, `Cargo.toml`, `go.mod`, `composer.json`, `*.sln`...

## Cấu hình

Trong `.env`, có thể đặt:
```dotenv
PROJECT_SCAN_ROOT=/Users/min
```
Mặc định nếu bỏ dòng này, bot quét thư mục home của tài khoản đang chạy bot.

## Telegram

- `/scanprojects` — quét lại thư mục gốc.
- `/projects` — quét và liệt kê các dự án được phát hiện.
- `/task` — quét rồi cho chọn dự án bằng nút bấm.
- `/task p0001 Mô tả task` — tạo task theo key hiện tại.

## Giới hạn

- Không quét toàn bộ ổ đĩa macOS một cách mù quáng. Mặc định chỉ quét thư mục home của user, bỏ qua Library, thư mục hệ thống, cache và dependency/build output.
- Tối đa 500 dự án và độ sâu 7 cấp thư mục trong bản MVP.
- Key `p0001`, `p0002` được sinh theo thứ tự quét, vì vậy có thể đổi sau khi quét lại; hãy dùng nút chọn dự án trong `/task` để tránh nhầm.
- Phát hiện dự án dựa trên dấu hiệu file, có thể bỏ sót dự án dùng cấu trúc khác.
- Bản này chỉ tìm và lưu task, chưa chạy coding agent hoặc sửa code.
- Quét được một thư mục không có nghĩa agent được phép sửa mọi file. Trước khi chạy agent cần xác thực path, workspace riêng và quyền hệ điều hành/container.
