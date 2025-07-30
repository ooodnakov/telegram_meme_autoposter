import os
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram import Update
from loguru import logger

from ..config import load_config

# Import commands from commands.py
from .commands import (
    start_command,
    help_command,
    get_chat_id_command,
    ok_command,
    notok_command,
    send_batch_command,
    delete_batch_command,
    send_luba_command,
    stats_command,
    reset_stats_command,
    save_stats_command,
    caption_command,
)

# Import callbacks from callbacks.py
from .callbacks import (
    ok_callback,
    push_callback,
    notok_callback,
    caption_select_callback,
)

# Import media handlers from handlers.py
from .handlers import handle_media


class TelegramMemeBot:
    def __init__(self):
        config = load_config()
        if "openai_api_key" in config:
            os.environ.setdefault("OPENAI_API_KEY", config["openai_api_key"])

        self.bot_token = config["bot_token"]
        self.bot_chat_id = config["bot_chat_id"]
        self.application = None
        logger.info(
            f"TelegramMemeBot initialized with chat_id: {self.bot_chat_id}"
        )

    async def setup(self):
        """Initialize the bot with all handlers and start updating."""
        logger.info("Setting up bot application...")
        self.application = ApplicationBuilder().token(self.bot_token).build()

        # Get config
        config = load_config()

        # Store important information in bot_data
        self.application.bot_data["chat_id"] = self.bot_chat_id
        self.application.bot_data["target_channel_id"] = config["target_channel"]

        # Store admin IDs
        if "admin_ids" in config:
            self.application.bot_data["admin_ids"] = config["admin_ids"]
            logger.info(f"Configured admin IDs: {config['admin_ids']}")
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
        self.application.add_handler(CommandHandler("caption", caption_command))

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
            CallbackQueryHandler(caption_select_callback, pattern=r"^cap_\d+:")
        )

        # Register media handler
        logger.info("Registering media handler...")
        self.application.add_handler(
            MessageHandler(filters.PHOTO | filters.VIDEO, handle_media)
        )

        # Just initialize the application
        logger.info("Initializing application...")
        await self.application.initialize()

        return self.application

    async def start_polling(self):
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
            read_timeout=20,
            write_timeout=20,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
        )
        logger.info("Bot polling started successfully!")

    async def stop(self):
        """Stop the bot."""
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
