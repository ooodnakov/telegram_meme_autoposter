"""Valkey/Redis client utilities and scheduled post helpers."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from telegram_auto_poster.config import CONFIG

if TYPE_CHECKING:  # pragma: no cover - imported only for type checking
    from valkey import Valkey as ValkeyClient
    from valkey.asyncio import Valkey as AsyncValkeyClient
else:  # pragma: no cover - fall back to ``Any`` when dependency missing
    ValkeyClient = Any  # type: ignore[misc]
    AsyncValkeyClient = Any  # type: ignore[misc]

Valkey: Any | None = None
AsyncValkey: Any | None = None

_redis_client: ValkeyClient | None = None
_async_clients: dict[int, tuple[asyncio.AbstractEventLoop, AsyncValkeyClient]] = {}


def get_redis_client() -> ValkeyClient:
    """Return a singleton instance of the Valkey (Redis) client.

    Returns:
        Valkey: Connected Valkey client instance.

    """
    global _redis_client
    if _redis_client is None:
        global Valkey
        if Valkey is None:  # Import here so monkeypatching works
            from valkey import Valkey as _Valkey

            Valkey = _Valkey

        _redis_client = Valkey(**_connection_kwargs())
    return _redis_client


def get_async_redis_client() -> AsyncValkeyClient:
    """Return an async Valkey client bound to the current event loop."""

    loop = asyncio.get_running_loop()
    loop_id = id(loop)

    entry = _async_clients.get(loop_id)
    if entry is None:
        global AsyncValkey
        if AsyncValkey is None:  # Import lazily so monkeypatching works
            from valkey.asyncio import Valkey as _AsyncValkey

            AsyncValkey = _AsyncValkey

        client = AsyncValkey(**_connection_kwargs())
        _async_clients[loop_id] = (loop, client)
        return client

    return entry[1]


def reset_cache_for_tests() -> None:
    """Reset cached clients and flush the backing data store."""

    global _redis_client

    if _redis_client is not None:
        try:
            _redis_client.flushdb()
            _redis_client.close()
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.debug("Failed to flush redis client during reset: {}", exc)
    _redis_client = None

    for loop, client in list(_async_clients.values()):
        try:
            if loop.is_closed():
                continue

            close_coro = client.close()
            try:
                fut = asyncio.run_coroutine_threadsafe(close_coro, loop)
            except RuntimeError:
                close_coro.close()
                try:
                    running_loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(client.close())
                else:
                    if running_loop is loop:
                        running_loop.create_task(client.close())
                    else:
                        fut = asyncio.run_coroutine_threadsafe(client.close(), loop)
                        fut.result()
            else:
                fut.result()
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.debug("Failed to close async redis client during reset: {}", exc)
    _async_clients.clear()

    # Ensure the external backend is cleared as well
    temp_client: Any | None = None
    try:
        from valkey import Valkey as _Valkey

        temp_client = _Valkey(**_connection_kwargs())
        temp_client.flushdb()
    except Exception as exc:  # pragma: no cover - temporary store may be offline
        logger.debug("Unable to flush valkey backend during reset: {}", exc)
    finally:
        if temp_client is not None:
            try:
                temp_client.close()
            except Exception as exc:  # pragma: no cover - best effort cleanup
                logger.debug(
                    "Failed to close temporary valkey client during reset: {}", exc
                )


def _connection_kwargs() -> dict[str, Any]:
    """Return connection keyword arguments for Valkey clients."""

    password = CONFIG.valkey.password.get_secret_value()
    kwargs: dict[str, Any] = {
        "host": CONFIG.valkey.host,
        "port": CONFIG.valkey.port,
        "decode_responses": True,
    }
    if password:
        kwargs["password"] = password
    return kwargs


def _redis_prefix() -> str:
    """Return the Redis key prefix, defaulting to the project name."""
    return CONFIG.valkey.prefix


def _redis_key(scope: str, name: str) -> str:
    """Compose a Redis key using the global prefix, ``scope`` and ``name``.

    Args:
        scope: Namespace for the counter (e.g. ``"daily"``).
        name: Metric or object name.

    Returns:
        str: Combined key.

    """
    prefix = _redis_prefix()
    return f"{prefix}:{scope}:{name}" if prefix else f"{scope}:{name}"


def _redis_meta_key() -> str:
    """Return the key used for storing metadata such as last reset time.

    Returns:
        str: Metadata key name.

    """
    prefix = _redis_prefix()
    return f"{prefix}:daily_last_reset" if prefix else "daily_last_reset"


def add_scheduled_post(scheduled_time: int, file_path: str) -> None:
    """Store or update a post's explicit scheduled timestamp.

    The timestamp is stored both as the score of a sorted set (for range
    queries) and in a hash for quick lookup of an individual post's
    ``scheduled_at`` value.

    Args:
        scheduled_time: Unix timestamp when the post should be published.
        file_path: Path identifier for the media item.

    """
    client = get_redis_client()
    zset_key = _redis_key("scheduled_posts", "schedule")
    hash_key = _redis_key("scheduled_posts", "scheduled_at")
    pipe = client.pipeline()
    pipe.zadd(zset_key, {file_path: scheduled_time})
    pipe.hset(hash_key, file_path, str(scheduled_time))
    pipe.execute()


def get_scheduled_posts(
    min_score: int = 0,
    max_score: int | None = None,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[tuple[str, float]]:
    """Retrieve scheduled posts by score (Unix timestamp).

    Args:
        min_score: Minimum score (timestamp) to include.
        max_score: Maximum score (timestamp) to include. ``None`` means no
            upper bound.
        offset: Number of leading results to skip.
        limit: Maximum number of results to return.

    Returns:
        list[tuple[str, float]]: List of ``(file_path, timestamp)`` pairs.

    """
    client = get_redis_client()
    key = _redis_key("scheduled_posts", "schedule")

    # Use score-based range; default to all (0 .. +inf)
    min_bound = min_score
    max_bound = "+inf" if max_score is None else max_score
    if limit is None and offset == 0:
        result = client.zrangebyscore(key, min_bound, max_bound, withscores=True)
    else:
        result = client.zrangebyscore(
            key,
            min_bound,
            max_bound,
            start=offset,
            num=limit,
            withscores=True,
        )
    return cast(list[tuple[str, float]], result)


def get_scheduled_posts_count(min_score: int = 0, max_score: int | None = None) -> int:
    """Return the number of scheduled posts in the given score range."""
    client = get_redis_client()
    key = _redis_key("scheduled_posts", "schedule")
    min_bound = min_score
    max_bound = "+inf" if max_score is None else max_score
    result = client.zcount(key, min_bound, max_bound)
    return cast(int, result)


def remove_scheduled_post(file_path: str) -> None:
    """Remove a post from the schedule.

    Args:
        file_path: Path identifier of the media to remove.

    """
    client = get_redis_client()
    zset_key = _redis_key("scheduled_posts", "schedule")
    hash_key = _redis_key("scheduled_posts", "scheduled_at")
    pipe = client.pipeline()
    pipe.zrem(zset_key, file_path)
    pipe.hdel(hash_key, file_path)
    pipe.execute()


def get_scheduled_time(file_path: str) -> int | None:
    """Return the stored ``scheduled_at`` timestamp for ``file_path``.

    Args:
        file_path: Path of the media item.

    Returns:
        Optional[int]: Unix timestamp or ``None`` if not scheduled.

    """
    client = get_redis_client()
    key = _redis_key("scheduled_posts", "scheduled_at")
    value = cast(str | None, client.hget(key, file_path))
    return int(value) if value is not None else None


async def increment_batch_count(amount: int = 1) -> int:
    """Increment the batch size counter.

    Args:
        amount: How much to increment the counter by.

    Returns:
        int: The new counter value.

    """
    r = get_async_redis_client()
    key = _redis_key("batch", "size")
    return await r.incrby(key, amount)


async def decrement_batch_count(amount: int) -> int:
    """Decrement the batch size counter.

    Args:
        amount: How much to decrement the counter by.

    Returns:
        int: The updated counter value, clamped at zero.

    """
    r = get_async_redis_client()
    key = _redis_key("batch", "size")
    new_val = await r.decrby(key, amount)
    if new_val < 0:
        await r.set(key, "0")
        new_val = 0
    return new_val


async def get_batch_count() -> int:
    """Return the current batch size."""
    r = get_async_redis_client()
    key = _redis_key("batch", "size")
    value = await r.get(key)
    return int(value) if value is not None else 0


async def add_trashed_post(path: str, expires_at: int) -> None:
    """Record ``path`` as trashed until ``expires_at`` (UTC timestamp)."""

    r = get_async_redis_client()
    key = _redis_key("trash", "expires")
    await r.zadd(key, {path: expires_at})


async def remove_trashed_post(path: str) -> None:
    """Remove ``path`` from the trashed registry."""

    r = get_async_redis_client()
    key = _redis_key("trash", "expires")
    await r.zrem(key, path)


async def get_expired_trashed_posts(now: int | None = None) -> list[str]:
    """Return trashed paths whose expiration is at or before ``now``."""

    r = get_async_redis_client()
    key = _redis_key("trash", "expires")
    max_score = now if now is not None else int(time.time())
    expired = await r.zrangebyscore(key, 0, max_score)
    if expired:
        await r.zremrangebyscore(key, 0, max_score)
    return list(expired)


async def get_trashed_posts_count() -> int:
    """Return the number of trashed posts currently tracked."""

    r = get_async_redis_client()
    key = _redis_key("trash", "expires")
    count = await r.zcard(key)
    return int(count) if count is not None else 0
