from __future__ import annotations

from unittest.mock import call

from fastapi.testclient import TestClient

from telegram_auto_poster.config import PHOTOS_PATH, BUCKET_MAIN
from telegram_auto_poster.utils.timezone import parse_to_utc_timestamp
from telegram_auto_poster.web.app import CONFIG, app

from .conftest import login_payload

def test_suggestions_view_requires_login(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app._gather_posts",
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._get_suggestions_count",
        new=mocker.AsyncMock(return_value=0),
    )
    with TestClient(app) as client:
        assert client.get("/suggestions").status_code == 401
        payload = login_payload(CONFIG.bot.admin_ids[0])
        assert client.post("/auth", json=payload).status_code == 200
        assert client.get("/suggestions").status_code == 200


def test_posts_view_requires_login(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app._gather_posts",
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._get_posts_count",
        new=mocker.AsyncMock(return_value=0),
    )
    with TestClient(app) as client:
        assert client.get("/posts").status_code == 401
        payload = login_payload(CONFIG.bot.admin_ids[0])
        assert client.post("/auth", json=payload).status_code == 200
        assert client.get("/posts").status_code == 200


def test_batch_view_lists_posts(mocker, auth_client: TestClient):
    mocker.patch(
        "telegram_auto_poster.web.app._gather_batch",
        new=mocker.AsyncMock(
            return_value=[
                {
                    "items": [
                        {
                            "path": f"{PHOTOS_PATH}/batch.jpg",
                            "url": "http://x",
                            "is_image": True,
                            "is_video": False,
                        }
                    ]
                }
            ]
        ),
    )
    mocker.patch(
        "telegram_auto_poster.web.app._get_batch_count",
        new=mocker.AsyncMock(return_value=1),
    )
    resp = auth_client.get("/batch")
    assert resp.status_code == 200
    assert "http://x" in resp.text


def test_send_batch_requires_login(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app._gather_batch",
        new=mocker.AsyncMock(return_value=[]),
    )
    with TestClient(app) as client:
        resp = client.post("/batch/send")
        assert resp.status_code == 401


