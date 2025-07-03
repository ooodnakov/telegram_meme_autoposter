import sys
import asyncio
import importlib
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def setup_modules(monkeypatch):
    fake_config = ModuleType("telegram_auto_poster.config")
    fake_config.PHOTOS_BUCKET = "photos"
    fake_config.VIDEOS_BUCKET = "videos"
    fake_config.DOWNLOADS_BUCKET = "downloads"
    fake_config.LUBA_CHAT = "@luba"
    fake_config.load_config = lambda: {"target_channel": "@c"}
    monkeypatch.setitem(sys.modules, "telegram_auto_poster.config", fake_config)

    fake_storage = ModuleType("telegram_auto_poster.utils.storage")
    fake_storage.PHOTOS_BUCKET = "photos"
    fake_storage.VIDEOS_BUCKET = "videos"
    fake_storage.DOWNLOADS_BUCKET = "downloads"
    fake_storage.LUBA_CHAT = "@luba"

    class DummyStorage:
        def list_files(self, bucket, prefix=None):
            return []

        def delete_file(self, object_name, bucket):
            pass

        def file_exists(self, object_name, bucket):
            return False

        def get_submission_metadata(self, object_name):
            return None

        def mark_notified(self, object_name):
            pass

    fake_storage.storage = DummyStorage()
    monkeypatch.setitem(sys.modules, "telegram_auto_poster.utils.storage", fake_storage)

    fake_stats = ModuleType("telegram_auto_poster.utils.stats")
    fake_stats.stats = SimpleNamespace(record_error=lambda *a, **k: None, record_approved=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "telegram_auto_poster.utils.stats", fake_stats)

    from telegram_auto_poster.bot import handlers as handlers_module
    from telegram_auto_poster.bot import callbacks as callbacks_module

    handlers = importlib.reload(handlers_module)
    callbacks = importlib.reload(callbacks_module)

    return handlers, callbacks


@pytest.mark.asyncio
async def test_notify_user_success(monkeypatch):
    handlers, _ = setup_modules(monkeypatch)
    send = AsyncMock()
    context = SimpleNamespace(bot=SimpleNamespace(send_message=send))

    await handlers.notify_user(context, 123, "msg", reply_to_message_id=1)

    send.assert_awaited_once_with(chat_id=123, text="msg", reply_to_message_id=1)


@pytest.mark.asyncio
async def test_ok_callback_suggestion(monkeypatch, tmp_path):
    handlers, callbacks = setup_modules(monkeypatch)

    temp = tmp_path / "file.jpg"
    temp.write_bytes(b"d")

    monkeypatch.setattr(callbacks.storage, "file_exists", lambda name, bucket: True)

    async def fake_download(name, bucket):
        return str(temp), ".jpg"

    monkeypatch.setattr(callbacks, "download_from_minio", fake_download)
    monkeypatch.setattr(callbacks.storage, "delete_file", lambda *a, **k: None)
    monkeypatch.setattr(callbacks.storage, "mark_notified", lambda *a, **k: None)
    monkeypatch.setattr(callbacks.stats, "record_approved", lambda *a, **k: None)
    monkeypatch.setattr(callbacks.storage, "get_submission_metadata", lambda n: {"user_id": 5, "message_id": 10, "notified": False})

    notify_calls = []

    async def fake_notify(*args, **kwargs):
        notify_calls.append(kwargs)

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
    assert notify_calls
