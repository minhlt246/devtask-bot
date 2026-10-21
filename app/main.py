from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import load_settings
from app.handlers.task_commands import (
    open_project_start,
    build_task_conversation,
    clear_history_command,
    cancel_task,
    clear_command,
    off_command,
    help_command,
    list_tasks,
    scan_projects_command,
    start,
    task_status,
    continue_task_message,
)
from app.storage.database import TaskDatabase
from app.services.agent_worker import worker_loop


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Lỗi khi xử lý update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Đã xảy ra lỗi nội bộ. Hãy kiểm tra log trên máy chạy bot."
            )
        except Exception:
            logging.exception("Không thể gửi thông báo lỗi về Telegram")



async def post_init(application: Application) -> None:
    """Register Telegram's native slash-command menu."""
    commands = [
        BotCommand("start", "🟢 Bật bot / worker"),
        BotCommand("off", "⏸️ Tạm dừng xử lý task"),
        BotCommand("clear", "🧹 Hướng dẫn dọn lịch sử chat"),
        BotCommand("projects", "📁 Chọn dự án bằng nút 3 cột"),
        BotCommand("projectbuttons", "🔘 Chọn dự án bằng nút bấm"),
        BotCommand("open", "🖥️ Mở dự án trong IDE"),
        BotCommand("task", "📝 Task: triển khai + audit"),
        BotCommand("readproject", "🧭 Đọc hiểu dự án (chỉ đọc)"),
        BotCommand("tasks", "📋 Danh sách task"),
        BotCommand("status", "🔎 Xem trạng thái task"),
        BotCommand("cancel", "✖️ Hủy task đang chờ"),
        BotCommand("scanprojects", "🔄 Quét lại dự án"),
        BotCommand("help", "❓ Hướng dẫn sử dụng"),
    ]
    await application.bot.set_my_commands(commands)
    logging.info("Đã đăng ký Telegram command menu (%s lệnh)", len(commands))
    application.bot_data.setdefault("agent_enabled", True)
    application.bot_data["worker_task"] = asyncio.create_task(worker_loop(application))


async def post_shutdown(application: Application) -> None:
    """Hủy worker nền khi bot dừng (Ctrl+C / stop) — dùng chung macOS và Windows."""
    worker = application.bot_data.get("worker_task")
    if worker is None:
        return
    worker.cancel()
    with suppress(asyncio.CancelledError):
        await worker
    logging.info("Worker task đã dừng.")


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    database = TaskDatabase(settings.database_path)
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["database"] = database

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("off", off_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("clearhistory", clear_history_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("scanprojects", scan_projects_command))
    application.add_handler(CommandHandler("open", open_project_start))
    application.add_handler(build_task_conversation())
    # Plain-text follow-ups outside an active conversation continue in the saved project.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, continue_task_message))
    application.add_handler(CommandHandler("tasks", list_tasks))
    application.add_handler(CommandHandler("status", task_status))
    application.add_handler(CommandHandler("cancel", cancel_task))
    application.add_error_handler(error_handler)

    logging.info(
        "DevTask Bot khởi động; database=%s; project_scan_root=%s",
        settings.database_path,
        settings.project_scan_root,
    )
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
