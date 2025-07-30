import asyncio
from pathlib import Path

from .bot.bot import TelegramMemeBot
from .client.client import TelegramMemeClient
from .utils.logger_setup import setup_logger
from .utils.stats import stats

# Setup logger
logger = setup_logger()

# Ensure required directories exist
Path("photos").mkdir(exist_ok=True)
Path("videos").mkdir(exist_ok=True)


async def main():
    """Main entry point for the Telegram Meme Autoposter."""
    bot = None
    client = None

    # Define signal handlers to gracefully shutdown
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal, stopping...")
        stop_event.set()

    # # Register signal handlers
    # for sig in (signal.SIGINT, signal.SIGTERM):
    #     asyncio.get_event_loop().add_signal_handler(sig, signal_handler)

    try:
        # Initialize bot
        bot = TelegramMemeBot()
        await bot.setup()

        # Initialize client with bot's application
        client = TelegramMemeClient(bot.application)
        asyncio.create_task(client.start())

        # Start the bot polling in our existing event loop
        asyncio.create_task(bot.start_polling())

        # Keep the program running until stop event is set
        logger.info("Bot started, press CTRL+C to stop")
        await stop_event.wait()

    except Exception as e:
        import sys
        import traceback

        # Print full traceback
        traceback.print_exc()

        # Or get traceback as string for logging
        error_details = traceback.format_exc()
        print(f"Error occurred: {error_details}")
        exc_type, exc_value, exc_traceback = sys.exc_info()
        print(f"Exception type: {exc_type}")
        print(f"Exception value: {exc_value}")
        print(f"Traceback: {exc_traceback}")
        logger.error(f"An error occurred: {e}")
    finally:
        # Cleanup - make sure we have proper objects before trying to stop them
        logger.info("Shutting down...")
        if client:
            await client.stop()
        if bot:
            await bot.stop()
        stats.force_save()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
