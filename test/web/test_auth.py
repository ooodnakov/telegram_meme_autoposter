from __future__ import annotations

from telegram_auto_poster.web.auth import sign_telegram_data, validate_telegram_login


BOT_TOKEN = "123456:ABCDEF_test_token"


def _signed_payload(auth_date: int) -> dict[str, int | str]:
    payload: dict[str, int | str] = {"id": 123, "auth_date": auth_date}
    payload["hash"] = sign_telegram_data(payload, BOT_TOKEN)
    return payload


def test_validate_telegram_login_accepts_current_payload(monkeypatch):
    now = 1_700_000_000
    monkeypatch.setattr("telegram_auto_poster.web.auth.time.time", lambda: now)

    payload = _signed_payload(now)

    assert validate_telegram_login(payload, BOT_TOKEN)


def test_validate_telegram_login_rejects_stale_payload(monkeypatch):
    now = 1_700_000_000
    monkeypatch.setattr("telegram_auto_poster.web.auth.time.time", lambda: now)

    payload = _signed_payload(now - 86_401)

    assert not validate_telegram_login(payload, BOT_TOKEN)


def test_validate_telegram_login_rejects_far_future_payload(monkeypatch):
    now = 1_700_000_000
    monkeypatch.setattr("telegram_auto_poster.web.auth.time.time", lambda: now)

    payload = _signed_payload(now + 121)

    assert not validate_telegram_login(payload, BOT_TOKEN, allowed_clock_skew=120)
