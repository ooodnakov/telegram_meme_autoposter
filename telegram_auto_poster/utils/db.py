import os
from valkey import Valkey

_redis_client = None

def get_redis_client():
    """
    Initializes and returns the Valkey client instance.
    Uses a global variable to ensure it's a singleton.
    """
    global _redis_client
    if _redis_client is None:
        valkey_host = os.getenv("VALKEY_HOST", "127.0.0.1")
        valkey_port = int(os.getenv("VALKEY_PORT", "6379"))
        valkey_pass = os.getenv("VALKEY_PASS", "redis")
        _redis_client = Valkey(
            host=valkey_host, port=valkey_port, password=valkey_pass, decode_responses=True
        )
    return _redis_client

redis_prefix = os.getenv("REDIS_PREFIX", "telegram_auto_poster")


def _redis_key(scope: str, name: str) -> str:
    return f"{redis_prefix}:{scope}:{name}" if redis_prefix else f"{scope}:{name}"


def _redis_meta_key() -> str:
    return f"{redis_prefix}:daily_last_reset" if redis_prefix else "daily_last_reset"
