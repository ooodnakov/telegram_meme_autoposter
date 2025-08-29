import fakeredis
import pytest
import pytest_asyncio

from telegram_auto_poster.config import CONFIG
from telegram_auto_poster.utils import db
from telegram_auto_poster.utils.stats import MediaStats
from telegram_auto_poster.utils.db import _redis_key, _redis_meta_key


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


@pytest.mark.asyncio
async def test_generate_stats_report_sections(stats_instance):
    for name in ("photos_processed", "videos_processed"):
        await stats_instance._increment(name)
        await stats_instance._increment(name, scope="total")

    await stats_instance._record_duration("photo_processing", 1.2)
    await stats_instance._record_duration("upload", 0.5)

    report = await stats_instance.generate_stats_report()

    assert "<b>Last 24 Hours:</b>" in report
    assert "<b>Performance Metrics:</b>" in report
    assert "<b>All-Time Totals:</b>" in report


@pytest.mark.asyncio
async def test_reset_daily_stats_clears_counters(stats_instance):
    for name in stats_instance.names:
        await stats_instance._increment(name)
    await stats_instance.r.set(_redis_key("hourly", "1"), 5)

    old_meta = await stats_instance.r.get(_redis_meta_key())

    await stats_instance.reset_daily_stats()

    for name in stats_instance.names:
        assert await stats_instance.r.get(_redis_key("daily", name)) == "0"
    for hour in range(24):
        assert await stats_instance.r.get(_redis_key("hourly", str(hour))) is None

    new_meta = await stats_instance.r.get(_redis_meta_key())
    assert new_meta and new_meta != old_meta


@pytest.mark.asyncio
async def test_force_save_swallows_errors(stats_instance, mocker):
    mock_save = mocker.AsyncMock(side_effect=Exception("boom"))
    mocker.patch.object(stats_instance.r, "save", mock_save)

    await stats_instance.force_save()

    mock_save.assert_awaited_once()
