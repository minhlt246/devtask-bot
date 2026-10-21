from __future__ import annotations
from pathlib import Path

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.security.auth import reject_unauthorized
from app.services.platform_support import open_path_in_editor
from app.services.project_discovery import default_scan_roots, discover_projects
from app.services.project_classifier import classify_project, load_rules
from app.services.task_status import format_task_status, normalize_status, parse_task_id
from app.storage.database import TaskDatabase

WAITING_FOR_PROJECT, WAITING_FOR_DESCRIPTION = range(2)


PROJECTS_PER_PAGE = 24  # 3 columns x 8 rows


def _project_label(project: dict[str, str], prefix: str = "") -> str:
    info = classify_project(project)
    name = project.get("name", "Unnamed")[:34]
    return f"{prefix}{info['emoji']} {name}"[:60]


def _project_list_text(title: str, projects: list[dict[str, str]], page: int = 0) -> str:
    lines = [title, ""]
    lines.extend(f"{i}. {p.get('name', 'Unnamed')} — {p.get('path', '')}"
                 for i, p in enumerate(projects, 1))
    lines.extend(["", "Gửi số thứ tự để chọn dự án."])
    return "\n".join(lines)


def _database(context: ContextTypes.DEFAULT_TYPE) -> TaskDatabase:
    return context.application.bot_data["database"]


def _remember_project(context: ContextTypes.DEFAULT_TYPE, user_id: int, project: dict[str, str]) -> None:
    _database(context).save_selected_project(
        user_id, project["key"], project["name"], project["path"]
    )


def _current_project(context: ContextTypes.DEFAULT_TYPE, user_id: int, projects: list[dict[str, str]]) -> dict[str, str] | None:
    saved = _database(context).get_selected_project(user_id)
    if not saved:
        return None
    # Prefer freshly discovered metadata, and do not silently use a deleted/moved path.
    project = next((p for p in projects if p.get("key") == saved["project_key"]), None)
    if project is None:
        project = next((p for p in projects if p.get("path") == saved["project_path"]), None)
    if project is None or not Path(project["path"]).is_dir():
        return None
    return project


def _discover(context: ContextTypes.DEFAULT_TYPE) -> list[dict[str, str]]:
    settings = context.application.bot_data["settings"]
    if str(settings.project_scan_root) == "__AUTO_DISCOVERY__":
        return discover_projects(default_scan_roots())
    return discover_projects([settings.project_scan_root])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_unauthorized(update, context):
        return
    context.application.bot_data["agent_enabled"] = True
    await update.effective_message.reply_text(
        "🟢 Bot đã bật. Antigravity worker được phép nhận task đang chờ.\n\n"
        "Chào bạn! DevTask Bot — tự phát hiện dự án.\n\n"
        "/scanprojects — quét lại thư mục người dùng\n"
        "/open — mở dự án trong Cursor/VS Code\n"
        "/projects — xem dự án đã phát hiện\n"
        "/task — chọn dự án rồi nhập việc (prompt 2 + audit prompt 3)\n"
        "/readproject — đọc hiểu/lập bản đồ dự án theo prompt 1, không sửa file\n"
        "/task <project_key> <mô tả> — tạo task nhanh\n"
        "/tasks — danh sách task\n"
        "/status <task_id|TASK-0014> — xem trạng thái lifecycle\n"
        "/cancel <task_id> — hủy task còn chờ\n"
        "/cancelinput — hủy quy trình nhập task\n\n"
        "Antigravity worker tự xử lý task trong hàng đợi, chạy test phù hợp và gửi báo cáo."
    )


