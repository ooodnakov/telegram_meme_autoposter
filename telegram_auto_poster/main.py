import asyncio
import signal
from pathlib import Path

from telegram_auto_poster.bot.bot import TelegramMemeBot
from telegram_auto_poster.client.client import TelegramMemeClient
from telegram_auto_poster.config import load_config
from telegram_auto_poster.utils.logger_setup import setup_logger
from telegram_auto_poster.utils.stats import stats

# Setup logger
logger = setup_logger()

# Ensure required directories exist
Path("photos").mkdir(exist_ok=True)
Path("videos").mkdir(exist_ok=True)


async def main():
    """Main entry point for the Telegram Meme Autoposter."""
    # init_stats()
    # init_storage()
    config = load_config()
    bot = None
    client = None

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal, stopping...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        bot = TelegramMemeBot(config)
        await bot.setup()
        client = TelegramMemeClient(bot.application, config)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(bot.start_polling())
            tg.create_task(client.start())
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
        logger.info("Shutting down...")
        if client:
            await client.stop()
        if bot:
            await bot.stop()
        await stats.force_save()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
