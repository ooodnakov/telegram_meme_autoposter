import importlib
import sys
import fakeredis
import valkey
import pytest
from unittest.mock import patch
import sqlalchemy


@pytest.fixture
def stats_module(monkeypatch, mocker):
    """Prepare test environment with in-memory DB and fake Redis."""
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: engine)
    monkeypatch.setattr(
        valkey, "Valkey", lambda *a, **k: fakeredis.FakeRedis(decode_responses=True)
    )
    monkeypatch.setenv("DB_MYSQL_USER", "test")
    monkeypatch.setenv("DB_MYSQL_PASSWORD", "test")
    monkeypatch.setenv("DB_MYSQL_HOST", "localhost")
    monkeypatch.setenv("DB_MYSQL_PORT", "3306")
    monkeypatch.setenv("DB_MYSQL_NAME", "test")
    monkeypatch.setenv("VALKEY_HOST", "localhost")
    monkeypatch.setenv("VALKEY_PORT", "6379")
    monkeypatch.setenv("VALKEY_PASS", "redis")
    monkeypatch.setenv("REDIS_PREFIX", "telegram_auto_poster_test")

    if "telegram_auto_poster.utils.stats" in sys.modules:
        del sys.modules["telegram_auto_poster.utils.stats"]
    if "telegram_auto_poster.utils.storage" in sys.modules:
        del sys.modules["telegram_auto_poster.utils.storage"]
    if "telegram_auto_poster.config" in sys.modules:
        del sys.modules["telegram_auto_poster.config"]

    mocker.patch("minio.Minio")
    import telegram_auto_poster.config

    importlib.reload(telegram_auto_poster.config)
    import telegram_auto_poster.utils.storage
    import telegram_auto_poster.utils.stats

    importlib.reload(telegram_auto_poster.utils.storage)
    importlib.reload(telegram_auto_poster.utils.stats)
    telegram_auto_poster.utils.stats.init_stats()
    yield telegram_auto_poster.utils.stats


def test_generate_stats_report_format(stats_module):
    """Test the HTML formatting of the stats report."""
    stats = stats_module.stats
    # Act
    report = stats.generate_stats_report()

    # Assert
    assert isinstance(report, str)
    assert "<b>Statistics Report</b>" in report
    assert "<b>Last 24 Hours:</b>" in report
    assert "<b>Performance Metrics:</b>" in report
    assert "<b>All-Time Totals:</b>" in report
    assert "<i>Last reset:" in report

    # Check for some emojis
    assert "📊" in report
    assert "📥" in report
    assert "📈" in report
    assert "✨" in report
    assert "🛑" in report
    assert "🗃️" in report
