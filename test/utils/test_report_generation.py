import importlib

import pytest

from telegram_auto_poster.utils import db
from telegram_auto_poster.utils.storage import reset_storage_for_tests


@pytest.fixture
def stats_module():
    db.reset_cache_for_tests()
    reset_storage_for_tests()
    import telegram_auto_poster.utils.stats as stats_module

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
