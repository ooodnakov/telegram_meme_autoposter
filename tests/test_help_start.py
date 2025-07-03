import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_auto_poster.bot import commands


@pytest.mark.asyncio
async def test_start_command_sends_welcome():
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=1))
    context = SimpleNamespace()

    await commands.start_command(update, context)

    message.reply_text.assert_awaited_once_with("Привет! Присылай сюда свои мемы)")


@pytest.mark.asyncio
async def test_help_command_for_user():
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=2), message=message)
    context = SimpleNamespace(bot_data={"admin_ids": [1]})

    await commands.help_command(update, context)

    sent = message.reply_text.call_args.args[0]
    assert "Команды администратора" not in sent


@pytest.mark.asyncio
async def test_help_command_for_admin():
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=message)
    context = SimpleNamespace(bot_data={"admin_ids": [1]})

    await commands.help_command(update, context)

    sent = message.reply_text.call_args.args[0]
    assert "Команды администратора" in sent
