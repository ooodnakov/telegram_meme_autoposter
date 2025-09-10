"""Telethon-based client for monitoring source channels and forwarding media."""

import asyncio
import os
from typing import TYPE_CHECKING

from loguru import logger
from telethon import TelegramClient, events, types
from telethon.events.common import EventCommon

if TYPE_CHECKING:
    from loguru import Logger
    from telegram.ext import Application

from telegram_auto_poster.bot.handlers import (
    process_media_group,
    process_photo,
    process_video,
)
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

    def __init__(self, application: "Application", config: Config) -> None:
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

    async def _check_rate_limit(self, chat_id: int, log: "Logger") -> bool:
        """Acquire a token from the rate limiter for the given chat.

        Returns ``True`` if processing should continue, ``False`` otherwise.
        """
        limiter = self.rate_limiters.setdefault(
            chat_id,
            RateLimiter(
                rate=self.rate_limit_config.rate,
                capacity=self.rate_limit_config.capacity,
            ),
        )
        if not await limiter.acquire(drop=True):
            log.warning("Rate limit exceeded")
            if stats_module.stats:
                await stats_module.stats.record_rate_limit_drop()
            return False
        return True

    async def _download_media(
        self, message: types.Message, log: "Logger"
    ) -> tuple["Logger", tuple[str, str, str] | None]:
        """Download supported media from a message.

        Returns a tuple of ``(log, file_info)`` where ``file_info`` is
        ``(path, basename, media_type)``. ``file_info`` is ``None`` if the
        message doesn't contain photo or video media.
        """
        media_info = None
        if isinstance(message.media, types.MessageMediaPhoto):
            media_info = ("photo", message.media.photo, "jpg")
        elif (
            isinstance(message.media, types.MessageMediaDocument)
            and message.media.document
        ):
            media_info = ("video", message.media.document, "mp4")

        if not media_info:
            return log, None

        media_type, media_obj, ext = media_info
        log = log.bind(media_type=media_type)
        file_path = f"{media_type}_{message.id}.{ext}"
        if stats_module.stats:
            await stats_module.stats.record_received(media_type)
        await self.client.download_media(media_obj, file=file_path)
        return log, (file_path, os.path.basename(file_path), media_type)

    async def _get_source_name(self, event: EventCommon) -> str:
        """Return a human-readable name for the originating chat."""
        chat = event.chat if getattr(event, "chat", None) else await event.get_chat()
        return (
            getattr(chat, "username", None)
            or getattr(chat, "title", None)
            or str(event.chat_id)
        )

    async def start(self) -> None:
        """Start the client and maintain the connection with retries."""
        self._running = True

        @self.client.on(events.Album(chats=self.selected_chats))
        async def handle_album(
            event: EventCommon,
        ) -> None:  # pragma: no cover - telemetry
            log = logger.bind(chat_id=event.chat_id, grouped_id=event.grouped_id)
            if not await self._check_rate_limit(event.chat_id, log):
                return

            files: list[tuple[str, str, str]] = []
            source_name = await self._get_source_name(event)
            try:
                for message in event.messages:
                    log, file_info = await self._download_media(message, log)
                    if file_info:
                        files.append(file_info)
                        if stats_module.stats:
                            await stats_module.stats.record_submission(source_name)
                if files:
                    await process_media_group(
                        "New post found with grouped media",
                        files,
                        self.bot_chat_id,
                        self.application,
                        user_metadata={"source": source_name},
                    )
            except Exception:
                log.exception("Failed to handle album")
            finally:
                for path, _, _ in files:
                    if path and os.path.exists(path):
                        os.remove(path)
                if not files:
                    log.info("New non photo/video album in channel")

        @self.client.on(events.NewMessage(chats=self.selected_chats))
        async def handle_new_message(
            event: EventCommon,
        ) -> None:  # pragma: no cover - telemetry
            log = logger.bind(chat_id=event.chat_id, message_id=event.id)
            if not await self._check_rate_limit(event.chat_id, log):
                return

            if getattr(event.message, "grouped_id", None):
                return

            path = None
            try:
                source_name = await self._get_source_name(event)
                log, file_info = await self._download_media(event.message, log)
                if file_info:
                    path, basename, media_type = file_info
                    if stats_module.stats:
                        await stats_module.stats.record_submission(source_name)
                    if media_type == "photo":
                        await process_photo(
                            "New post found with image",
                            path,
                            basename,
                            self.bot_chat_id,
                            self.application,
                            user_metadata={"source": source_name},
                        )
                    elif media_type == "video":
                        await process_video(
                            "New post found with video",
                            path,
                            basename,
                            self.bot_chat_id,
                            self.application,
                            user_metadata={"source": source_name},
                        )
            except Exception:
                log.exception("Failed to handle message")
            finally:
                if path and os.path.exists(path):
                    os.remove(path)
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
