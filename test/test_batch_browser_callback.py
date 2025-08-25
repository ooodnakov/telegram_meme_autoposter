import pytest
from pytest_mock import MockerFixture

from types import SimpleNamespace

from telegram_auto_poster.bot import callbacks
from telegram_auto_poster.bot.callbacks import batch_browser_callback


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,expected_path,expected_idx",
    [
        ("/batch_prev:0", "p3", 2),
        ("/batch_next:2", "p1", 0),
    ],
)
async def test_batch_browser_navigation_wraps(
    mocker: MockerFixture, data, expected_path, expected_idx
):
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.list_batch_files",
        new=mocker.AsyncMock(return_value=["p1", "p2", "p3"]),
    )
    preview = mocker.patch(
        "telegram_auto_poster.bot.callbacks.send_batch_preview",
        new=mocker.AsyncMock(),
    )
    message = SimpleNamespace(
        chat_id=1, delete=mocker.AsyncMock(), edit_text=mocker.AsyncMock()
    )
    query = SimpleNamespace(
        data=data,
        message=message,
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=SimpleNamespace())

    await batch_browser_callback(update, context)

    preview.assert_awaited_once_with(context.bot, 1, expected_path, expected_idx)


@pytest.mark.asyncio
async def test_batch_browser_remove_shows_next(mocker: MockerFixture):
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.list_batch_files",
        side_effect=[["p1", "p2", "p3"], ["p1", "p3"]],
    )
    delete = mocker.patch(
        "telegram_auto_poster.bot.callbacks.storage.delete_file",
        new=mocker.AsyncMock(),
    )
    dec = mocker.patch(
        "telegram_auto_poster.bot.callbacks.db.decrement_batch_count",
        new=mocker.AsyncMock(),
    )
    preview = mocker.patch(
        "telegram_auto_poster.bot.callbacks.send_batch_preview",
        new=mocker.AsyncMock(),
    )
    message = SimpleNamespace(
        chat_id=1, delete=mocker.AsyncMock(), edit_text=mocker.AsyncMock()
    )
    query = SimpleNamespace(
        data="/batch_remove:1",
        message=message,
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=SimpleNamespace())

    await batch_browser_callback(update, context)

    delete.assert_awaited_once_with("p2", callbacks.BUCKET_MAIN)
    dec.assert_awaited_once_with(1)
    preview.assert_awaited_once_with(context.bot, 1, "p3", 1)


@pytest.mark.asyncio
async def test_batch_browser_push_sends_and_shows_next(mocker: MockerFixture):
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.list_batch_files",
        side_effect=[["p2.mp4", "p1.mp4"], ["p1.mp4"]],
    )
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.storage.delete_file",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.db.decrement_batch_count",
        new=mocker.AsyncMock(),
    )
    preview = mocker.patch(
        "telegram_auto_poster.bot.callbacks.send_batch_preview",
        new=mocker.AsyncMock(),
    )
    download = mocker.patch(
        "telegram_auto_poster.bot.callbacks.download_from_minio",
        new=mocker.AsyncMock(return_value=("/tmp/t.mp4", None)),
    )
    send_media = mocker.patch(
        "telegram_auto_poster.bot.callbacks.send_media_to_telegram",
        new=mocker.AsyncMock(),
    )
    mocker.patch("telegram_auto_poster.bot.callbacks.cleanup_temp_file")

    message = SimpleNamespace(
        chat_id=1, delete=mocker.AsyncMock(), edit_text=mocker.AsyncMock()
    )
    query = SimpleNamespace(
        data="/batch_push:0",
        message=message,
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=SimpleNamespace(), bot_data={"target_channel_id": 99})

    await batch_browser_callback(update, context)

    download.assert_awaited_once()
    send_media.assert_awaited_once_with(
        context.bot, 99, "/tmp/t.mp4", caption=None, supports_streaming=True
    )
    preview.assert_awaited_once_with(context.bot, 1, "p1.mp4", 0)
