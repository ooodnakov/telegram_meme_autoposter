from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_dependencies(mocker):
    """Mock storage and stats singletons used across the project."""
    stats_mock = MagicMock()
    storage_mock = MagicMock()

    stats_targets = [
        "telegram_auto_poster.utils.stats.stats",
        "telegram_auto_poster.bot.handlers.stats",
        "telegram_auto_poster.bot.commands.stats",
        "telegram_auto_poster.utils.stats_client",
    ]
    for target in stats_targets:
        mocker.patch(target, stats_mock)

    storage_targets = [
        "telegram_auto_poster.utils.storage.storage",
        "telegram_auto_poster.bot.handlers.storage",
        "telegram_auto_poster.bot.commands.storage",
        "telegram_auto_poster.media.photo.storage",
        "telegram_auto_poster.media.video.storage",
        "telegram_auto_poster.utils.storage_client",
    ]
    for target in storage_targets:
        mocker.patch(target, storage_mock)




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
