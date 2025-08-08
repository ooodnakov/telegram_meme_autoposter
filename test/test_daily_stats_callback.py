from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from telegram_auto_poster.bot import commands


@pytest.mark.asyncio
async def test_daily_stats_callback_sends_report(monkeypatch):
    report_text = "report"
    gen_stats_mock = MagicMock(return_value=report_text)
    monkeypatch.setattr(commands.stats, "generate_stats_report", gen_stats_mock)
    reset_mock = MagicMock()
    monkeypatch.setattr(commands.stats, "reset_daily_stats", reset_mock)
    bot = SimpleNamespace(send_message=AsyncMock())
    context = SimpleNamespace(
        bot=bot,
        job=SimpleNamespace(chat_id=123),
        application=SimpleNamespace(bot_data={}),
    )
    await commands.daily_stats_callback(context)
    bot.send_message.assert_awaited_once_with(chat_id=123, text=report_text)
    gen_stats_mock.assert_called_once_with(reset_daily=False)
    reset_mock.assert_called_once()

