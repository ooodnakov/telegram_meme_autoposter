from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

dummy_stats_module = ModuleType("telegram_auto_poster.utils.stats")
dummy_stats_module.stats = SimpleNamespace(
    record_approved=lambda *a, **k: None,
    record_error=lambda *a, **k: None,
    record_batch_sent=lambda *a, **k: None,
    generate_stats_report=lambda: "",
    reset_daily_stats=lambda: "",
    force_save=lambda: None,
)
sys.modules["telegram_auto_poster.utils.stats"] = dummy_stats_module

dummy_storage_module = ModuleType("telegram_auto_poster.utils.storage")

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

dummy_storage_module.storage = DummyStorage()
sys.modules["telegram_auto_poster.utils.storage"] = dummy_storage_module

dummy_config_module = ModuleType("telegram_auto_poster.config")
dummy_config_module.PHOTOS_BUCKET = "photos"
dummy_config_module.VIDEOS_BUCKET = "videos"
dummy_config_module.DOWNLOADS_BUCKET = "downloads"
dummy_config_module.LUBA_CHAT = "@luba"
dummy_config_module.load_config = lambda: {}
sys.modules["telegram_auto_poster.config"] = dummy_config_module

import pytest
import importlib

from telegram_auto_poster.bot import commands as imported_commands

commands = importlib.reload(imported_commands)


@pytest.mark.asyncio
async def test_send_batch_photo_closes_file_and_cleans(tmp_path, monkeypatch):
    temp_file = tmp_path / "photo.jpg"
    temp_file.write_bytes(b"data")

    async def mock_download(name, bucket, ext):
        return str(temp_file), ext

    monkeypatch.setattr(commands, "download_from_minio", mock_download)
    monkeypatch.setattr(commands.storage, "get_submission_metadata", lambda name: None)
    monkeypatch.setattr(commands.storage, "mark_notified", lambda name: None)
    monkeypatch.setattr(commands.stats, "record_approved", lambda *a, **k: None)

    monkeypatch.setattr(commands, "check_admin_rights", AsyncMock(return_value=True))
    cleaned = {}

    def mock_cleanup(path):
        cleaned["path"] = path

    monkeypatch.setattr(commands, "cleanup_temp_file", mock_cleanup)

    update = SimpleNamespace(
        message=SimpleNamespace(reply_text=AsyncMock()),
        effective_message=SimpleNamespace(message_id=1),
    )
    bot = SimpleNamespace(send_photo=AsyncMock(), send_video=AsyncMock())
    context = SimpleNamespace(
        bot=bot,
        bot_data={"target_channel_id": 123, "photo_batch": ["file"], "video_batch": []},
    )

    await commands.send_batch_command(update, context)

    bot.send_photo.assert_awaited_once()
    sent_args = bot.send_photo.call_args.kwargs
    assert sent_args["chat_id"] == 123
    file_obj = sent_args["photo"]
    assert file_obj.closed
    assert cleaned["path"] == str(temp_file)
    assert context.bot_data["photo_batch"] == []


@pytest.mark.asyncio
async def test_send_batch_video_closes_file_and_cleans(tmp_path, monkeypatch):
    temp_file = tmp_path / "video.mp4"
    temp_file.write_bytes(b"data")

    async def mock_download(name, bucket, ext):
        return str(temp_file), ext

    monkeypatch.setattr(commands, "download_from_minio", mock_download)
    monkeypatch.setattr(commands.storage, "get_submission_metadata", lambda name: None)
    monkeypatch.setattr(commands.storage, "mark_notified", lambda name: None)
    monkeypatch.setattr(commands.stats, "record_approved", lambda *a, **k: None)
    monkeypatch.setattr(commands, "check_admin_rights", AsyncMock(return_value=True))

    cleaned = {}

    def mock_cleanup(path):
        cleaned["path"] = path

    monkeypatch.setattr(commands, "cleanup_temp_file", mock_cleanup)

    update = SimpleNamespace(
        message=SimpleNamespace(reply_text=AsyncMock()),
        effective_message=SimpleNamespace(message_id=1),
    )
    bot = SimpleNamespace(send_photo=AsyncMock(), send_video=AsyncMock())
    context = SimpleNamespace(
        bot=bot,
        bot_data={"target_channel_id": 123, "photo_batch": [], "video_batch": ["file"]},
    )

    await commands.send_batch_command(update, context)

    bot.send_video.assert_awaited_once()
    sent_args = bot.send_video.call_args.kwargs
    assert sent_args["chat_id"] == 123
    file_obj = sent_args["video"]
    assert file_obj.closed
    assert cleaned["path"] == str(temp_file)
    assert context.bot_data["video_batch"] == []
