import os
import os
from pathlib import Path

import pytest

CONFIG_CONTENT = """
[Telegram]
api_id = 1
api_hash = test
username = test
target_channels = @test
[Bot]
bot_token = token
bot_username = bot
bot_chat_id = 1
[Chats]
selected_chats = @test1,@test2
luba_chat = @luba
[Web]
session_secret = secret
"""

config_path = Path("/tmp/test_config.ini")
config_path.write_text(CONFIG_CONTENT, encoding="utf-8")
os.environ.setdefault("CONFIG_PATH", str(config_path))
os.environ.setdefault("VALKEY_BACKEND", "pogocache")
os.environ.setdefault("MINIO_BACKEND", "garage")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio")


@pytest.fixture(autouse=True)
def configure_backends(monkeypatch, tmp_path):
    """Configure local in-memory backends for every test."""

    garage_root = tmp_path / "garage"
    garage_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GARAGE_ROOT", str(garage_root))

    from telegram_auto_poster.config import CONFIG

    CONFIG.valkey.backend = "pogocache"
    CONFIG.minio.backend = "garage"
    CONFIG.minio.garage_root = str(garage_root)

    from telegram_auto_poster.utils import db
    from telegram_auto_poster.utils.storage import reset_storage_for_tests

    db.reset_cache_for_tests()
    reset_storage_for_tests()

    yield

    db.reset_cache_for_tests()
    reset_storage_for_tests()


@pytest.fixture
def mock_config(mocker):
    """Autouse fixture to mock config loading for all tests."""

    from telegram_auto_poster.config import (
        BotConfig,
        ChatsConfig,
        Config,
        TelegramConfig,
        WebConfig,
    )

    mocker.patch(
        "telegram_auto_poster.config.load_config",
        return_value=Config(
            telegram=TelegramConfig(
                api_id=1,
                api_hash="test",
                username="test",
                target_channels=["@test"],
            ),
            bot=BotConfig(
                bot_token="token",
                bot_username="bot",
                bot_chat_id=1,
                admin_ids=[1],
            ),
            web=WebConfig(session_secret="secret"),
            chats=ChatsConfig(
                selected_chats=["@test1", "@test2"],
                luba_chat="@luba",
            ),
        ),
    )
