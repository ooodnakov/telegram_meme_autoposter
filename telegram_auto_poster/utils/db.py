from telegram_auto_poster.config import CONFIG

# Valkey is only imported when a client is requested. This allows tests to
# monkeypatch ``valkey.Valkey`` before the import happens and avoids connection
# attempts during module import when a Valkey server isn't available.
Valkey = None

_redis_client = None


def get_redis_client() -> "Valkey":
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

        valkey_host = CONFIG["valkey"]["host"]
        valkey_port = CONFIG["valkey"]["port"]
        valkey_pass = CONFIG["valkey"]["password"]
        _redis_client = Valkey(
            host=valkey_host,
            port=valkey_port,
            password=valkey_pass,
            decode_responses=True,
        )
    else:
        # When using fakeredis in tests, ensure a clean database for each call
        if _redis_client.__class__.__module__.startswith("fakeredis"):
            _redis_client.flushdb()
    return _redis_client


def _redis_prefix() -> str:
    """Return the Redis key prefix, defaulting to the project name."""
    return CONFIG["valkey"]["prefix"]


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
    """Add a post to the sorted set of scheduled posts.

    Args:
        scheduled_time: Unix timestamp when the post should be published.
        file_path: Path identifier for the media item.
    """
    client = get_redis_client()
    key = _redis_key("scheduled_posts", "schedule")
    client.zadd(key, {file_path: scheduled_time})


def get_scheduled_posts(
    min_score: int = 0, max_score: int | None = None
) -> list[tuple[str, float]]:
    """Retrieve scheduled posts by score (Unix timestamp).

    Args:
        min_score: Minimum score (timestamp) to include.
        max_score: Maximum score (timestamp) to include. ``None`` means no
            upper bound.

    Returns:
        list[tuple[str, float]]: List of ``(file_path, timestamp)`` pairs.
    """
    client = get_redis_client()
    key = _redis_key("scheduled_posts", "schedule")

    # Use score-based range; default to all (0 .. +inf)
    min_bound = min_score
    max_bound = "+inf" if max_score is None else max_score
    return client.zrangebyscore(key, min_bound, max_bound, withscores=True)


def remove_scheduled_post(file_path: str) -> None:
    """Remove a post from the schedule.

    Args:
        file_path: Path identifier of the media to remove.
    """
    client = get_redis_client()
    key = _redis_key("scheduled_posts", "schedule")
    client.zrem(key, file_path)
