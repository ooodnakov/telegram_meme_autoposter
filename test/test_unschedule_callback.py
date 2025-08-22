import pytest
from types import SimpleNamespace
from pytest_mock import MockerFixture

from telegram_auto_poster.bot.callbacks import unschedule_callback


@pytest.mark.asyncio
async def test_unschedule_callback_invalid_data(mocker: MockerFixture):
    message = SimpleNamespace(reply_text=mocker.AsyncMock())
    query = SimpleNamespace(
        data="/unschedule:abc",
        message=message,
        answer=mocker.AsyncMock(),
        from_user=SimpleNamespace(id=1),
    )
    update = SimpleNamespace(callback_query=query)

    await unschedule_callback(update, SimpleNamespace())

    message.reply_text.assert_awaited_once_with("Invalid request")

