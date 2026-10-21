from telegram import Update
from telegram.ext import ContextTypes


def is_authorized(update: Update, settings) -> bool:
    user = update.effective_user
    return user is not None and user.id in settings.allowed_user_ids


async def reject_unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = context.application.bot_data["settings"]
    if is_authorized(update, settings):
        return False
    if update.effective_message:
        await update.effective_message.reply_text(
            "⛔ Bạn chưa được cấp quyền sử dụng bot. Hãy cấu hình Telegram user ID trong .env."
        )
    return True
