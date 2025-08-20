import importlib

import fakeredis
import fakeredis.aioredis
import pytest
import valkey


@pytest.fixture
def stats_module(monkeypatch, mocker):
    """Prepare test environment with fake Redis."""

    monkeypatch.setattr(
        valkey, "Valkey", lambda *a, **k: fakeredis.FakeRedis(decode_responses=True)
    )
    monkeypatch.setattr(
        valkey.asyncio,
        "Valkey",
        lambda *a, **k: fakeredis.aioredis.FakeRedis(decode_responses=True),
    )
    monkeypatch.setenv("VALKEY_HOST", "localhost")
    monkeypatch.setenv("VALKEY_PORT", "6379")
    monkeypatch.setenv("VALKEY_PASS", "redis")
    monkeypatch.setenv("REDIS_PREFIX", "telegram_auto_poster_test")

    import telegram_auto_poster.config as cfg
    importlib.reload(cfg)
    import telegram_auto_poster.utils.storage as storage_module
    import telegram_auto_poster.utils.stats as stats_module
    importlib.reload(storage_module)
    importlib.reload(stats_module)
    return stats_module


@pytest.mark.asyncio
async def test_generate_stats_report_format(stats_module, mocker):
    """Test the HTML formatting of the stats report."""

    stats = stats_module.stats
    mocker.patch.object(
        stats,
        "get_performance_metrics",
        new=mocker.AsyncMock(
            return_value={
                "avg_photo_processing_time": 1.0,
                "avg_video_processing_time": 2.0,
                "avg_upload_time": 3.0,
                "avg_download_time": 4.0,
            }
        ),
    )

    report = await stats.generate_stats_report()

    assert isinstance(report, str)
    assert "<b>Statistics Report</b>" in report
    assert "<b>Last 24 Hours:</b>" in report
    assert "<b>Performance Metrics:</b>" in report
    assert "<b>All-Time Totals:</b>" in report
    assert "<i>Last reset:" in report
    assert "📊" in report
    assert "📥" in report
    assert "📈" in report
    assert "✨" in report
    assert "🛑" in report
    assert "🗃️" in report

