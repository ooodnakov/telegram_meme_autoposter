from __future__ import annotations

from unittest.mock import call

from fastapi.testclient import TestClient

from telegram_auto_poster.config import PHOTOS_PATH
from telegram_auto_poster.utils.timezone import parse_to_utc_timestamp
from telegram_auto_poster.web.app import MANUAL_SCHEDULE_INTERVAL_SECONDS


def test_dashboard_api_payload(mocker, auth_client: TestClient):
    mocker.patch(
        "telegram_auto_poster.web.app._get_dashboard_payload",
        new=mocker.AsyncMock(
            return_value={
                "suggestions_count": 1,
                "batch_count": 2,
                "posts_count": 3,
                "trash_count": 4,
                "scheduled_count": 5,
                "next_scheduled_at": None,
                "daily": {"media_received": 10},
                "recent_events": [],
            }
        ),
    )
    resp = auth_client.get("/api/dashboard")
    assert resp.status_code == 200
    assert resp.json()["batch_count"] == 2


def test_queue_api_lists_posts(mocker, auth_client: TestClient):
    async def fake_get_meta(name):
        assert name == "processed.jpg"
        return {"caption": "caption", "source": "@src"}

    mocker.patch(
        "telegram_auto_poster.web.app.get_scheduled_posts_count",
        return_value=1,
    )
    mocker.patch(
        "telegram_auto_poster.web.app.get_scheduled_posts",
        return_value=[("scheduled/processed.jpg", 1)],
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_presigned_url",
        new=mocker.AsyncMock(return_value="http://example.com/media.jpg"),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.get_submission_metadata",
        side_effect=fake_get_meta,
    )

    resp = auth_client.get("/api/queue")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_items"] == 1
    assert payload["items"][0]["url"] == "http://example.com/media.jpg"
    assert payload["items"][0]["caption"] == "caption"


def test_action_api_push_group(mocker, auth_client: TestClient):
    group = mocker.patch(
        "telegram_auto_poster.web.app._push_post_group",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._get_metas_for_paths",
        new=mocker.AsyncMock(return_value=[]),
    )
    record = mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    resp = auth_client.post(
        "/api/actions",
        json={
            "action": "push",
            "origin": "posts",
            "paths": [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"],
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    group.assert_awaited_once_with([f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"])
    record.assert_awaited_once()


def test_batch_send_processes_posts(mocker, auth_client: TestClient):
    posts = [
        {"items": [{"path": f"{PHOTOS_PATH}/batch_a.jpg"}]},
        {"items": [{"path": f"{PHOTOS_PATH}/batch_b.jpg"}]},
    ]
    mocker.patch(
        "telegram_auto_poster.web.app._gather_batch",
        new=mocker.AsyncMock(return_value=posts),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._get_metas_for_paths",
        new=mocker.AsyncMock(return_value=[]),
    )
    push_group = mocker.patch(
        "telegram_auto_poster.web.app._push_post_group",
        new=mocker.AsyncMock(),
    )
    decr = mocker.patch(
        "telegram_auto_poster.web.app.decrement_batch_count",
        new=mocker.AsyncMock(),
    )
    rec = mocker.patch(
        "telegram_auto_poster.web.app.stats.record_batch_sent",
        new=mocker.AsyncMock(),
    )
    record = mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    resp = auth_client.post("/api/batch/send", json={})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "processed_groups": 2}
    assert push_group.await_args_list == [
        call([f"{PHOTOS_PATH}/batch_a.jpg"]),
        call([f"{PHOTOS_PATH}/batch_b.jpg"]),
    ]
    assert decr.await_args_list == [call(1), call(1)]
    assert rec.await_args_list == [call(1), call(1)]
    record.assert_not_awaited()


def test_manual_schedule_api_schedules_paths(mocker, auth_client: TestClient):
    schedule = mocker.patch(
        "telegram_auto_poster.web.app._schedule_post_at",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._get_metas_for_paths",
        new=mocker.AsyncMock(
            return_value=[
                (f"{PHOTOS_PATH}/a.jpg", {}),
                (f"{PHOTOS_PATH}/b.jpg", {}),
            ]
        ),
    )
    record = mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    resp = auth_client.post(
        "/api/batch/manual-schedule",
        json={
            "paths": [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"],
            "scheduled_at": "2024-01-01 12:00",
            "origin": "batch",
        },
    )
    base_ts = parse_to_utc_timestamp("2024-01-01 12:00")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "scheduled": 2}
    assert schedule.await_args_list == [
        call(f"{PHOTOS_PATH}/a.jpg", base_ts),
        call(
            f"{PHOTOS_PATH}/b.jpg",
            base_ts + MANUAL_SCHEDULE_INTERVAL_SECONDS,
        ),
    ]
    record.assert_awaited_once()


def test_reset_endpoints_return_json(mocker, auth_client: TestClient):
    mocker.patch(
        "telegram_auto_poster.web.app.clear_event_history",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.reset_daily_stats",
        new=mocker.AsyncMock(return_value="Daily statistics have been reset."),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.reset_leaderboard",
        new=mocker.AsyncMock(return_value="Leaderboard reset."),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.stats.force_save",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._record_event",
        new=mocker.AsyncMock(),
    )

    assert auth_client.post("/api/events/reset", json={}).json() == {"status": "ok"}
    assert auth_client.post("/api/stats/reset", json={}).json() == {
        "status": "ok",
        "message": "Daily statistics have been reset.",
    }
    assert auth_client.post("/api/leaderboard/reset", json={}).json() == {
        "status": "ok",
        "message": "Leaderboard reset.",
    }
