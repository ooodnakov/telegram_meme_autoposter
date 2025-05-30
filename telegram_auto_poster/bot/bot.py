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
from .handlers import (
    start,
    get_chat_id,
    ok_command,
    notok_command,
    send_batch_command,
    delete_batch_command,
    send_luba_command,
    ok_callback,
    push_callback,
    notok_callback,
    handle_media,
)


class TelegramMemeBot:
    def __init__(self):
        config = load_config()
        self.bot_token = config["bot_token"]
        self.bot_chat_id = config["bot_chat_id"]
        self.application = None
        logger.info(f"TelegramMemeBot initialized with chat_id: {self.bot_chat_id}")

    async def setup(self):
        """Initialize the bot with all handlers and start updating."""
        logger.info("Setting up bot application...")
        self.application = ApplicationBuilder().token(self.bot_token).build()

        # Store bot_chat_id in application's bot_data
        self.application.bot_data["chat_id"] = self.bot_chat_id

        # Test the bot connection
        me = await self.application.bot.get_me()
        logger.info(f"Bot connected successfully as: {me.first_name} (@{me.username})")

        # Register command handlers
        logger.info("Registering command handlers...")
        self.application.add_handler(CommandHandler("start", start))
        self.application.add_handler(CommandHandler("get", get_chat_id))
        self.application.add_handler(CommandHandler("ok", ok_command))
        self.application.add_handler(CommandHandler("notok", notok_command))
        self.application.add_handler(CommandHandler("send_batch", send_batch_command))
        self.application.add_handler(
            CommandHandler("delete_batch", delete_batch_command)
        )
        self.application.add_handler(CommandHandler("luba", send_luba_command))

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
