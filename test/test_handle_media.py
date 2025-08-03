import sys
import types
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import os

from telegram_auto_poster.config import BUCKET_MAIN

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Create dummy stats module before importing handlers
fake_stats = types.SimpleNamespace(stats=MagicMock())
# Provide minimal interface for record_error
fake_stats.stats.record_error = MagicMock()
fake_stats.stats.record_received = MagicMock()
sys.modules["telegram_auto_poster.utils.stats"] = fake_stats

# Create dummy storage module required by utils
fake_storage = types.SimpleNamespace(
    DOWNLOADS_PATH="downloads",
    PHOTOS_PATH="photos",
    VIDEOS_PATH="videos",
    BUCKET_MAIN="telegram-auto-poster",
    storage=MagicMock(),
)
sys.modules["telegram_auto_poster.utils.storage"] = fake_storage

# Provide dummy config module
fake_config = types.SimpleNamespace(
    load_config=lambda: {
        "target_channel": "@dummy",
    }
)
sys.modules["telegram_auto_poster.config"] = fake_config

# Now import handlers (will import utils which uses our fake modules)
from telegram_auto_poster.bot import handlers  # noqa: E402


# Utility to create fake update object
class DummyMessage:
    def __init__(self, photo=None, video=None):
        self.photo = photo
        self.video = video
        self.reply_text = AsyncMock()


class DummyChat:
    def __init__(self, chat_id):
        self.id = chat_id


class DummyUpdate:
    def __init__(self, chat_id, message):
        self.effective_chat = DummyChat(chat_id)
        self.message = message


def run(coro):
    return asyncio.run(coro)


def test_handle_media_photo():
    update = DummyUpdate(1, DummyMessage(photo=[object()]))
    context = MagicMock()
    with patch.object(handlers, "handle_photo", new=AsyncMock()) as hp:
        run(handlers.handle_media(update, context))
        hp.assert_awaited_once_with(update, context, 1)
    update.message.reply_text.assert_not_called()


def test_handle_media_video():
    update = DummyUpdate(2, DummyMessage(video=object()))
    context = MagicMock()
    with patch.object(handlers, "handle_video", new=AsyncMock()) as hv:
        run(handlers.handle_media(update, context))
        hv.assert_awaited_once_with(update, context, 2)
    update.message.reply_text.assert_not_called()


def test_handle_media_exception():
    update = DummyUpdate(3, DummyMessage(photo=[object()]))
    context = MagicMock()
    with patch.object(
        handlers, "handle_photo", new=AsyncMock(side_effect=Exception("boom"))
    ):
        run(handlers.handle_media(update, context))
    update.message.reply_text.assert_awaited_once()
