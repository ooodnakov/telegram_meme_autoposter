from unittest.mock import MagicMock, patch

patch("sqlalchemy.create_engine").start()
patch("valkey.Valkey").start()
patch("minio.Minio").start()

import pytest







@pytest.fixture
def mock_config(mocker):
    """
    Autouse fixture to mock config loading for all tests.
    """
    mocker.patch(
        "telegram_auto_poster.config.load_config",
        return_value={
            "telegram": {"api_id": "123", "api_hash": "abc"},
            "minio": {
                "access_key": "minio",
                "secret_key": "minio123",
                "endpoint": "localhost:9000",
            },
            "settings": {
                "deduplication_threshold": "95",
                "target_channel_id": "@test",
            },
        },
    )
