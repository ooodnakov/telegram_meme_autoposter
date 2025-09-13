from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture
from telegram_auto_poster.bot.permissions import check_admin_rights
from telegram_auto_poster.config import (
    BotConfig,
    ChatsConfig,
    Config,
    TelegramConfig,
)


@pytest.fixture
def mock_update(mocker: MockerFixture):
    """Fixture to create a mock update object."""
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=SimpleNamespace(reply_text=mocker.AsyncMock()),
    )
    return update


@pytest.mark.asyncio
async def test_check_admin_rights_bot_data(mocker, mock_update):
    """Test that admin rights are granted if user ID is in bot_data."""
    context = SimpleNamespace(bot_data={"admin_ids": [123]})
    assert await check_admin_rights(mock_update, context) is True


@pytest.mark.asyncio
async def test_check_admin_rights_config(mocker, mock_update):
    """Test that admin rights are granted if user ID is in config."""
    context = SimpleNamespace(bot_data={})
    load_config_mock = mocker.patch(
        "telegram_auto_poster.bot.permissions.load_config",
        return_value=Config(
            telegram=TelegramConfig(
                api_id=1, api_hash="h", username="u", target_channels=["@c"]
            ),
            bot=BotConfig(
                bot_token="t", bot_username="b", bot_chat_id=999, admin_ids=[123]
            ),
            chats=ChatsConfig(selected_chats=["@a"], luba_chat="@b"),
        ),
    )
    assert await check_admin_rights(mock_update, context) is True
    assert load_config_mock.call_count == 1
    assert context.bot_data["admin_ids"] == [123]


@pytest.mark.asyncio
async def test_check_admin_rights_config_cached(mocker, mock_update):
    """Test that configuration is cached between calls."""
    context = SimpleNamespace(bot_data={})
    load_config_mock = mocker.patch(
        "telegram_auto_poster.bot.permissions.load_config",
        return_value=Config(
            telegram=TelegramConfig(
                api_id=1, api_hash="h", username="u", target_channels=["@c"]
            ),
            bot=BotConfig(
                bot_token="t", bot_username="b", bot_chat_id=999, admin_ids=[123]
            ),
            chats=ChatsConfig(selected_chats=["@a"], luba_chat="@b"),
        ),
    )
    assert await check_admin_rights(mock_update, context) is True
    assert await check_admin_rights(mock_update, context) is True
    assert load_config_mock.call_count == 1


@pytest.mark.asyncio
async def test_check_admin_rights_bot_chat_id(mocker, mock_update):
    """Test backward compatibility with bot_chat_id."""
    context = SimpleNamespace(bot_data={})
    load_config_mock = mocker.patch(
        "telegram_auto_poster.bot.permissions.load_config",
        return_value=Config(
            telegram=TelegramConfig(
                api_id=1, api_hash="h", username="u", target_channels=["@c"]
            ),
            bot=BotConfig(bot_token="t", bot_username="b", bot_chat_id=123),
            chats=ChatsConfig(selected_chats=["@a"], luba_chat="@b"),
        ),
    )
    assert await check_admin_rights(mock_update, context) is True
    assert load_config_mock.call_count == 1


@pytest.mark.asyncio
async def test_check_admin_rights_no_permission(mocker, mock_update):
    """Test that admin rights are denied if user is not an admin."""
    mock_update.effective_user.id = 456
    context = SimpleNamespace(bot_data={})
    mocker.patch(
        "telegram_auto_poster.bot.permissions.load_config",
        return_value=Config(
            telegram=TelegramConfig(
                api_id=1, api_hash="h", username="u", target_channels=["@c"]
            ),
            bot=BotConfig(
                bot_token="t", bot_username="b", bot_chat_id=999, admin_ids=[123]
            ),
            chats=ChatsConfig(selected_chats=["@a"], luba_chat="@b"),
        ),
    )
    assert await check_admin_rights(mock_update, context) is False
    mock_update.message.reply_text.assert_awaited_once_with(
        "У вас нет прав на использование этой команды."
    )


@pytest.mark.asyncio
async def test_check_admin_rights_exception(mocker, mock_update):
    """Test that an error message is sent if an exception occurs."""
    context = SimpleNamespace(bot_data={})
    mocker.patch(
        "telegram_auto_poster.bot.permissions.load_config",
        side_effect=Exception("boom"),
    )
    assert await check_admin_rights(mock_update, context) is False
    mock_update.message.reply_text.assert_awaited_once_with(
        "Произошла ошибка при проверке прав доступа."
    )
