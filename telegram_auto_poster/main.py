import asyncio
import signal
from pathlib import Path

from .utils.logger import setup_logger
from .bot.bot import TelegramMemeBot
from .client.client import TelegramMemeClient

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
        logger.error(f"An error occurred: {e}")
    finally:
        # Cleanup - make sure we have proper objects before trying to stop them
        logger.info("Shutting down...")
        if client:
            await client.stop()
        if bot:
            await bot.stop()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
