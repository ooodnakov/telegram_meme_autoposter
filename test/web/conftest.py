from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from telegram_auto_poster.web.app import CONFIG, app
from telegram_auto_poster.web.auth import sign_telegram_data


def login_payload(user_id: int) -> dict[str, int | str]:
    auth_date = int(time.time())
    data = {"id": user_id, "auth_date": auth_date}
    data["hash"] = sign_telegram_data(
        data, CONFIG.bot.bot_token.get_secret_value()
    )
    return data


@pytest.fixture()
def auth_client() -> TestClient:
    with TestClient(app) as client:
        payload = login_payload(CONFIG.bot.admin_ids[0])
        assert client.get("/auth", params=payload).status_code == 200
        yield client
