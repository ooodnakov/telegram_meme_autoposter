from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from telegram_auto_poster.web.app import CONFIG, app


@pytest.fixture(autouse=True)
def clear_access_key():
    original = CONFIG.web.access_key
    CONFIG.web.access_key = None
    yield
    CONFIG.web.access_key = original


def test_queue_requires_access_key(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app.run_in_threadpool",
        new=mocker.AsyncMock(return_value=[]),
    )
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        resp = client.get("/queue")
        assert resp.status_code == 401
        resp = client.get("/queue?key=token")
        assert resp.status_code == 200


def test_queue_rejects_wrong_key(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app.run_in_threadpool",
        new=mocker.AsyncMock(return_value=[]),
    )
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        resp = client.get("/queue?key=bad")
        assert resp.status_code == 401


def test_queue_lists_posts(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app.run_in_threadpool",
        new=mocker.AsyncMock(return_value=[("photos/processed.jpg", 1)]),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_presigned_url",
        new=mocker.AsyncMock(return_value="http://example.com/photos/processed.jpg"),
    )
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        resp = client.get("/queue?key=token")
        assert resp.status_code == 200
        assert "http://example.com/photos/processed.jpg" in resp.text


def test_stats_endpoint(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app.stats.get_daily_stats",
        new=mocker.AsyncMock(
            return_value={
                "processing_errors": 0,
                "storage_errors": 0,
                "telegram_errors": 0,
            }
        ),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.get_total_stats",
        new=mocker.AsyncMock(
            return_value={
                "processing_errors": 0,
                "storage_errors": 0,
                "telegram_errors": 0,
            }
        ),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.get_performance_metrics",
        new=mocker.AsyncMock(
            return_value=SimpleNamespace(
                avg_photo_processing_time=0,
                avg_video_processing_time=0,
                avg_upload_time=0,
                avg_download_time=0,
            )
        ),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.get_busiest_hour",
        new=mocker.AsyncMock(return_value=(0, 0)),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.get_approval_rate_24h",
        new=mocker.AsyncMock(return_value=0.0),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.get_approval_rate_total",
        new=mocker.AsyncMock(return_value=0.0),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.get_success_rate_24h",
        new=mocker.AsyncMock(return_value=0.0),
    )
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        resp = client.get("/stats?key=token")
        assert resp.status_code == 200


def test_stats_requires_access_key():
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        resp = client.get("/stats")
        assert resp.status_code == 401

def test_stats_rejects_wrong_key():
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        resp = client.get("/stats?key=bad")
        assert resp.status_code == 401
