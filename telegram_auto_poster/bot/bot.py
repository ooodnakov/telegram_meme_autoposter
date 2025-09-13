"""Telegram bot application setup and lifecycle helpers."""

import datetime

from loguru import logger
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

# Import callbacks from callbacks.py
from telegram_auto_poster.bot.callbacks import (
    batch_browser_callback,
    notok_callback,
    ok_callback,
    push_callback,
    schedule_browser_callback,
    schedule_callback,
    unschedule_callback,
)

# Import commands from commands.py
from telegram_auto_poster.bot.commands import (
    batch_command,
    daily_stats_callback,
    delete_batch_command,
    get_chat_id_command,
    help_command,
    notok_command,
    ok_command,
    post_scheduled_media_job,
    reset_stats_command,
    save_stats_command,
    sch_command,
    schedule_command,
    send_batch_command,
    send_luba_command,
    start_command,
    stats_command,
)

# Import media handlers from handlers.py
from telegram_auto_poster.bot.handlers import handle_media
from telegram_auto_poster.config import Config
from telegram_auto_poster.utils.timezone import now_utc
from telegram_auto_poster.utils.ui import (
    CALLBACK_NOTOK,
    CALLBACK_OK,
    CALLBACK_PUSH,
    CALLBACK_SCHEDULE,
)


class TelegramMemeBot:
    """High level wrapper around ``python-telegram-bot`` for meme posting.

    Attributes:
        bot_token (str): Authentication token for the bot account.
        bot_chat_id (int): Chat ID where administrative commands are accepted.
        application (Application | None): Underlying PTB application instance.
        config (Config): Loaded configuration object.

    """

    def __init__(self, config: Config) -> None:
        """Store configuration and prepare for later setup."""
        self.bot_token = config.bot.bot_token.get_secret_value()
        self.bot_chat_id = config.bot.bot_chat_id
        self.application: Application | None = None
        self.config = config
        logger.info(f"TelegramMemeBot initialized with chat_id: {self.bot_chat_id}")

    async def setup(self) -> "Application":
        """Initialize the bot application and register all handlers.

        Returns:
            Application: The initialized application instance.

        """
        logger.info("Setting up bot application...")
        self.application = ApplicationBuilder().token(self.bot_token).build()
        application = self.application
        if application is None:
            raise RuntimeError("Failed to initialize bot application")

        # Store important information in bot_data
        application.bot_data["chat_id"] = self.bot_chat_id
        application.bot_data["target_channel_ids"] = (
            self.config.telegram.target_channels
        )
        application.bot_data["quiet_hours_start"] = (
            self.config.schedule.quiet_hours_start
        )
        application.bot_data["quiet_hours_end"] = self.config.schedule.quiet_hours_end
        application.bot_data["prompt_target_channel"] = (
            self.config.bot.prompt_target_channel
        )

        # Store admin IDs
        application.bot_data["admin_ids"] = self.config.bot.admin_ids
        logger.info(f"Configured admin IDs: {self.config.bot.admin_ids}")

        # Test the bot connection
        me = await application.bot.get_me()
        logger.info(f"Bot connected successfully as: {me.first_name} (@{me.username})")

        # Register command handlers
        logger.info("Registering command handlers...")
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("get", get_chat_id_command))
        application.add_handler(CommandHandler("ok", ok_command))
        application.add_handler(CommandHandler("notok", notok_command))
        application.add_handler(CommandHandler("sendall", send_batch_command))
        application.add_handler(CommandHandler("delete_batch", delete_batch_command))
        application.add_handler(CommandHandler("luba", send_luba_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("reset_stats", reset_stats_command))
        application.add_handler(CommandHandler("save_stats", save_stats_command))
        application.add_handler(CommandHandler("schedule", schedule_command))
        application.add_handler(CommandHandler("sch", sch_command))
        application.add_handler(CommandHandler("batch", batch_command))

        # Register callback handlers - fixed to use exact pattern matching with regex
        logger.info("Registering callback handlers...")
        application.add_handler(
            CallbackQueryHandler(ok_callback, pattern=rf"^{CALLBACK_OK}$")
        )
        application.add_handler(
            CallbackQueryHandler(push_callback, pattern=rf"^{CALLBACK_PUSH}(:.*)?$")
        )
        application.add_handler(
            CallbackQueryHandler(notok_callback, pattern=rf"^{CALLBACK_NOTOK}$")
        )
        application.add_handler(
            CallbackQueryHandler(schedule_callback, pattern=rf"^{CALLBACK_SCHEDULE}$")
        )
        application.add_handler(
            CallbackQueryHandler(unschedule_callback, pattern=r"^/unschedule:")
        )
        application.add_handler(
            CallbackQueryHandler(
                schedule_browser_callback,
                pattern=r"^/sch_(prev|next|unschedule|push):",
            )
        )
        application.add_handler(
            CallbackQueryHandler(
                batch_browser_callback,
                pattern=r"^/batch_(prev|next|remove|push):",
            )
        )

        # Register media handler
        logger.info("Registering media handler...")
        application.add_handler(
            MessageHandler(filters.PHOTO | filters.VIDEO, handle_media)
        )

        # Schedule daily statistics report at midnight
        application.job_queue.run_daily(
            daily_stats_callback,
            time=datetime.time(hour=0, minute=0),
            name="daily_stats_report",
            chat_id=self.bot_chat_id,
        )

        # Schedule the job to post scheduled media
        now = now_utc()
        next_hour = (now + datetime.timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0
        )
        application.job_queue.run_repeating(
            post_scheduled_media_job,
            interval=60 * 60,
            first=next_hour,
            name="post_scheduled_media",
        )

        # Just initialize the application
        logger.info("Initializing application...")
        await application.initialize()

        self.application = application
        return application

    async def start_polling(self) -> None:
        """Start receiving updates without running a separate event loop."""
        # Start the bot without using run_polling (which creates its own event loop)
        logger.info("Starting bot application...")
        application = self.application
        if application is None:
            raise RuntimeError("Application not initialized")
        await application.start()

        # Fix: Make sure updater exists (it may not in newer versions)
        if not hasattr(application, "updater") or application.updater is None:
            logger.error("Application has no updater! Cannot start polling.")
            return

        logger.info("Starting updater polling...")
        await application.updater.start_polling(
            poll_interval=0.5,
            timeout=10,
            bootstrap_retries=1,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
        )
        logger.info("Bot polling started successfully!")

    async def stop(self) -> None:
        """Gracefully stop the bot and shut down its resources."""
        logger.info("Stopping bot...")
        application = self.application
        if (
            application
            and hasattr(application, "updater")
            and application.updater
            and application.updater.running
        ):
            logger.info("Stopping updater...")
            await application.updater.stop()
        if application and application.running:
            logger.info("Stopping application...")
            await application.stop()
        if application:
            logger.info("Shutting down application...")
            await application.shutdown()
        logger.info("Bot stopped successfully")
