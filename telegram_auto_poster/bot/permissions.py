from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from telegram_auto_poster.config import load_config


async def check_admin_rights(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """
    Check if the user has admin rights to execute a command.

    Args:
        update: The update object from Telegram
        context: The context object from Telegram

    Returns:
        bool: True if the user has admin rights, False otherwise
    """
    try:
        # Get user ID
        user_id = update.effective_user.id

        admin_ids = None
        if hasattr(context, "bot_data"):
            admin_ids = context.bot_data.get("admin_ids")

        if admin_ids is None:
            config = None
            if hasattr(context, "bot_data"):
                config = context.bot_data.get("config")

            if config is None:
                config = load_config()
                if hasattr(context, "bot_data"):
                    context.bot_data["config"] = config

            admin_ids = list(config.bot.admin_ids or [])
            if not admin_ids and getattr(config.bot, "bot_chat_id", None):
                admin_ids = [config.bot.bot_chat_id]

            if hasattr(context, "bot_data"):
                context.bot_data["admin_ids"] = admin_ids

        if user_id in admin_ids:
            logger.debug(f"User {user_id} has admin rights")
            return True

        # User does not have admin rights
        logger.warning(
            f"User {user_id} attempted to use admin command without permission"
        )
        await update.message.reply_text("У вас нет прав на использование этой команды.")
        return False

    except Exception as e:
        logger.error(f"Error checking admin rights: {e}")
        await update.message.reply_text("Произошла ошибка при проверке прав доступа.")
        return False
