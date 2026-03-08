"""Helpers for storing and retrieving channel lists in Valkey."""

from __future__ import annotations

import json
from typing import Iterable, Sequence

from loguru import logger

from telegram_auto_poster.utils.db import _redis_key, get_async_redis_client, get_redis_client

SELECTED_CHATS_KEY = _redis_key("config", "selected_chats")


def _normalize_channels(channels: Iterable[str | int]) -> list[str]:
    """Return a cleaned list of channel identifiers as strings."""

    normalized: list[str] = []
    for channel in channels:
        if channel is None:
            continue
        value = str(channel).strip()
        if value:
            normalized.append(value)
    return normalized


def _parse_raw_channels(raw: str | list[str] | None) -> list[str]:
    """Parse a raw Valkey value into a list of channels."""

    if not raw:
        return []

    if isinstance(raw, list):
        return _normalize_channels(raw)

    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Stored selected_chats value is not valid JSON, ignoring it")
        return []
    if not isinstance(loaded, list):
        logger.warning("Stored selected_chats value is not a list, ignoring it")
        return []
    return _normalize_channels(loaded)


def ensure_selected_chats_cached(default_channels: Iterable[str | int]) -> list[str]:
    """Ensure selected chats exist in Valkey and return the current value."""

    channels = _normalize_channels(default_channels)
    client = get_redis_client()
    stored = _parse_raw_channels(client.get(SELECTED_CHATS_KEY))
    if stored:
        logger.info("Loaded selected chats from Valkey cache")
        return stored

    client.set(SELECTED_CHATS_KEY, json.dumps(channels))
    logger.info("Initialized Valkey cache for selected chats")
    return channels


async def fetch_selected_chats(*, fallback: Sequence[str | int] | None = None) -> list[str]:
    """Fetch the selected chats from Valkey, falling back to defaults."""

    client = get_async_redis_client()
    stored = _parse_raw_channels(await client.get(SELECTED_CHATS_KEY))
    if stored:
        return stored

    if fallback:
        return _normalize_channels(fallback)
    return []


async def store_selected_chats(channels: Iterable[str | int]) -> list[str]:
    """Persist the provided channel list to Valkey."""

    normalized = _normalize_channels(channels)
    client = get_async_redis_client()
    await client.set(SELECTED_CHATS_KEY, json.dumps(normalized))
    return normalized
