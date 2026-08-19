from types import SimpleNamespace

import pytest

from telegram_auto_poster.bot.callbacks import comment_callback
from telegram_auto_poster.utils.ui import CALLBACK_COMMENT, approval_keyboard


@pytest.mark.asyncio
async def test_comment_callback_toggles_keyboard_off(mocker):
    message = SimpleNamespace(reply_markup=approval_keyboard())
    query = SimpleNamespace(
        message=message,
        data=f"{CALLBACK_COMMENT}:1",
        answer=mocker.AsyncMock(),
        edit_message_reply_markup=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=1),
    )
    context = SimpleNamespace(
        bot_data={"admin_ids": [1], "target_channel_ids": ["@test"]}
    )

    await comment_callback(update, context)

    query.answer.assert_awaited_once_with()
    query.edit_message_reply_markup.assert_awaited_once()
    markup = query.edit_message_reply_markup.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[-1][0].callback_data == f"{CALLBACK_COMMENT}:0"
    assert markup.inline_keyboard[-1][0].text == "comment ✖️"


@pytest.mark.asyncio
async def test_comment_callback_rejects_non_admin(mocker):
    query = SimpleNamespace(
        message=SimpleNamespace(reply_markup=approval_keyboard()),
        data=f"{CALLBACK_COMMENT}:1",
        answer=mocker.AsyncMock(),
        edit_message_reply_markup=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=2),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=2),
    )
    context = SimpleNamespace(bot_data={"admin_ids": [1]})

    await comment_callback(update, context)

    query.answer.assert_awaited_once_with(
        "У вас нет прав на это действие.", show_alert=True
    )
    query.edit_message_reply_markup.assert_not_awaited()
