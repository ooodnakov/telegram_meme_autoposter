import importlib
import os
import sys
import types
import fakeredis
import valkey
import pytest
from unittest.mock import patch
import sqlalchemy

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def stats_module():
    """Prepare test environment with in-memory DB and fake Redis."""
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    with patch("sqlalchemy.create_engine", lambda *a, **k: engine), \
         patch("valkey.Valkey", lambda *a, **k: fakeredis.FakeRedis(decode_responses=True)), \
         patch("minio.Minio"), \
         patch.dict(os.environ, {
            "DB_MYSQL_USER": "test",
            "DB_MYSQL_PASSWORD": "test",
            "DB_MYSQL_HOST": "localhost",
            "DB_MYSQL_PORT": "3306",
            "DB_MYSQL_NAME": "test",
            "VALKEY_HOST": "localhost",
            "VALKEY_PORT": "6379",
            "VALKEY_PASS": "redis",
            "REDIS_PREFIX": "telegram_auto_poster_test"
         }):
        # Import the module under test
        import telegram_auto_poster.utils.storage
        import telegram_auto_poster.utils.stats
        yield telegram_auto_poster.utils.stats


def test_generate_stats_report_format(stats_module):
    """Test the HTML formatting of the stats report."""
    stats = stats_module

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
