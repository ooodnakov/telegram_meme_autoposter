import asyncio
import os

from loguru import logger
from telethon import TelegramClient, events, types

from telegram_auto_poster.bot.handlers import process_photo, process_video
from telegram_auto_poster.config import Config
from telegram_auto_poster.utils import stats as stats_module
from telegram_auto_poster.utils.general import RateLimiter, backoff_delay


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

    def __init__(self, application, config: Config) -> None:
        """Initialize the Telethon client and store configuration values.

        Args:
            application: PTB ``Application`` instance used for coordination.
            config: Typed configuration instance with credentials and channels.
        """
        self.client = TelegramClient(
            config.telegram.username,
            config.telegram.api_id,
            config.telegram.api_hash,
        )
        self.application = application
        self.target_channel = config.telegram.target_channel
        self.bot_chat_id = config.bot.bot_chat_id
        self.selected_chats = config.chats.selected_chats
        self._running = False
        self.rate_limiters: dict[int, RateLimiter] = {}
        self.rate_limit_config = config.rate_limit

        if self.application and hasattr(self.application, "bot_data"):
            self.application.bot_data["telethon_client"] = self.client
            logger.info("TelegramClient instance stored in application.bot_data")
        else:
            logger.error(
                "Could not store client in application.bot_data - application not ready"
            )

        logger.info("TelegramClient instance created")

    async def start(self) -> None:
        """Start the client and maintain the connection with retries."""
        self._running = True

        @self.client.on(events.NewMessage(chats=self.selected_chats))
        async def handle_new_message(event):  # pragma: no cover - telemetry
            log = logger.bind(chat_id=event.chat_id, message_id=event.id)
            limiter = self.rate_limiters.setdefault(
                event.chat_id,
                RateLimiter(
                    rate=self.rate_limit_config.rate,
                    capacity=self.rate_limit_config.capacity,
                ),
            )
            if not await limiter.acquire(drop=True):
                log.warning("Rate limit exceeded")
                if stats_module.stats:
                    await stats_module.stats.record_rate_limit_drop()
                return

            file_path = None
            try:
                if isinstance(event.media, types.MessageMediaPhoto):
                    log = log.bind(media_type="photo")
                    photo = event.media.photo
                    file_path = f"photo_{event.id}.jpg"
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
                        log = log.bind(media_type="video")
                        if stats_module.stats:
                            await stats_module.stats.record_received("video")
                        video = event.media.document
                        file_path = f"video_{event.id}.mp4"
                        await self.client.download_media(video, file=file_path)
                        await process_video(
                            "New post found with video",
                            file_path,
                            os.path.basename(file_path),
                            self.bot_chat_id,
                            self.application,
                        )
            except Exception:
                log.exception("Failed to handle message")
            finally:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                else:
                    log.info("New non photo/video in channel")

        retry = 0
        while self._running:
            try:
                await self.client.start()
                logger.info("TelegramClient started successfully")
                # Resolve and log monitored channels after connecting
                for ch in self.selected_chats:
                    try:
                        channel = await self.client.get_entity(ch)
                        title = (
                            getattr(channel, "title", None)
                            or getattr(channel, "username", None)
                            or str(ch)
                        )
                        logger.info(f"Listening for messages in {title}")
                    except Exception as e:  # pragma: no cover - network resolution
                        logger.warning(f"Failed to resolve channel {ch}: {e}")
                retry = 0
                await self.client.run_until_disconnected()
            except asyncio.CancelledError:  # pragma: no cover - task cancellation
                break
            except Exception as e:
                retry += 1
                delay = backoff_delay(retry, cap=300)
                logger.bind(retry_count=retry).warning(
                    f"Client disconnected, retrying in {delay:.1f}s: {e}"
                )
                if stats_module.stats:
                    await stats_module.stats.record_client_reconnect()
                await asyncio.sleep(delay)

    async def stop(self) -> None:
        """Disconnect the Telethon client."""
        self._running = False
        if self.client.is_connected():
            await self.client.disconnect()
        logger.info("TelegramClient disconnected")
