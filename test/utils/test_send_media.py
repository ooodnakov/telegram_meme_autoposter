import asyncio
import os
from unittest.mock import call

import pytest
from telegram.error import TimedOut

from telegram_auto_poster.utils.general import (
    TelegramMediaError,
    send_media_to_telegram,
)


@pytest.fixture
def bot(mocker):
    return mocker.Mock(
        send_photo=mocker.AsyncMock(),
        send_video=mocker.AsyncMock(),
        send_animation=mocker.AsyncMock(),
        send_document=mocker.AsyncMock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,method",
    [
        ("test.jpg", "send_photo"),
        ("test.mp4", "send_video"),
        ("test.gif", "send_animation"),
    ],
)
async def test_send_media_supported_types(tmp_path, bot, mocker, name, method):
    file_path = tmp_path / name
    file_path.write_bytes(b"data")
    record_error = mocker.patch(
        "telegram_auto_poster.utils.general.stats.record_error",
        new=mocker.AsyncMock(),
    )

    await send_media_to_telegram(bot, 123, str(file_path))

    getattr(bot, method).assert_awaited_once()
    bot.send_document.assert_not_called()
    record_error.assert_not_called()


@pytest.mark.asyncio
async def test_send_media_unsupported_falls_back_to_document(tmp_path, bot, mocker):
    file_path = tmp_path / "file.xyz"
    file_path.write_bytes(b"data")
    record_error = mocker.patch(
        "telegram_auto_poster.utils.general.stats.record_error",
        new=mocker.AsyncMock(),
    )

    await send_media_to_telegram(bot, 123, str(file_path))

    bot.send_document.assert_awaited_once()
    record_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_media_retries_on_network_error(tmp_path, bot, mocker):
    file_path = tmp_path / "img.jpg"
    file_path.write_bytes(b"data")

    bot.send_photo.side_effect = TimedOut()
    record_error = mocker.patch(
        "telegram_auto_poster.utils.general.stats.record_error",
        new=mocker.AsyncMock(),
    )
    sleep = mocker.patch(
        "telegram_auto_poster.utils.general.asyncio.sleep",
        new=mocker.AsyncMock(),
    )

    with pytest.raises(TelegramMediaError):
        await send_media_to_telegram(bot, 123, str(file_path))

    assert bot.send_photo.await_count == 3
    assert sleep.await_args_list == [call(2), call(4), call(8)]
    assert record_error.await_count == 4


@pytest.mark.asyncio
async def test_send_media_missing_file_logs_and_raises(bot, tmp_path, mocker):
    missing = tmp_path / "missing.jpg"
    record_error = mocker.patch(
        "telegram_auto_poster.utils.general.stats.record_error",
        new=mocker.AsyncMock(),
    )

    with pytest.raises(FileNotFoundError):
        await send_media_to_telegram(bot, 123, str(missing))

    record_error.assert_awaited_once_with(
        "telegram", f"File {missing} does not exist"
    )
