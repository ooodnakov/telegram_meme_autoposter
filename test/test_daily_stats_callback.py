from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_auto_poster.bot import commands


@pytest.mark.asyncio
async def test_daily_stats_callback_sends_report(mocker):
    report_text = "report"
    gen_stats_mock = mocker.patch.object(
        commands.stats, "generate_stats_report", return_value=report_text
    )
    reset_mock = mocker.patch.object(commands.stats, "reset_daily_stats")
    bot = SimpleNamespace(send_message=AsyncMock())
    context = SimpleNamespace(
        bot=bot,
        job=SimpleNamespace(chat_id=123),
        application=SimpleNamespace(bot_data={}),
    )
    await commands.daily_stats_callback(context)
    bot.send_message.assert_awaited_once_with(
        chat_id=123, text=report_text, parse_mode="HTML"
    )
    gen_stats_mock.assert_called_once_with(reset_daily=False)
    reset_mock.assert_called_once()
