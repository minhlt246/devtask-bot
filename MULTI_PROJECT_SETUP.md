# Cấu hình nhiều dự án

1. Mở `config/projects.json` trong Cursor.
2. Tạo một mục cho mỗi dự án. `key` chỉ dùng chữ thường, số, gạch dưới.
3. `path` là đường dẫn tuyệt đối đến thư mục dự án trên Mac.
4. `enabled: true` để cho phép chọn trong Telegram; `false` để ẩn/tắt dự án.
5. Lưu file.

Ví dụ:
```json
{
  "projects": {
    "shop": {
      "name": "Website bán hàng",
      "path": "/Users/min/Projects/shop",
      "enabled": true
    },
    "bot_api": {
      "name": "API Bot",
      "path": "/Users/min/Projects/bot-api",
      "enabled": true
    }
  }
}
```

Trong Telegram:
- `/projects` xem danh sách dự án.
- `/task` chọn một dự án bằng nút bấm, rồi gửi nội dung task.
- `/task shop Sửa giao diện trang chủ` tạo task nhanh.
- `/tasks` xem danh sách task.

**Chú ý:** Bản này chỉ chọn dự án và lưu task vào SQLite. Nó chưa chạy coding agent và chưa sửa code dự án.
