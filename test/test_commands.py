import asyncio
from types import SimpleNamespace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Подменяем модули, которые при импорте пытаются подключиться к внешним
# сервисам (база данных и MinIO).
dummy_stats_module = SimpleNamespace(stats=SimpleNamespace())
dummy_storage = SimpleNamespace()
dummy_storage.list_files = lambda bucket: []
dummy_storage_module = SimpleNamespace(storage=dummy_storage)
sys.modules.setdefault('telegram_auto_poster.utils.stats', dummy_stats_module)
sys.modules.setdefault('telegram_auto_poster.utils.storage', dummy_storage_module)

from telegram_auto_poster.bot.commands import send_luba_command


class DummyMessage:
    def __init__(self):
        self.texts = []

    async def reply_text(self, text):
        self.texts.append(text)


class DummyUpdate:
    def __init__(self, user_id=1):
        self.effective_user = SimpleNamespace(id=user_id)
        self.message = DummyMessage()
        self.effective_message = self.message


class DummyContext:
    def __init__(self):
        self.bot = object()
        self.bot_data = {}


@pytest.mark.asyncio
async def test_send_luba_command_sends_media(monkeypatch):
    update = DummyUpdate()
    context = DummyContext()

    # Prepare mocks
    monkeypatch.setattr(
        'telegram_auto_poster.bot.commands.check_admin_rights',
        lambda u, c: asyncio.Future()
    )
    check_future = asyncio.Future()
    check_future.set_result(True)
    monkeypatch.setattr(
        'telegram_auto_poster.bot.commands.check_admin_rights',
        lambda u, c: check_future,
    )

    monkeypatch.setattr(
        'telegram_auto_poster.bot.commands.storage.list_files',
        lambda bucket: ['a.jpg', 'b.mp4'],
    )

    async def fake_download(name, bucket):
        ext = '.mp4' if name.endswith('.mp4') else '.jpg'
        return f'/tmp/{name}', ext

    monkeypatch.setattr(
        'telegram_auto_poster.bot.commands.download_from_minio',
        fake_download,
    )

    send_calls = []

    async def fake_send(bot, chat_id, file_path, caption=None, supports_streaming=True):
        send_calls.append((bot, chat_id, file_path, caption, supports_streaming))

    monkeypatch.setattr(
        'telegram_auto_poster.bot.commands.send_media_to_telegram',
        fake_send,
    )

    monkeypatch.setattr('telegram_auto_poster.bot.commands.cleanup_temp_file', lambda p: None)
    monkeypatch.setattr('telegram_auto_poster.bot.commands.asyncio.sleep', lambda s: asyncio.Future())
    sleep_future = asyncio.Future()
    sleep_future.set_result(None)
    monkeypatch.setattr(
        'telegram_auto_poster.bot.commands.asyncio.sleep',
        lambda s: sleep_future,
    )

    await send_luba_command(update, context)

    assert len(send_calls) == 2
    assert send_calls[0][4] is False
    assert send_calls[1][4] is True
    assert update.message.texts[-1].startswith('Sent 2 files')


@pytest.mark.asyncio
async def test_send_luba_command_no_files(monkeypatch):
    update = DummyUpdate()
    context = DummyContext()

    future = asyncio.Future()
    future.set_result(True)
    monkeypatch.setattr(
        'telegram_auto_poster.bot.commands.check_admin_rights',
        lambda u, c: future,
    )

    monkeypatch.setattr(
        'telegram_auto_poster.bot.commands.storage.list_files',
        lambda bucket: [],
    )

    await send_luba_command(update, context)

    assert update.message.texts[-1] == 'No files to send to Luba.'
