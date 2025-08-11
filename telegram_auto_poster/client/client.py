import asyncio

from loguru import logger
from telethon import TelegramClient, events, types

from ..config import SELECTED_CHATS, load_config
from ..utils.stats import stats
from ..utils.storage import storage, DOWNLOADS_PATH, BUCKET_MAIN
import os

# Create a global client variable that can be accessed from other modules
client_instance = None


class TelegramMemeClient:
    def __init__(self, application):
        config = load_config()
        self.client = TelegramClient(
            config["username"], config["api_id"], config["api_hash"]
        )
        self.application = application
        self.target_channel = config["target_channel"]
        self.bot_chat_id = config["bot_chat_id"]

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

    async def start(self):
        """Start the client and register event handlers."""
        await self.client.start()
        logger.info("TelegramClient started successfully")

        # Import process_photo and process_video here to avoid circular imports
        from ..bot.handlers import process_photo, process_video

        # Register event handler for new messages
        @self.client.on(events.NewMessage(chats=SELECTED_CHATS))
        async def handle_new_message(event):
            file_path = None
            try:
                if isinstance(event.media, types.MessageMediaPhoto):
                    photo = event.media.photo
                    file_path = f"downloaded_image_{event.id}.jpg"
                    stats.record_received("photo")
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
                        stats.record_received("video")
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
            for ch in SELECTED_CHATS:
                channel = await self.client.get_entity(ch)
                logger.info(f"Listening for messages in {channel.title}")
        except (TypeError, ValueError) as e:
            logger.error(f"Error getting channel entity: {e}")
            return

        await asyncio.Event().wait()

    async def stop(self):
        """Stop the client."""
        await self.client.disconnect()
        logger.info("TelegramClient disconnected")
