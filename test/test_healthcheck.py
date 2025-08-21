import pytest
from unittest.mock import AsyncMock, MagicMock

import healthcheck


@pytest.mark.asyncio
async def test_healthcheck_success(mocker):
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mocker.patch.object(healthcheck, "client_instance", mock_client)

    mock_storage = MagicMock()
    mock_storage.client = MagicMock()
    mock_storage.client.bucket_exists = AsyncMock(return_value=True)
    mocker.patch.object(healthcheck, "storage", mock_storage)

    mock_stats = MagicMock()
    mock_stats.stats = MagicMock()
    mock_stats.stats.r = MagicMock()
    mock_stats.stats.r.ping = AsyncMock(return_value=True)
    mocker.patch.object(healthcheck, "stats_module", mock_stats)

    assert await healthcheck.check_health() is True


@pytest.mark.asyncio
async def test_healthcheck_fail_minio(mocker):
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mocker.patch.object(healthcheck, "client_instance", mock_client)

    mock_storage = MagicMock()
    mock_storage.client = MagicMock()
    mock_storage.client.bucket_exists = AsyncMock(side_effect=Exception("boom"))
    mocker.patch.object(healthcheck, "storage", mock_storage)

    mock_stats = MagicMock()
    mock_stats.stats = MagicMock()
    mock_stats.stats.r = MagicMock()
    mock_stats.stats.r.ping = AsyncMock(return_value=True)
    mocker.patch.object(healthcheck, "stats_module", mock_stats)

    assert await healthcheck.check_health() is False
