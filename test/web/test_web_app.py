import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from telegram_auto_poster.web.app import CONFIG, app
from telegram_auto_poster.web.auth import sign_telegram_data

from .conftest import login_payload


def test_queue_requires_login(mocker):
    async def fake_run_in_threadpool(func, *args, **kwargs):
        return await func(*args, **kwargs)

    mocker.patch(
        "telegram_auto_poster.web.app.run_in_threadpool", side_effect=fake_run_in_threadpool
    )
    mocker.patch(
        "telegram_auto_poster.web.app.get_scheduled_posts_count",
        new=mocker.AsyncMock(return_value=0),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.get_scheduled_posts",
        new=mocker.AsyncMock(return_value=[]),
    )
    with TestClient(app) as client:
        resp = client.get("/queue")
        assert resp.status_code == 401
        payload = login_payload(CONFIG.bot.admin_ids[0])
        assert client.post("/auth", json=payload).status_code == 200
        assert client.get("/queue").status_code == 200


def test_login_rejects_non_admin():
    with TestClient(app) as client:
        payload = login_payload(999999)
        resp = client.post("/auth", json=payload)
        assert resp.status_code == 403


def test_login_rejects_stale_payload():
    with TestClient(app) as client:
        payload = login_payload(CONFIG.bot.admin_ids[0])
        payload["auth_date"] -= 90000
        payload["hash"] = sign_telegram_data(
            {"id": payload["id"], "auth_date": payload["auth_date"]},
            CONFIG.bot.bot_token.get_secret_value(),
        )
        resp = client.post("/auth", json=payload)
        assert resp.status_code == 400


@pytest.mark.parametrize(
    "method, payload_kwarg",
    [
        ("POST", "json"),
        ("GET", "params"),
    ],
)
def test_login_sets_session_cookie(method, payload_kwarg):
    with TestClient(app) as client:
        payload = login_payload(CONFIG.bot.admin_ids[0])
        resp = client.request(method, "/auth", **{payload_kwarg: payload})
        assert resp.status_code == 200
        assert client.cookies.get("session") is not None


def test_queue_lists_posts(mocker, auth_client: TestClient):
    async def fake_run_in_threadpool(func, *args, **kwargs):
        return await func(*args, **kwargs)

    mocker.patch(
        "telegram_auto_poster.web.app.run_in_threadpool", side_effect=fake_run_in_threadpool
    )
    mocker.patch(
        "telegram_auto_poster.web.app.get_scheduled_posts_count",
        new=mocker.AsyncMock(return_value=1),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.get_scheduled_posts",
        new=mocker.AsyncMock(return_value=[("photos/processed.jpg", 1)]),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_presigned_url",
        new=mocker.AsyncMock(return_value="http://example.com/photos/processed.jpg"),
    )
    resp = auth_client.get("/queue")
    assert resp.status_code == 200
    assert "http://example.com/photos/processed.jpg" in resp.text


def test_reschedule_route_updates_timestamp(mocker, auth_client: TestClient):
    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    mocker.patch(
        "telegram_auto_poster.web.app.run_in_threadpool", side_effect=fake_run_in_threadpool
    )
    add_post = mocker.patch("telegram_auto_poster.web.app.add_scheduled_post")
    resp = auth_client.post(
        "/queue/schedule",
        data={"path": "foo.jpg", "scheduled_at": "2024-01-02 03:04"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    expected_ts = int(datetime.datetime(2024, 1, 2, 0, 4, tzinfo=datetime.timezone.utc).timestamp())
    add_post.assert_called_once_with(expected_ts, "foo.jpg")


def test_stats_endpoint(mocker, auth_client: TestClient):
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
    resp = auth_client.get("/stats")
    assert resp.status_code == 200


def test_stats_requires_login():
    with TestClient(app) as client:
        resp = client.get("/stats")
        assert resp.status_code == 401
