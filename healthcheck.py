import asyncio

from telegram_auto_poster.client.client import client_instance
from telegram_auto_poster.utils.storage import storage
import telegram_auto_poster.utils.stats as stats_module
from telegram_auto_poster.config import BUCKET_MAIN


async def check_health() -> bool:
    if client_instance is None or not client_instance.is_connected():
        return False
    try:
        await storage.client.bucket_exists(BUCKET_MAIN)
    except Exception:
        return False
    try:
        await stats_module.stats.r.ping()
    except Exception:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(check_health()) else 1)