async def off_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause new agent work while keeping Telegram commands available."""
    if await reject_unauthorized(update, context):
        return
    context.application.bot_data["agent_enabled"] = False
    await update.effective_message.reply_text(
        "⏸️ Đã tắt xử lý task mới. Task đang chạy sẽ tiếp tục đến khi hoàn tất; "
        "task đang chờ sẽ được giữ nguyên. Gõ /start để bật lại."
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain Telegram's history limitation without deleting audit/task records."""
    if await reject_unauthorized(update, context):
        return
    message = update.effective_message
    # Remove the /clear command itself where Telegram permits it.
    try:
        await message.delete()
    except Exception:
        pass
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "🧹 /clear không xóa lịch sử task hoặc nhật ký kiểm toán. "
            "Telegram Bot API không cho bot tự lấy toàn bộ lịch sử chat để xóa hàng loạt.\n\n"
            "Để dọn màn hình: mở menu ⋮ của cuộc trò chuyện Telegram và chọn Clear History / Xóa lịch sử."
        ),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_unauthorized(update, context):
        return
    await update.effective_message.reply_text(
        "Cách dùng:\n"
        "/scanprojects — quét lại thư mục quét\n"
        "/projects — xem danh sách dự án tìm được\n"
        "/task — chọn dự án bằng nút bấm, rồi gửi mô tả (prompt 2 + audit prompt 3)\n"
        "/readproject — chọn dự án để đọc hiểu theo prompt 1 (chỉ đọc)\n"
        "/task p0001 Sửa lỗi đăng nhập — tạo task nhanh theo key\n"
        "/tasks — xem lịch sử\n"
        "/status 1 hoặc /status TASK-0001 — xem lifecycle task\n"
        "/cancel 1 — hủy task đang QUEUED\n\n"
        "Bot mặc định quét Desktop, Documents, Downloads và các thư mục thông thường trong home. Có thể đặt PROJECT_SCAN_ROOT để giới hạn vào một thư mục cụ thể."
    )


async def scan_projects_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if await reject_unauthorized(update, context):
        return
    message = update.effective_message
    settings = context.application.bot_data["settings"]
    await message.reply_text(
        "🔎 Đang quét Desktop, Documents, Downloads và các thư mục thông thường trong home.\n"
        "Có thể mất một lúc nếu có nhiều file."
    )
    projects = _discover(context)
    await message.reply_text(
        f"✅ Quét xong. Phát hiện {len(projects)} dự án.\n"
        "Dùng /projects để xem danh sách hoặc /task để giao việc."
    )


async def projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_unauthorized(update, context):
        return
    projects = _discover(context)
    if not projects:
        settings = context.application.bot_data["settings"]
        await update.effective_message.reply_text(
            "Chưa tìm thấy dự án code trong:\n"
            f"{settings.project_scan_root}\n\n"
            "Hãy kiểm tra quyền truy cập thư mục hoặc đặt PROJECT_SCAN_ROOT trong .env."
        )
        return

    # Telegram message limit is 4096 chars; send batches.
    lines = [f"📁 TÌM THẤY {len(projects)} DỰ ÁN (tối đa 500):"]
    for project in projects:
        lines.append(
            f"\n• {project['name']}\n"
            f"  Key: {project['key']}\n"
            f"  Đường dẫn: {project['path']}"
        )
    output = "\n".join(lines)
    while output:
        chunk = output[:3800]
        # Prefer ending at a newline when possible.
        split_at = chunk.rfind("\n")
        if split_at > 500:
            chunk = chunk[:split_at]
        await update.effective_message.reply_text(chunk)
        output = output[len(chunk):].lstrip("\n")


