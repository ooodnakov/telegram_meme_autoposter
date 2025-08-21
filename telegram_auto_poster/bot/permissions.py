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

        # First check if admin_ids in bot_data
        if hasattr(context, "bot_data") and "admin_ids" in context.bot_data:
            admin_ids = context.bot_data["admin_ids"]
            if user_id in admin_ids:
                logger.debug(f"User {user_id} has admin rights (from bot_data)")
                return True

        # If not found in bot_data, get admin IDs from config
        config = load_config()
        admin_ids = config.bot.admin_ids

        # Check if user is in admin list
        if user_id in admin_ids:
            logger.debug(f"User {user_id} has admin rights (from config)")
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
