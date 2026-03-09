"""Telethon-based client for monitoring source channels and forwarding media."""

import asyncio
import os
import time
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
from telegram_auto_poster.utils.channel_analytics import (
    CHANNEL_ANALYTICS_REFRESH_THRESHOLD_SECONDS,
    refresh_channel_analytics_cache,
)
from telegram_auto_poster.utils.channels import (
    ensure_selected_chats_cached,
    fetch_selected_chats,
)
from telegram_auto_poster.utils.general import RateLimiter, backoff_delay


class TelegramMemeClient:
    """Utility class that listens to Telegram channels using Telethon.

    Attributes:
        client (TelegramClient): Underlying Telethon client instance.
        application (Application): Telegram bot application used for
            processing.
        target_channels (list[str]): Channel usernames or IDs where media is forwarded.
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
        self.target_channels = config.telegram.target_channels
        self.bot_chat_id = config.bot.bot_chat_id
        self.selected_chats = ensure_selected_chats_cached(config.chats.selected_chats)
        self._selected_chat_ids: set[int] = set()
        self._selected_chat_usernames: set[str] = set()
        self._selected_chat_last_refresh = 0.0
        self._selected_chat_refresh_interval = 30.0
        self._update_selected_chat_lookup(self.selected_chats)
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

    def _update_selected_chat_lookup(self, channels: list[str]) -> None:
        """Cache selected chats for quick membership tests."""

        self.selected_chats = channels
        ids: set[int] = set()
        usernames: set[str] = set()
        for channel in channels:
            cleaned = channel.strip()
            if not cleaned:
                continue
            if cleaned.lstrip("-").isdigit():
                try:
                    channel_id = int(cleaned)
                except ValueError:
                    continue
                ids.add(channel_id)
                ids.add(abs(channel_id))
            else:
                usernames.add(cleaned.lstrip("@").lower())
        self._selected_chat_ids = ids
        self._selected_chat_usernames = usernames

    async def _refresh_selected_chats(self, *, force: bool = False) -> None:
        """Refresh selected chats from Valkey, updating caches if needed."""

        now = time.monotonic()
        if (
            not force
            and now - self._selected_chat_last_refresh
            < self._selected_chat_refresh_interval
        ):
            return

        channels = await fetch_selected_chats(fallback=self.selected_chats)
        if channels != self.selected_chats:
            rendered = ", ".join(channels) if channels else "<empty>"
            logger.info(f"Selected chats updated from Valkey: {rendered}")
        self._update_selected_chat_lookup(channels)
        self._selected_chat_last_refresh = now

    async def _is_selected_chat(self, event: EventCommon) -> bool:
        """Return ``True`` when the event is from a monitored chat."""

        await self._refresh_selected_chats()
        chat = event.chat if getattr(event, "chat", None) else await event.get_chat()
        candidate_ids = {
            candidate
            for candidate in (
                getattr(chat, "id", None),
                getattr(event, "chat_id", None),
            )
            if isinstance(candidate, int)
        }
        candidate_ids.update(abs(candidate) for candidate in tuple(candidate_ids))
        if candidate_ids.intersection(self._selected_chat_ids):
            return True

        username = getattr(chat, "username", None)
        if (
            isinstance(username, str)
            and username.lower() in self._selected_chat_usernames
        ):
            return True
        return False

    async def _channel_analytics_refresh_loop(self) -> None:
        """Refresh cached Telegram-provided channel analytics while connected."""

        while self._running:
            try:
                await refresh_channel_analytics_cache(self.client, self.target_channels)
            except asyncio.CancelledError:  # pragma: no cover - task cancellation
                raise
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning(
                    f"Failed to refresh Telegram channel analytics cache: {exc}"
                )
            await asyncio.sleep(CHANNEL_ANALYTICS_REFRESH_THRESHOLD_SECONDS)

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

        @self.client.on(events.Album())
        async def handle_album(
            event: EventCommon,
        ) -> None:  # pragma: no cover - telemetry
            if not await self._is_selected_chat(event):
                return
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

        @self.client.on(events.NewMessage())
        async def handle_new_message(
            event: EventCommon,
        ) -> None:  # pragma: no cover - telemetry
            if not await self._is_selected_chat(event):
                return
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
                await self._refresh_selected_chats(force=True)
                logger.info("TelegramClient started successfully")
                analytics_task = asyncio.create_task(
                    self._channel_analytics_refresh_loop()
                )
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
                try:
                    await self.client.run_until_disconnected()
                finally:
                    analytics_task.cancel()
                    await asyncio.gather(analytics_task, return_exceptions=True)
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
