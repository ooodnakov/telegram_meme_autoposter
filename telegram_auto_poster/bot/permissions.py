"""Utilities for checking administrative permissions for bot commands."""

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from telegram_auto_poster.config import load_config


def _get_bot_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """Return the best available mutable ``bot_data`` mapping from ``context``."""
    if hasattr(context, "bot_data"):
        return context.bot_data
    if hasattr(context, "application") and hasattr(context.application, "bot_data"):
        return context.application.bot_data
    return None


def _resolve_admin_ids(context: ContextTypes.DEFAULT_TYPE) -> list[int]:
    """Load and cache the configured administrator IDs."""
    bot_data = _get_bot_data(context)
    admin_ids = bot_data.get("admin_ids") if bot_data is not None else None
    if admin_ids is not None:
        return admin_ids

    config = bot_data.get("config") if bot_data is not None else None
    if config is None:
        config = load_config()
        if bot_data is not None:
            bot_data["config"] = config

    admin_ids = list(config.bot.admin_ids or [])
    if not admin_ids and getattr(config.bot, "bot_chat_id", None):
        admin_ids = [config.bot.bot_chat_id]

    if bot_data is not None:
        bot_data["admin_ids"] = admin_ids
    return admin_ids


async def check_admin_rights(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Check whether the user has administrative privileges for commands.

    Args:
        update: Incoming update from Telegram.
        context: Handler context providing bot data.

    Returns:
        ``True`` if the user is an administrator, ``False`` otherwise.

    """
    try:
        user_id = update.effective_user.id
        admin_ids = _resolve_admin_ids(context)

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


async def check_callback_admin_rights(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Check whether the callback query sender has administrative privileges."""
    query = update.callback_query
    try:
        user_id = update.effective_user.id
        admin_ids = _resolve_admin_ids(context)

        if user_id in admin_ids:
            logger.debug(f"User {user_id} has admin rights for callback actions")
            return True

        logger.warning(
            f"User {user_id} attempted to use admin callback without permission"
        )
        await query.answer("У вас нет прав на это действие.", show_alert=True)
        return False
    except Exception as e:
        logger.error(f"Error checking callback admin rights: {e}")
        if query is not None:
            await query.answer(
                "Произошла ошибка при проверке прав доступа.", show_alert=True
            )
        return False
