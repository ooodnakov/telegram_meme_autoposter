import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_notify_user_success(monkeypatch, setup_bot_modules):
    modules = setup_bot_modules()
    handlers = modules.handlers
    send = AsyncMock()
    context = SimpleNamespace(bot=SimpleNamespace(send_message=send))

    await handlers.notify_user(context, 123, "msg", reply_to_message_id=1)

    send.assert_awaited_once_with(chat_id=123, text="msg", reply_to_message_id=1)


@pytest.mark.asyncio
async def test_ok_callback_suggestion(monkeypatch, setup_bot_modules, tmp_path):
    modules = setup_bot_modules()
    callbacks = modules.callbacks

    temp = tmp_path / "file.jpg"
    temp.write_bytes(b"d")

    monkeypatch.setattr(callbacks.storage, "file_exists", lambda name, bucket: True)

    async def fake_download(name, bucket):
        return str(temp), ".jpg"

    monkeypatch.setattr(callbacks, "download_from_minio", fake_download)
    monkeypatch.setattr(callbacks.storage, "delete_file", lambda *a, **k: None)
    monkeypatch.setattr(callbacks.storage, "mark_notified", lambda *a, **k: None)
    monkeypatch.setattr(callbacks.stats, "record_approved", lambda *a, **k: None)
    monkeypatch.setattr(
        callbacks.storage,
        "get_submission_metadata",
        lambda n: {"user_id": 5, "message_id": 10, "notified": False},
    )

    notify_calls = []

    async def fake_notify(context, user_id, message, reply_to_message_id=None, media_type=None):
        notify_calls.append(
            {
                "user_id": user_id,
                "message": message,
                "reply_to_message_id": reply_to_message_id,
            }
        )

    monkeypatch.setattr(callbacks, "notify_user", fake_notify)

    bot = SimpleNamespace(send_photo=AsyncMock())
    query = SimpleNamespace(
        data="/ok",
        message=SimpleNamespace(
            caption="suggestion\nphotos/test.jpg",
            edit_caption=AsyncMock(),
        ),
        answer=AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=bot)

    await callbacks.ok_callback(update, context)

    bot.send_photo.assert_awaited_once()
    assert len(notify_calls) == 1
    assert notify_calls[0]["user_id"] == 5
    assert notify_calls[0]["reply_to_message_id"] == 10
    assert "одобрена и размещена" in notify_calls[0]["message"]
