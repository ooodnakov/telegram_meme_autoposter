from __future__ import annotations

from unittest.mock import call

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from telegram_auto_poster.config import PHOTOS_PATH, BUCKET_MAIN
from telegram_auto_poster.web.app import CONFIG, app


@pytest.fixture(autouse=True)
def clear_access_key():
    original = CONFIG.web.access_key
    CONFIG.web.access_key = None
    yield
    CONFIG.web.access_key = original


def test_suggestions_view_requires_access_key(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app._gather_posts",
        new=mocker.AsyncMock(return_value=[]),
    )
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        assert client.get("/suggestions").status_code == 401
        assert client.get("/suggestions?key=token").status_code == 200


def test_posts_view_requires_access_key(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app._gather_posts",
        new=mocker.AsyncMock(return_value=[]),
    )
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        assert client.get("/posts").status_code == 401
        assert client.get("/posts?key=token").status_code == 200


def test_batch_view_lists_posts(mocker):
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
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        assert client.get("/batch").status_code == 401
        resp = client.get("/batch?key=token")
        assert resp.status_code == 200
        assert "http://x" in resp.text


def test_send_batch_requires_access_key(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app._gather_batch",
        new=mocker.AsyncMock(return_value=[]),
    )
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        resp = client.post("/batch/send")
        assert resp.status_code == 401


def test_send_batch_processes_posts(mocker):
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
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        resp = client.post(
            "/batch/send?key=token",
            data={"key": "token"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/batch?key=token"
    assert push_group.await_args_list == [
        call([f"{PHOTOS_PATH}/batch_a.jpg"]),
        call([f"{PHOTOS_PATH}/batch_b.jpg"]),
    ]
    assert decr.await_args_list == [call(1), call(1)]
    assert rec.await_args_list == [call(1), call(1)]


def test_send_batch_redirects_when_empty(mocker):
    mocker.patch(
        "telegram_auto_poster.web.app._gather_batch",
        new=mocker.AsyncMock(return_value=[]),
    )
    CONFIG.web.access_key = SecretStr("token")
    with TestClient(app) as client:
        resp = client.post(
            "/batch/send?key=token",
            data={"key": "token"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/batch?key=token"


def test_handle_action_push_single(mocker):
    push = mocker.patch(
        "telegram_auto_poster.web.app._push_post",
        new=mocker.AsyncMock(),
    )
    with TestClient(app) as client:
        resp = client.post(
            "/action",
            data={
                "path": f"{PHOTOS_PATH}/a.jpg",
                "action": "push",
                "origin": "suggestions",
                "key": "token",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/suggestions?key=token"
    push.assert_awaited_once_with(f"{PHOTOS_PATH}/a.jpg")


def test_handle_action_push_group(mocker):
    group = mocker.patch(
        "telegram_auto_poster.web.app._push_post_group",
        new=mocker.AsyncMock(),
    )
    data = {
        "paths": [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"],
        "action": "push",
        "origin": "posts",
        "key": "token",
    }
    with TestClient(app) as client:
        resp = client.post("/action", data=data, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/posts?key=token"
    group.assert_awaited_once_with(
        [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"]
    )


def test_handle_action_schedule(mocker):
    sched = mocker.patch(
        "telegram_auto_poster.web.app._schedule_post",
        new=mocker.AsyncMock(),
    )
    data = {
        "paths": [f"{PHOTOS_PATH}/a.jpg", f"{PHOTOS_PATH}/b.jpg"],
        "action": "schedule",
        "key": "token",
    }
    with TestClient(app) as client:
        resp = client.post("/action", data=data, follow_redirects=False)
        assert resp.status_code == 303
    assert sched.await_args_list == [
        call(f"{PHOTOS_PATH}/a.jpg"),
        call(f"{PHOTOS_PATH}/b.jpg"),
    ]


def test_handle_action_notok_background(mocker):
    notok = mocker.patch(
        "telegram_auto_poster.web.app._notok_post",
        new=mocker.AsyncMock(),
    )
    with TestClient(app) as client:
        resp = client.post(
            "/action",
            data={"path": f"{PHOTOS_PATH}/a.jpg", "action": "notok"},
            headers={"X-Background-Request": "true"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
    notok.assert_awaited_once_with(f"{PHOTOS_PATH}/a.jpg")


def test_unschedule_removes_and_redirects(mocker):
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
    with TestClient(app) as client:
        resp = client.post(
            "/queue/unschedule",
            data={"path": f"{PHOTOS_PATH}/a.jpg", "key": "token"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/queue?key=token"
    assert run_tp.awaited
    assert exists.await_args_list == [call(f"{PHOTOS_PATH}/a.jpg", BUCKET_MAIN)]
    assert delete.await_args_list == [call(f"{PHOTOS_PATH}/a.jpg", BUCKET_MAIN)]


def test_unschedule_background_returns_json(mocker):
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
    with TestClient(app) as client:
        resp = client.post(
            "/queue/unschedule",
            data={"path": f"{PHOTOS_PATH}/a.jpg"},
            headers={"X-Background-Request": "true"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
    delete.assert_not_called()

