import sys
import types
import asyncio
import importlib
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def setup_modules(monkeypatch):
    fake_config = ModuleType("telegram_auto_poster.config")
    fake_config.load_config = lambda: {
        "bot_token": "t",
        "bot_chat_id": "1",
        "target_channel": "@c",
        "admin_ids": [1],
    }
    fake_config.PHOTOS_BUCKET = "photos"
    fake_config.VIDEOS_BUCKET = "videos"
    fake_config.DOWNLOADS_BUCKET = "downloads"
    fake_config.LUBA_CHAT = "@luba"
    monkeypatch.setitem(sys.modules, "telegram_auto_poster.config", fake_config)

    fake_stats = ModuleType("telegram_auto_poster.utils.stats")
    fake_stats.stats = SimpleNamespace(record_error=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "telegram_auto_poster.utils.stats", fake_stats)

    fake_storage = ModuleType("telegram_auto_poster.utils.storage")

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

    from telegram_auto_poster.bot import bot as bot_module

    bot_module = importlib.reload(bot_module)

    return bot_module


class DummyApp:
    def __init__(self):
        self.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(first_name="t", username="t")))
        self.bot_data = {}
        self.handlers = []
        self.updater = SimpleNamespace()

    def add_handler(self, handler, *a, **k):
        self.handlers.append(handler)

    async def initialize(self):
        pass


class DummyBuilder:
    def token(self, _):
        return self

    def build(self):
        return DummyApp()


def test_setup(monkeypatch):
    bot_module = setup_modules(monkeypatch)

    monkeypatch.setattr(bot_module, "ApplicationBuilder", DummyBuilder)
    monkeypatch.setattr(
        bot_module,
        "load_config",
        lambda: {
            "bot_token": "t",
            "bot_chat_id": "1",
            "target_channel": "@c",
            "admin_ids": [1],
        },
    )

    tb = bot_module.TelegramMemeBot()
    app = asyncio.run(tb.setup())

    assert app.bot_data["chat_id"] == "1"
    assert app.bot_data["target_channel_id"] == "@c"
    assert app.bot_data["admin_ids"] == [1]