def _project_reply_keyboard(projects, context):
    rows = []
    labels = {}
    row = []
    for index, project in enumerate(projects, 1):
        label = f"{index}. {project.get('name', 'Unnamed')}"[:60]
        labels[label] = index
        row.append(KeyboardButton(label))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    context.user_data["project_button_labels"] = labels
    rows.append([KeyboardButton("/refresh"), KeyboardButton("/cancel")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)


async def projects_select_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await reject_unauthorized(update, context):
        return ConversationHandler.END
    projects = _discover(context)
    if not projects:
        await update.effective_message.reply_text("Không tìm thấy dự án. Hãy chạy /scanprojects.")
        return ConversationHandler.END
    context.user_data["project_selection_list"] = projects
    await update.effective_message.reply_text(
        f"📂 CHỌN DỰ ÁN — {len(projects)} dự án. Bấm một nút bên dưới:",
        reply_markup=_project_reply_keyboard(projects, context)
    )
    return WAITING_FOR_PROJECT


async def open_project_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_unauthorized(update, context):
        return
    projects = _discover(context)
    if not projects:
        await update.effective_message.reply_text("Chưa tìm thấy dự án. Hãy chạy /scanprojects.")
        return
    if not context.args:
        user = update.effective_user
        project = (
            _current_project(context, user.id, projects)
            if user is not None
            else None
        )
        if project is None:
            await update.effective_message.reply_text(
                _project_list_text("🖥️ MỞ DỰ ÁN TRONG IDE", projects)
                + "\nChưa có dự án được chọn. Hãy chọn dự án bằng /projects "
                  "hoặc dùng /open SỐ."
            )
            return
    else:
        try:
            index = int(context.args[0]) - 1
        except ValueError:
            index = -1
        if index < 0 or index >= len(projects):
            await update.effective_message.reply_text(
                "Số dự án không hợp lệ. Dùng /open để xem danh sách."
            )
            return
        project = projects[index]
    path = Path(project["path"]).expanduser().resolve()
    try:
        path.relative_to(Path.home().resolve())
    except ValueError:
        await update.effective_message.reply_text(
            "Đường dẫn nằm ngoài thư mục người dùng; từ chối mở."
        )
        return
    if not path.is_dir():
        await update.effective_message.reply_text("Thư mục dự án không còn tồn tại.")
        return
    settings = context.application.bot_data["settings"]
    ok, message = open_path_in_editor(path, settings.code_editor)
    await update.effective_message.reply_text(message if ok else f"Không mở được IDE: {message}")



async def task_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await reject_unauthorized(update, context):
        return ConversationHandler.END

    command_text = (update.effective_message.text or "").split(maxsplit=1)[0].split("@", 1)[0].lower()
    forced_mode = "ANALYSIS" if command_text == "/readproject" else None
    context.user_data["requested_task_mode"] = forced_mode
    projects = _discover(context)
    if len(context.args) >= 2:
        project_key = context.args[0].strip()
        request_text = " ".join(context.args[1:]).strip()
        return await _create_task_from_values(
            update, context, projects, project_key, request_text, task_mode=forced_mode
        )

    if not projects:
        await update.effective_message.reply_text(
            "Chưa tìm thấy dự án. Hãy chạy /scanprojects và kiểm tra PROJECT_SCAN_ROOT."
        )
        return ConversationHandler.END

    # Reuse the last selected project by default; user can explicitly change it via the picker.
    current = _current_project(context, update.effective_user.id, projects)
    if current:
        context.user_data["selected_project"] = current
        await update.effective_message.reply_text(
            f"📌 Tiếp tục với dự án gần nhất: {current['name']}\n{current['path']}\n\n"
            + ("Gửi yêu cầu đọc/phân tích dự án chỉ đọc. Gõ /cancelinput để hủy."
               if forced_mode == "ANALYSIS" else
               "Gửi yêu cầu task tiếp theo; bot sẽ dùng dự án này và chạy audit sau task. "
               "Muốn đổi dự án thì dùng /projects để chọn lại. Gõ /cancelinput để hủy.")
        )
        return WAITING_FOR_DESCRIPTION

    context.user_data["project_selection_list"] = projects
    await update.effective_message.reply_text(
        f"📂 CHỌN DỰ ÁN — {len(projects)} dự án. Bấm một nút bên dưới:",
        reply_markup=_project_reply_keyboard(projects, context)
    )
    return WAITING_FOR_PROJECT


async def refresh_project_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await projects_select_start(update, context)


async def receive_project_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await reject_unauthorized(update, context):
        return ConversationHandler.END

    value = (update.effective_message.text or "").strip()
    labels = context.user_data.get("project_button_labels", {})
    if value in labels:
        value = str(labels[value])


    if value.lower() in {"/cancel", "cancel", "huỷ", "hủy"}:
        context.user_data.pop("project_selection_list", None)
        context.user_data.pop("selected_project", None)
        await update.effective_message.reply_text("Đã huỷ thao tác chọn dự án.")
        return ConversationHandler.END

    if value.lower() in {"/refresh", "refresh", "làm mới"}:
        return await refresh_project_list(update, context)

    projects = context.user_data.get("project_selection_list") or _discover(context)
    try:
        index = int(value) - 1
    except ValueError:
        await update.effective_message.reply_text(
            "Hãy gửi số thứ tự dự án, /refresh để quét lại hoặc /cancel để huỷ."
        )
        return WAITING_FOR_PROJECT

    if index < 0 or index >= len(projects):
        await update.effective_message.reply_text(
            f"Số không hợp lệ. Hãy chọn từ 1 đến {len(projects)}."
        )
        return WAITING_FOR_PROJECT

    project = projects[index]
    context.user_data["selected_project"] = project
    context.user_data.pop("project_selection_list", None)
    _remember_project(context, update.effective_user.id, project)

    await update.effective_message.reply_text(
        f"Đã chọn dự án: {project['name']}\n{project['path']}\n\n"
        "Gửi mô tả công việc trong một tin nhắn. Gửi /cancel để huỷ."
    )
    return WAITING_FOR_DESCRIPTION



async def receive_task_description(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await reject_unauthorized(update, context):
        return ConversationHandler.END
    request_text = (update.effective_message.text or "").strip()
    if not request_text:
        await update.effective_message.reply_text("Mô tả không được để trống. Hãy gửi lại.")
        return WAITING_FOR_DESCRIPTION
    if len(request_text) > 3000:
        await update.effective_message.reply_text("Mô tả tối đa 3000 ký tự.")
        return WAITING_FOR_DESCRIPTION

    project = context.user_data.pop("selected_project", None)
    task_mode = context.user_data.pop("requested_task_mode", None)
    if not project:
        await update.effective_message.reply_text("Phiên chọn dự án đã hết. Hãy chạy /task lại.")
        return ConversationHandler.END
    return await _create_task_from_values(
        update, context, _discover(context), project["key"], request_text,
        selected_project=project, task_mode=task_mode
    )


async def cancel_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await reject_unauthorized(update, context):
        return ConversationHandler.END
    context.user_data.pop("selected_project", None)
    context.user_data.pop("requested_task_mode", None)
    await update.effective_message.reply_text("Đã hủy quy trình tạo task.")
    return ConversationHandler.END


def _infer_task_mode(request_text: str) -> str:
    """Default normal tasks to execution; analysis must be explicitly requested."""
    return "EXECUTE"


async def _create_task_from_values(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    projects: list[dict[str, str]],
    project_key: str,
    request_text: str,
    selected_project: dict[str, str] | None = None,
    task_mode: str | None = None,
) -> int:
    message = update.effective_message
    user = update.effective_user
    if not request_text:
        await message.reply_text("Mô tả task không được để trống.")
        return ConversationHandler.END
    if len(request_text) > 3000:
        await message.reply_text("Mô tả task tối đa 3000 ký tự.")
        return ConversationHandler.END

    project = selected_project or next(
        (p for p in projects if p["key"] == project_key), None
    )
    if not project:
        await message.reply_text(
            f"Không tìm thấy project key '{project_key}'. Hãy chạy /projects để xem key hiện tại."
        )
        return ConversationHandler.END

    # Explicit project key or selected project becomes the user's persistent current project.
    _remember_project(context, user.id, project)
    resolved_mode = task_mode or _infer_task_mode(request_text)
    task_id = _database(context).create_task(
        telegram_user_id=user.id,
        project_key=project["key"],
        request_text=(f"[Project: {project['name']} | Path: {project['path']}]\n"
                      f"[Mode: {resolved_mode}]\n{request_text}"),
    )
    mode_label = "ĐỌC HIỂU DỰ ÁN (CHỈ ĐỌC)" if resolved_mode == "ANALYSIS" else "TRIỂN KHAI + AUDIT SAU TASK"
    status_message = await message.reply_text(
        f"🟡 TASK-{task_id:04d} — QUEUED (ĐANG CHỜ)\n"
        f"Dự án: {project['name']}\n"
        f"Chế độ: {mode_label}\n"
        f"Đường dẫn: {project['path']}\n\n"
        + ("Bot sẽ đọc hiểu codebase theo prompt 1, không sửa file.\n"
           if resolved_mode == "ANALYSIS" else
           "Bot sẽ triển khai theo prompt 2, sau đó audit chỉ-đọc theo prompt 3.\n")
        + "\nTin nhắn này sẽ tự cập nhật tiến độ và kết quả cuối cùng."
    )
    _database(context).set_status_message(
        task_id, status_message.chat_id, status_message.message_id
    )
    return ConversationHandler.END


async def continue_task_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Treat a plain-text follow-up as a new task in the last selected project."""
    if await reject_unauthorized(update, context):
        return
    message = update.effective_message
    user = update.effective_user
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    projects = _discover(context)
    project = _current_project(context, user.id, projects)
    if project is None:
        await message.reply_text(
            "Chưa có dự án hiện tại được lưu hoặc dự án cũ không còn tồn tại. "
            "Dùng /task để chọn dự án trước."
        )
        return
    await _create_task_from_values(
        update, context, projects, project["key"], text,
        selected_project=project,
    )


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_unauthorized(update, context):
        return
    tasks = _database(context).list_tasks(limit=10)
    if not tasks:
        await update.effective_message.reply_text("Chưa có task nào.")
        return
    lines = ["📋 10 task gần đây:"]
    for task in tasks:
        short_request = task["request_text"]
        if len(short_request) > 70:
            short_request = short_request[:67] + "..."
        lines.append(
            f"\nTASK-{task['id']:04d} · {normalize_status(task['status'])}\n"
            f"Dự án: {task['project_key']}\n{short_request}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def task_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hiển thị lifecycle thật từ SQLite (/status 14 hoặc /status TASK-0014)."""
    if await reject_unauthorized(update, context):
        return
    if len(context.args) != 1:
        await update.effective_message.reply_text(
            "Cách dùng: /status <task_id>\nVí dụ: /status 14 hoặc /status TASK-0014"
        )
        return
    task_id = parse_task_id(context.args[0])
    if task_id is None:
        await update.effective_message.reply_text(
            "Task id không hợp lệ. Dùng số (14) hoặc TASK-0014."
        )
        return
    db = _database(context)
    task = db.get_task(task_id)
    if not task:
        await update.effective_message.reply_text(f"Không tìm thấy task TASK-{task_id:04d}.")
        return

    try:
        events = db.list_task_events(task_id, limit=80)
    except Exception:
        events = []
    # Chuẩn hoá status legacy trên bản ghi hiển thị (không ghi đè DB).
    view = dict(task)
    view["status"] = normalize_status(task.get("status"))
    await update.effective_message.reply_text(format_task_status(view, events))


async def cancel_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_unauthorized(update, context):
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.effective_message.reply_text("Cách dùng: /cancel <task_id>")
        return
    result = _database(context).cancel_task(
        int(context.args[0]), update.effective_user.id
    )
    messages = {
        "CANCELLED": "Đã hủy task đang chờ.",
        "NOT_FOUND": "Không tìm thấy task.",
        "FORBIDDEN": "Bạn không có quyền hủy task này.",
        "NOT_QUEUED": "Chỉ có thể hủy task ở trạng thái QUEUED trong MVP hiện tại.",
    }
    await update.effective_message.reply_text(messages[result])


async def _safe_edit_message_text(query, text, **kwargs):
    try:
        return await query.edit_message_text(text, **kwargs)
    except BadRequest as exc:
        if "Message is not modified" in str(exc):
            return None
        raise


def build_task_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("task", task_start),
            CommandHandler("readproject", task_start),
            CommandHandler("projects", projects_select_start),
        ],
        states={
            WAITING_FOR_PROJECT: [
            CommandHandler("refresh", refresh_project_list),
            CommandHandler("cancel", receive_project_selection),
            CommandHandler("cancelinput", receive_project_selection),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_project_selection),
        ],
        WAITING_FOR_DESCRIPTION: [
                CommandHandler("projects", projects_select_start),
                CommandHandler("open", open_project_start),
                CommandHandler("cancelinput", cancel_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_description),
            ],
        },
        fallbacks=[CommandHandler("cancelinput", cancel_input)],
        allow_reentry=True,
    )



async def clear_history_command(update, context):
    if await reject_unauthorized(update, context):
        return

    keys = (
        "history", "conversation_history", "chat_history",
        "messages", "conversation", "agent_history", "chat_messages"
    )
    for key in keys:
        context.user_data.pop(key, None)

    await reply_text(
        update,
        "Đã xóa lịch sử hội thoại đang lưu trong phiên hiện tại."
    )
