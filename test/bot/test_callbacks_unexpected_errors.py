from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from telegram_auto_poster.bot.callbacks import ok_callback, schedule_callback


@pytest.mark.asyncio
async def test_schedule_callback_hides_raw_exception_in_reply(mocker: MockerFixture):
    reply_text = mocker.AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    query = SimpleNamespace(
        message=message,
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"admin_ids": [1]}))

    mocker.patch(
        "telegram_auto_poster.bot.callbacks.extract_paths_from_message",
        return_value=["photos/test.jpg"],
    )
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.db.get_scheduled_posts",
        side_effect=RuntimeError("boom-secret"),
    )
    record_error = mocker.patch(
        "telegram_auto_poster.bot.callbacks.stats.record_error",
        new=mocker.AsyncMock(),
    )

    await schedule_callback(update, context)

    reply_text.assert_awaited_once_with(
        "Sorry, an unexpected error occurred. Please try again later."
    )
    assert "boom-secret" not in reply_text.await_args.args[0]
    record_error.assert_awaited_once_with(
        "processing", "Error in schedule_callback: boom-secret"
    )


@pytest.mark.asyncio
async def test_ok_callback_hides_raw_exception_in_reply(mocker: MockerFixture):
    reply_text = mocker.AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    query = SimpleNamespace(
        message=message,
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
        data="ok",
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(bot_data={"admin_ids": [1]})

    mocker.patch(
        "telegram_auto_poster.bot.callbacks.extract_paths_from_message",
        return_value=["photos/test.jpg"],
    )
    mocker.patch(
        "telegram_auto_poster.bot.callbacks.storage.file_exists",
        new=mocker.AsyncMock(side_effect=RuntimeError("token-leak")),
    )
    record_error = mocker.patch(
        "telegram_auto_poster.bot.callbacks.stats.record_error",
        new=mocker.AsyncMock(),
    )

    await ok_callback(update, context)

    reply_text.assert_awaited_once_with(
        "Sorry, an unexpected error occurred. Please try again later."
    )
    assert "token-leak" not in reply_text.await_args.args[0]
    record_error.assert_awaited_once_with("processing", "Error in ok_callback: token-leak")


@pytest.mark.asyncio
async def test_schedule_callback_rejects_non_admin(mocker: MockerFixture):
    reply_text = mocker.AsyncMock()
    query = SimpleNamespace(
        message=SimpleNamespace(reply_text=reply_text),
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=2),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=2),
    )
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"admin_ids": [1]}))

    await schedule_callback(update, context)

    query.answer.assert_awaited_once_with("У вас нет прав на это действие.", show_alert=True)
    reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_ok_callback_rejects_non_admin(mocker: MockerFixture):
    reply_text = mocker.AsyncMock()
    query = SimpleNamespace(
        message=SimpleNamespace(reply_text=reply_text),
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=2),
        data="ok",
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=2),
    )
    context = SimpleNamespace(bot_data={"admin_ids": [1]})

    await ok_callback(update, context)

    query.answer.assert_awaited_once_with("У вас нет прав на это действие.", show_alert=True)
    reply_text.assert_not_called()
