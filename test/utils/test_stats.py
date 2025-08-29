import fakeredis
import pytest
import pytest_asyncio

from telegram_auto_poster.config import CONFIG
from telegram_auto_poster.utils import db
from telegram_auto_poster.utils.stats import MediaStats
from telegram_auto_poster.utils.db import _redis_key


@pytest_asyncio.fixture
async def stats_instance(mocker):
    mocker.patch("telegram_auto_poster.utils.db.AsyncValkey", fakeredis.aioredis.FakeRedis)
    mocker.patch.object(CONFIG.valkey.password, "get_secret_value", return_value=None)
    db._async_redis_client = None
    MediaStats._instance = None
    inst = MediaStats()
    await inst.r.flushdb()
    yield inst
    await inst.r.flushdb()
    MediaStats._instance = None


@pytest.mark.asyncio
async def test_rates(stats_instance):
    daily = {
        "photos_processed": 5,
        "videos_processed": 5,
        "photos_approved": 3,
        "videos_approved": 2,
        "media_received": 10,
        "processing_errors": 1,
        "storage_errors": 1,
        "telegram_errors": 0,
    }
    assert await stats_instance.get_success_rate_24h(daily) == pytest.approx(80.0)

    await stats_instance._increment("photos_processed", scope="total", count=10)
    await stats_instance._increment("photos_approved", scope="total", count=7)
    await stats_instance._increment("videos_approved", scope="total", count=1)
    assert await stats_instance.get_approval_rate_total() == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_get_busiest_hour(stats_instance):
    await stats_instance.r.set(_redis_key("hourly", "2"), 3)
    await stats_instance.r.set(_redis_key("hourly", "5"), 7)
    assert await stats_instance.get_busiest_hour() == (5, 7)
