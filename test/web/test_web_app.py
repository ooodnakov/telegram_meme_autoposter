import time

from fastapi.testclient import TestClient

from telegram_auto_poster.web.app import CONFIG, app
from telegram_auto_poster.web.auth import sign_telegram_data

from .conftest import login_payload


def test_api_requires_login():
    with TestClient(app) as client:
        resp = client.get("/api/session")
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}


def test_login_shell_is_public():
    with TestClient(app) as client:
        resp = client.get("/login")
        assert resp.status_code == 200
        assert 'id="root"' in resp.text


def test_auth_post_sets_session_cookie():
    with TestClient(app) as client:
        payload = login_payload(CONFIG.bot.admin_ids[0])
        resp = client.post("/auth", json=payload)
        assert resp.status_code == 200
        assert client.cookies.get("session") is not None


def test_auth_get_sets_session_cookie():
    with TestClient(app) as client:
        payload = login_payload(CONFIG.bot.admin_ids[0])
        resp = client.get("/auth", params=payload)
        assert resp.status_code == 200
        assert client.cookies.get("session") is not None


def test_login_rejects_non_admin():
    with TestClient(app) as client:
        payload = login_payload(999999)
        resp = client.post("/auth", json=payload)
        assert resp.status_code == 403


def test_login_rejects_stale_payload():
    with TestClient(app) as client:
        payload = login_payload(CONFIG.bot.admin_ids[0])
        payload["auth_date"] = int(time.time()) - 90000
        payload["hash"] = sign_telegram_data(
            {"id": payload["id"], "auth_date": payload["auth_date"]},
            CONFIG.bot.bot_token.get_secret_value(),
        )
        resp = client.post("/auth", json=payload)
        assert resp.status_code == 400


def test_dashboard_shell_requires_login_redirect():
    with TestClient(app) as client:
        resp = client.get("/queue", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"


def test_authenticated_shell_route_serves_spa(auth_client: TestClient):
    resp = auth_client.get("/queue")
    assert resp.status_code == 200
    assert 'id="root"' in resp.text


def test_api_session_returns_authenticated_payload(auth_client: TestClient):
    resp = auth_client.get("/api/session")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["user_id"] == CONFIG.bot.admin_ids[0]
    assert "languages" in payload
    assert payload["bot_username"] == CONFIG.bot.bot_username


def test_api_language_updates_session(auth_client: TestClient):
    resp = auth_client.post("/api/session/language", json={"language": "en"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "language": "en"}

    resp = auth_client.get("/api/session")
    assert resp.status_code == 200
    assert resp.json()["language"] == "en"


def test_api_channel_settings_returns_live_and_default_values(auth_client: TestClient):
    resp = auth_client.get("/api/settings/channels")

    assert resp.status_code == 200
    assert resp.json() == {
        "selected_chats": ["@test1", "@test2"],
        "default_selected_chats": ["@test1", "@test2"],
        "valkey_key": "telegram_auto_poster:config:selected_chats",
    }


def test_api_channel_settings_update_persists_value(auth_client: TestClient):
    resp = auth_client.post(
        "/api/settings/channels",
        json={"selected_chats": ["@source_one", "-1001234567890", "@source_one"]},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "selected_chats": ["@source_one", "-1001234567890"],
        "default_selected_chats": ["@test1", "@test2"],
        "valkey_key": "telegram_auto_poster:config:selected_chats",
    }