def test_send_batch_processes_posts(mocker, auth_client: TestClient):
    posts = [
        {"items": [{"path": f"{PHOTOS_PATH}/batch_a.jpg"}]},
        {"items": [{"path": f"{PHOTOS_PATH}/batch_b.jpg"}]},
    ]
    mocker.patch(
        "telegram_auto_poster.web.app._gather_batch",
        new=mocker.AsyncMock(return_value=posts),
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
    resp = auth_client.post(
        "/batch/send",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/batch"
    assert push_group.await_args_list == [
        call([f"{PHOTOS_PATH}/batch_a.jpg"]),
        call([f"{PHOTOS_PATH}/batch_b.jpg"]),
    ]
    assert decr.await_args_list == [call(1), call(1)]
    assert rec.await_args_list == [call(1), call(1)]


def test_send_batch_redirects_when_empty(mocker, auth_client: TestClient):
    mocker.patch(
        "telegram_auto_poster.web.app._gather_batch",
        new=mocker.AsyncMock(return_value=[]),
    )
    resp = auth_client.post(
        "/batch/send",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/batch"


def test_manual_schedule_requires_login():
    with TestClient(app) as client:
        resp = client.post(
            "/batch/manual_schedule",
            data={"scheduled_at": "2024-01-01 12:00"},
        )
        assert resp.status_code == 401


def test_manual_schedule_schedules_paths(mocker, auth_client: TestClient):
    schedule = mocker.patch(
        "telegram_auto_poster.web.app._schedule_post_at",
        new=mocker.AsyncMock(),
    )
    base_ts = parse_to_utc_timestamp("2024-01-01 12:00")
    resp = auth_client.post(
        "/batch/manual_schedule",
        data={
            "paths": [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"],
            "scheduled_at": "2024-01-01 12:00",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/batch"
    assert schedule.await_args_list == [
        call(f"{PHOTOS_PATH}/a.jpg", base_ts),
        call(f"{PHOTOS_PATH}/b.jpg", base_ts + 3600),
    ]


def test_manual_schedule_background_returns_json(mocker, auth_client: TestClient):
    schedule = mocker.patch(
        "telegram_auto_poster.web.app._schedule_post_at",
        new=mocker.AsyncMock(),
    )
    resp = auth_client.post(
        "/batch/manual_schedule",
        data={
            "paths": [f"{PHOTOS_PATH}/a.jpg"],
            "scheduled_at": "2024-01-01 12:00",
        },
        headers={"X-Background-Request": "true"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert schedule.await_args_list == [
        call(f"{PHOTOS_PATH}/a.jpg", parse_to_utc_timestamp("2024-01-01 12:00"))
    ]


def test_handle_action_push_single(mocker, auth_client: TestClient):
    push = mocker.patch(
        "telegram_auto_poster.web.app._push_post",
        new=mocker.AsyncMock(),
    )
    resp = auth_client.post(
        "/action",
        data={
            "path": f"{PHOTOS_PATH}/a.jpg",
            "action": "push",
            "origin": "suggestions",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/suggestions"
    push.assert_awaited_once_with(f"{PHOTOS_PATH}/a.jpg")


def test_handle_action_push_group(mocker, auth_client: TestClient):
    group = mocker.patch(
        "telegram_auto_poster.web.app._push_post_group",
        new=mocker.AsyncMock(),
    )
    data = {
        "paths": [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"],
        "action": "push",
        "origin": "posts",
    }
    resp = auth_client.post("/action", data=data, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/posts"
    group.assert_awaited_once_with(
        [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"]
    )


def test_handle_action_schedule(mocker, auth_client: TestClient):
    sched = mocker.patch(
        "telegram_auto_poster.web.app._schedule_post",
        new=mocker.AsyncMock(),
    )
    data = {
        "paths": [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"],
        "action": "schedule",
    }
    resp = auth_client.post("/action", data=data, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/suggestions"
    assert sched.await_args_list == [
        call(f"{PHOTOS_PATH}/a.jpg"),
        call(f"{PHOTOS_PATH}/b.jpg"),
    ]


def test_handle_action_notok_background(mocker, auth_client: TestClient):
    notok = mocker.patch(
        "telegram_auto_poster.web.app._notok_post",
        new=mocker.AsyncMock(),
    )
    resp = auth_client.post(
        "/action",
        data={"path": f"{PHOTOS_PATH}/a.jpg", "action": "notok"},
        headers={"X-Background-Request": "true"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    notok.assert_awaited_once_with(f"{PHOTOS_PATH}/a.jpg")


def test_unschedule_removes_and_redirects(mocker, auth_client: TestClient):
    run_tp = mocker.patch(
        "telegram_auto_poster.web.app.run_in_threadpool",
        new=mocker.AsyncMock(),
    )
    exists = mocker.patch(
        "telegram_auto_poster.web.app.storage.file_exists",
        new=mocker.AsyncMock(return_value=True),
    )
    delete = mocker.patch(
        "telegram_auto_poster.web.app.storage.delete_file",
        new=mocker.AsyncMock(),
    )
    resp = auth_client.post(
        "/queue/unschedule",
        data={"path": f"{PHOTOS_PATH}/a.jpg"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/queue"
    assert run_tp.awaited
    assert exists.await_args_list == [call(f"{PHOTOS_PATH}/a.jpg", BUCKET_MAIN)]
    assert delete.await_args_list == [call(f"{PHOTOS_PATH}/a.jpg", BUCKET_MAIN)]


def test_unschedule_background_returns_json(mocker, auth_client: TestClient):
    mocker.patch(
        "telegram_auto_poster.web.app.run_in_threadpool",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.web.app.storage.file_exists",
        new=mocker.AsyncMock(return_value=False),
    )
    delete = mocker.patch(
        "telegram_auto_poster.web.app.storage.delete_file",
        new=mocker.AsyncMock(),
    )
    resp = auth_client.post(
        "/queue/unschedule",
        data={"path": f"{PHOTOS_PATH}/a.jpg"},
        headers={"X-Background-Request": "true"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    delete.assert_not_called()

