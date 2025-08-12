import os


# Valkey is only imported when a client is requested. This allows tests to
# monkeypatch ``valkey.Valkey`` before the import happens and avoids connection
# attempts during module import when a Valkey server isn't available.
Valkey = None

_redis_client = None


def get_redis_client():
    """
    Initializes and returns the Valkey client instance.
    Uses a global variable to ensure it's a singleton.
    """
    global _redis_client
    if _redis_client is None:
        global Valkey
        if Valkey is None:  # Import here so monkeypatching works
            from valkey import Valkey as _Valkey

            Valkey = _Valkey

        valkey_host = os.getenv("VALKEY_HOST", "127.0.0.1")
        valkey_port = int(os.getenv("VALKEY_PORT", "6379"))
        valkey_pass = os.getenv("VALKEY_PASS", "redis")
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
    """Return the Redis key prefix, defaulting to project name."""
    return os.getenv("REDIS_PREFIX", "telegram_auto_poster")


def _redis_key(scope: str, name: str) -> str:
    prefix = _redis_prefix()
    return f"{prefix}:{scope}:{name}" if prefix else f"{scope}:{name}"


def _redis_meta_key() -> str:
    prefix = _redis_prefix()
    return f"{prefix}:daily_last_reset" if prefix else "daily_last_reset"


def add_scheduled_post(scheduled_time: int, file_path: str):
    """Adds a post to the scheduled list."""
    client = get_redis_client()
    key = _redis_key("scheduled_posts", "schedule")
    client.zadd(key, {file_path: scheduled_time})


def get_scheduled_posts(min_score: int = 0, max_score: int = -1):
    """Retrieves all scheduled posts."""
    client = get_redis_client()
    key = _redis_key("scheduled_posts", "schedule")
    if max_score == -1:
        max_score = "+inf"
    return client.zrange(key, min_score, max_score, withscores=True)


def remove_scheduled_post(file_path: str):
    """Removes a post from the schedule."""
    client = get_redis_client()
    key = _redis_key("scheduled_posts", "schedule")
    client.zrem(key, file_path)
