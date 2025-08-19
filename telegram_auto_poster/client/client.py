import asyncio
import os

from loguru import logger
from telethon import TelegramClient, events, types

from telegram_auto_poster.bot.handlers import process_photo, process_video
from telegram_auto_poster.utils import stats as stats_module

# Create a global client variable that can be accessed from other modules
client_instance = None


class TelegramMemeClient:
    """Utility class that listens to Telegram channels using Telethon.

    Attributes:
        client (TelegramClient): Underlying Telethon client instance.
        application (Application): Telegram bot application used for
            processing.
        target_channel (str): Channel username or ID where media is forwarded.
        bot_chat_id (str): Chat ID of the controlling bot.
        selected_chats (list[str]): Channels to monitor for new media.
    """

    def __init__(self, application, config: dict) -> None:
        """Initialize the Telethon client and store configuration values.

        Args:
            application: PTB ``Application`` instance used for coordination.
            config: Configuration dictionary with Telegram credentials and
                channel information.
        """
        self.client = TelegramClient(
            config["username"], config["api_id"], config["api_hash"]
        )
        self.application = application
        self.target_channel = config["target_channel"]
        self.bot_chat_id = config["bot_chat_id"]
        self.selected_chats = config["selected_chats"]
        self._task = None

        # Set the global client instance
        global client_instance
        client_instance = self.client

        # Also store the client in the application's bot_data
        if self.application and hasattr(self.application, "bot_data"):
            self.application.bot_data["telethon_client"] = self.client
            logger.info("TelegramClient instance stored in application.bot_data")
        else:
            logger.error(
                "Could not store client in application.bot_data - application not ready"
            )

        logger.info("TelegramClient instance created and globally available")

    async def _run(self):
        await self.client.run_until_disconnected()

    async def start(self) -> None:
        """Start the client and register event handlers."""
        await self.client.start()
        logger.info("TelegramClient started successfully")

        # Import process_photo and process_video here to avoid circular imports
        # Register event handler for new messages
        @self.client.on(events.NewMessage(chats=self.selected_chats))
        async def handle_new_message(event):
            file_path = None
            try:
                if isinstance(event.media, types.MessageMediaPhoto):
                    photo = event.media.photo
                    file_path = f"downloaded_image_{event.id}.jpg"
                    if stats_module.stats:
                        await stats_module.stats.record_received("photo")
                    await self.client.download_media(photo, file=file_path)
                    await process_photo(
                        "New post found with image",
                        file_path,
                        os.path.basename(file_path),
                        self.bot_chat_id,
                        self.application,
                    )
                elif isinstance(event.media, types.MessageMediaDocument):
                    if event.media.document:
                        logger.info(
                            f"Video with eventid {event.id} has started downloading!"
                        )
                        if stats_module.stats:
                            await stats_module.stats.record_received("video")
                        video = event.media.document
                        file_path = f"downloaded_video_{event.id}.mp4"
                        await self.client.download_media(video, file=file_path)
                        logger.info(
                            f"Video with eventid {event.id} has been downloaded!"
                        )
                        await process_video(
                            "New post found with video",
                            file_path,
                            os.path.basename(file_path),
                            self.bot_chat_id,
                            self.application,
                        )
            finally:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                else:
                    logger.info("New non photo/video in channel")

        # Try to get channel entities
        try:
            for ch in self.selected_chats:
                channel = await self.client.get_entity(ch)
                logger.info(f"Listening for messages in {channel.title}")
        except (TypeError, ValueError) as e:
            logger.error(f"Error getting channel entity: {e}")
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Disconnect the Telethon client."""
        if self.client.is_connected():
            await self.client.disconnect()
        logger.info("TelegramClient disconnected")
