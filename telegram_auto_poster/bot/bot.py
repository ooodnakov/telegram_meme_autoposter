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
    notok_callback,
    ok_callback,
    push_callback,
    schedule_browser_callback,
    schedule_callback,
    unschedule_callback,
)

# Import commands from commands.py
from telegram_auto_poster.bot.commands import (
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
    send_batch_command,
    send_luba_command,
    start_command,
    stats_command,
)

# Import media handlers from handlers.py
from telegram_auto_poster.bot.handlers import handle_media
from telegram_auto_poster.utils.timezone import now_utc


class TelegramMemeBot:
    """High level wrapper around ``python-telegram-bot`` for meme posting.

    Attributes:
        bot_token (str): Authentication token for the bot account.
        bot_chat_id (str): Chat ID where administrative commands are accepted.
        application (Application | None): Underlying PTB application instance.
        config (dict): Original configuration dictionary.
    """

    def __init__(self, config: dict) -> None:
        """Store configuration and prepare for later setup.

        Args:
            config: Parsed configuration mapping from :mod:`configparser`.
        """
        self.bot_token = config["bot_token"]
        self.bot_chat_id = config["bot_chat_id"]
        self.application = None
        self.config = config
        logger.info(f"TelegramMemeBot initialized with chat_id: {self.bot_chat_id}")

    async def setup(self) -> "Application":
        """Initialize the bot application and register all handlers.

        Returns:
            Application: The initialized application instance.
        """
        logger.info("Setting up bot application...")
        self.application = ApplicationBuilder().token(self.bot_token).build()

        # Store important information in bot_data
        self.application.bot_data["chat_id"] = self.bot_chat_id
        self.application.bot_data["target_channel_id"] = self.config["target_channel"]
        self.application.bot_data["quiet_hours_start"] = self.config.get(
            "quiet_hours_start", 22
        )
        self.application.bot_data["quiet_hours_end"] = self.config.get(
            "quiet_hours_end", 10
        )

        # Store admin IDs
        if "admin_ids" in self.config:
            self.application.bot_data["admin_ids"] = self.config["admin_ids"]
            logger.info(f"Configured admin IDs: {self.config['admin_ids']}")
        else:
            # For backward compatibility, use the bot_chat_id as admin
            self.application.bot_data["admin_ids"] = [int(self.bot_chat_id)]
            logger.info(
                f"No admin IDs configured, using chat_id as admin: {self.bot_chat_id}"
            )

        # Test the bot connection
        me = await self.application.bot.get_me()
        logger.info(f"Bot connected successfully as: {me.first_name} (@{me.username})")

        # Register command handlers
        logger.info("Registering command handlers...")
        self.application.add_handler(CommandHandler("start", start_command))
        self.application.add_handler(CommandHandler("help", help_command))
        self.application.add_handler(CommandHandler("get", get_chat_id_command))
        self.application.add_handler(CommandHandler("ok", ok_command))
        self.application.add_handler(CommandHandler("notok", notok_command))
        self.application.add_handler(CommandHandler("sendall", send_batch_command))
        self.application.add_handler(
            CommandHandler("delete_batch", delete_batch_command)
        )
        self.application.add_handler(CommandHandler("luba", send_luba_command))
        self.application.add_handler(CommandHandler("stats", stats_command))
        self.application.add_handler(CommandHandler("reset_stats", reset_stats_command))
        self.application.add_handler(CommandHandler("save_stats", save_stats_command))
        self.application.add_handler(CommandHandler("sch", sch_command))

        # Register callback handlers - fixed to use exact pattern matching with regex
        logger.info("Registering callback handlers...")
        self.application.add_handler(
            CallbackQueryHandler(ok_callback, pattern=r"^/ok$")
        )
        self.application.add_handler(
            CallbackQueryHandler(push_callback, pattern=r"^/push$")
        )
        self.application.add_handler(
            CallbackQueryHandler(notok_callback, pattern=r"^/notok$")
        )
        self.application.add_handler(
            CallbackQueryHandler(schedule_callback, pattern=r"^/schedule$")
        )
        self.application.add_handler(
            CallbackQueryHandler(unschedule_callback, pattern=r"^/unschedule:")
        )
        self.application.add_handler(
            CallbackQueryHandler(
                schedule_browser_callback,
                pattern=r"^/sch_(prev|next|unschedule|push):",
            )
        )

        # Register media handler
        logger.info("Registering media handler...")
        self.application.add_handler(
            MessageHandler(filters.PHOTO | filters.VIDEO, handle_media)
        )

        # Schedule daily statistics report at midnight
        self.application.job_queue.run_daily(
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
        self.application.job_queue.run_repeating(
            post_scheduled_media_job,
            interval=60 * 60,
            first=next_hour,
            name="post_scheduled_media",
        )

        # Just initialize the application
        logger.info("Initializing application...")
        await self.application.initialize()

        return self.application

    async def start_polling(self) -> None:
        """Start receiving updates without running a separate event loop."""
        # Start the bot without using run_polling (which creates its own event loop)
        logger.info("Starting bot application...")
        await self.application.start()

        # Fix: Make sure updater exists (it may not in newer versions)
        if not hasattr(self.application, "updater") or self.application.updater is None:
            logger.error("Application has no updater! Cannot start polling.")
            return

        logger.info("Starting updater polling...")
        await self.application.updater.start_polling(
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
        if (
            self.application
            and hasattr(self.application, "updater")
            and self.application.updater
            and self.application.updater.running
        ):
            logger.info("Stopping updater...")
            await self.application.updater.stop()
        if self.application and self.application.running:
            logger.info("Stopping application...")
            await self.application.stop()
        if self.application:
            logger.info("Shutting down application...")
            await self.application.shutdown()
        logger.info("Bot stopped successfully")
