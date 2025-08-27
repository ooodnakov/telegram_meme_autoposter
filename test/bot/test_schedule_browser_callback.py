from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture
from telegram_auto_poster.bot.callbacks import schedule_browser_callback


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,expected_path,expected_idx",
    [
        ("/sch_prev:0", "p3", 2),
        ("/sch_next:2", "p1", 0),
    ],
)
async def test_schedule_browser_navigation_wraps(
    mocker: MockerFixture, data, expected_path, expected_idx
):
    scheduled = [("p1", 0), ("p2", 0), ("p3", 0)]
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.db.get_scheduled_posts",
        return_value=scheduled,
    )
    preview = mocker.patch(
        "telegram_auto_poster.bot.callbacks.send_schedule_preview",
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

    await schedule_browser_callback(update, context)

    preview.assert_awaited_once_with(context.bot, 1, expected_path, expected_idx)


@pytest.mark.asyncio
async def test_schedule_browser_unschedule_removes_and_shows_next(
    mocker: MockerFixture,
):
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.db.get_scheduled_posts",
        side_effect=[[("p1", 0), ("p2", 0), ("p3", 0)], [("p1", 0), ("p3", 0)]],
    )
    remove = mocker.patch("telegram_auto_poster.bot.callbacks.db.remove_scheduled_post")
    exists = mocker.patch(
        "telegram_auto_poster.bot.callbacks.storage.file_exists",
        new=mocker.AsyncMock(return_value=True),
    )
    delete = mocker.patch(
        "telegram_auto_poster.bot.callbacks.storage.delete_file",
        new=mocker.AsyncMock(),
    )
    preview = mocker.patch(
        "telegram_auto_poster.bot.callbacks.send_schedule_preview",
        new=mocker.AsyncMock(),
    )
    message = SimpleNamespace(
        chat_id=1, delete=mocker.AsyncMock(), edit_text=mocker.AsyncMock()
    )
    query = SimpleNamespace(
        data="/sch_unschedule:1",
        message=message,
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=SimpleNamespace())

    await schedule_browser_callback(update, context)

    remove.assert_called_once_with("p2")
    exists.assert_awaited_once()
    delete.assert_awaited_once()
    preview.assert_awaited_once_with(context.bot, 1, "p3", 1)


@pytest.mark.asyncio
async def test_schedule_browser_push_sends_and_shows_next(mocker: MockerFixture):
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.db.get_scheduled_posts",
        side_effect=[[("p2.mp4", 0), ("p1.mp4", 0)], [("p1.mp4", 0)]],
    )
    mocker.patch("telegram_auto_poster.bot.callbacks.db.remove_scheduled_post")
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.storage.file_exists",
        new=mocker.AsyncMock(return_value=False),
    )
    preview = mocker.patch(
        "telegram_auto_poster.bot.callbacks.send_schedule_preview",
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
        data="/sch_push:0",
        message=message,
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=SimpleNamespace(), bot_data={"target_channel_id": 99})

    await schedule_browser_callback(update, context)

    download.assert_awaited_once()
    send_media.assert_awaited_once_with(
        context.bot, 99, "/tmp/t.mp4", caption=None, supports_streaming=True
    )
    preview.assert_awaited_once_with(context.bot, 1, "p1.mp4", 0)


@pytest.mark.asyncio
async def test_schedule_browser_unschedule_last_shows_none(mocker: MockerFixture):
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.db.get_scheduled_posts",
        side_effect=[[("p1", 0)], []],
    )
    mocker.patch("telegram_auto_poster.bot.callbacks.db.remove_scheduled_post")
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.storage.file_exists",
        new=mocker.AsyncMock(return_value=False),
    )
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.storage.delete_file",
        new=mocker.AsyncMock(),
    )
    preview = mocker.patch(
        "telegram_auto_poster.bot.callbacks.send_schedule_preview",
        new=mocker.AsyncMock(),
    )
    message = SimpleNamespace(
        chat_id=1, delete=mocker.AsyncMock(), edit_text=mocker.AsyncMock()
    )
    query = SimpleNamespace(
        data="/sch_unschedule:0",
        message=message,
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=SimpleNamespace())

    await schedule_browser_callback(update, context)

    message.edit_text.assert_awaited_once_with("No posts scheduled.")
    assert preview.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    ["/sch_prev:abc", "/sch_unschedule:abc", "/sch_push:abc"],
)
async def test_schedule_browser_invalid_index(mocker: MockerFixture, data):
    message = SimpleNamespace(
        reply_text=mocker.AsyncMock(),
        edit_text=mocker.AsyncMock(),
        delete=mocker.AsyncMock(),
    )
    query = SimpleNamespace(
        data=data,
        message=message,
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=SimpleNamespace(), bot_data={})

    await schedule_browser_callback(update, context)

    message.reply_text.assert_awaited_once_with("Invalid request")
