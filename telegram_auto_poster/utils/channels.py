"""Helpers for storing and retrieving channel lists in Valkey."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

from loguru import logger
from telegram_auto_poster.utils.db import (
    _redis_key,
    get_async_redis_client,
    get_redis_client,
)
from valkey.exceptions import ValkeyError

SELECTED_CHATS_KEY = _redis_key("config", "selected_chats")


def _normalize_channels(channels: Iterable[str | int]) -> list[str]:
    """Return unique channel identifiers as cleaned strings."""

    normalized: list[str] = []
    seen: set[str] = set()
    for channel in channels:
        if channel is None:
            continue
        value = str(channel).strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _parse_raw_channels(raw: str | list[str] | None) -> list[str] | None:
    """Parse a raw Valkey value into a normalized channel list."""

    if raw is None:
        return None
    if isinstance(raw, list):
        return _normalize_channels(raw)

    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("stored selected chats value is not valid JSON") from exc

    if not isinstance(loaded, list):
        raise ValueError("stored selected chats value is not a list")

    return _normalize_channels(loaded)


def get_selected_chats_cache_key() -> str:
    """Return the Valkey key used for the runtime source channel list."""

    return SELECTED_CHATS_KEY


def ensure_selected_chats_cached(default_channels: Iterable[str | int]) -> list[str]:
    """Ensure selected chats exist in Valkey and return the current value."""

    channels = _normalize_channels(default_channels)
    client = get_redis_client()
    try:
        raw = client.get(SELECTED_CHATS_KEY)
        stored = _parse_raw_channels(raw)
        if stored is not None:
            logger.info("Loaded selected chats from Valkey cache")
            return stored

        client.set(SELECTED_CHATS_KEY, json.dumps(channels))
        logger.info("Initialized Valkey cache for selected chats")
    except ValueError as exc:
        logger.warning(f"Invalid selected chats cache, resetting to defaults: {exc}")
        client.set(SELECTED_CHATS_KEY, json.dumps(channels))
    except ValkeyError as exc:
        logger.warning(
            f"Failed to read selected chats from Valkey, using defaults: {exc}"
        )
    return channels


async def fetch_selected_chats(
    *, fallback: Sequence[str | int] | None = None
) -> list[str]:
    """Fetch selected chats from Valkey, falling back only when the key is absent."""

    try:
        client = get_async_redis_client()
        raw = await client.get(SELECTED_CHATS_KEY)
        stored = _parse_raw_channels(raw)
        if stored is not None:
            return stored
    except ValueError as exc:
        logger.warning(f"Invalid selected chats cache, using fallback: {exc}")
    except ValkeyError as exc:
        logger.warning(f"Failed to fetch selected chats from Valkey: {exc}")

    if fallback is None:
        return []
    return _normalize_channels(fallback)


async def store_selected_chats(channels: Iterable[str | int]) -> list[str]:
    """Persist the provided channel list to Valkey."""

    normalized = _normalize_channels(channels)
    client = get_async_redis_client()
    await client.set(SELECTED_CHATS_KEY, json.dumps(normalized))
    return normalized
