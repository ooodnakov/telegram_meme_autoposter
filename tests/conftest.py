import sys
import importlib
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def setup_bot_modules(monkeypatch):
    def factory(config_override=None):
        fake_config = ModuleType("telegram_auto_poster.config")
        conf = {
            "bot_token": "t",
            "bot_chat_id": "1",
            "target_channel": "@c",
            "admin_ids": [1],
        }
        if config_override:
            conf.update(config_override)
        fake_config.load_config = lambda: conf
        fake_config.PHOTOS_BUCKET = "photos"
        fake_config.VIDEOS_BUCKET = "videos"
        fake_config.DOWNLOADS_BUCKET = "downloads"
        fake_config.LUBA_CHAT = "@luba"
        monkeypatch.setitem(sys.modules, "telegram_auto_poster.config", fake_config)

        fake_stats = ModuleType("telegram_auto_poster.utils.stats")
        fake_stats.stats = SimpleNamespace(
            record_error=lambda *a, **k: None,
            record_approved=lambda *a, **k: None,
        )
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
        fake_storage.PHOTOS_BUCKET = "photos"
        fake_storage.VIDEOS_BUCKET = "videos"
        fake_storage.DOWNLOADS_BUCKET = "downloads"
        fake_storage.LUBA_CHAT = "@luba"
        monkeypatch.setitem(sys.modules, "telegram_auto_poster.utils.storage", fake_storage)

        handlers_module = importlib.import_module("telegram_auto_poster.bot.handlers")
        callbacks_module = importlib.import_module("telegram_auto_poster.bot.callbacks")
        bot_module = importlib.import_module("telegram_auto_poster.bot.bot")
        handlers = importlib.reload(handlers_module)
        callbacks = importlib.reload(callbacks_module)
        bot_module = importlib.reload(bot_module)

        return SimpleNamespace(bot=bot_module, handlers=handlers, callbacks=callbacks)

    return factory
