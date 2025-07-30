import os
from pathlib import Path

import pytest

from telegram_auto_poster import config as config_module


def write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_missing_sections(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
""",
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="Файл config.ini заполнен некорректно"):
        config_module.load_config()


def test_missing_field(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
# target_channel missing
[Bot]
bot_token = token
bot_username = user
bot_chat_id = 1
""",
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="target_channel"):
        config_module.load_config()


def test_valid_config(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
target_channel = @test
[Bot]
bot_token = token
bot_username = user
bot_chat_id = 1
openai_api_key = KEY
""",
    )
    monkeypatch.chdir(tmp_path)
    conf = config_module.load_config()
    assert conf["api_id"] == 123
    assert conf["bot_chat_id"] == "1"
    assert conf["openai_api_key"] == "KEY"


def test_bot_sets_openai_env(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
target_channel = @test
[Bot]
bot_token = token
bot_username = user
bot_chat_id = 1
openai_api_key = ENVKEY
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    import sys
    from types import ModuleType

    dummy_config = ModuleType("telegram_auto_poster.config")
    dummy_config.PHOTOS_BUCKET = "photos"
    dummy_config.VIDEOS_BUCKET = "videos"
    dummy_config.DOWNLOADS_BUCKET = "downloads"
    dummy_config.LUBA_CHAT = "@luba"
    dummy_config.load_config = lambda: {
        "bot_token": "t",
        "bot_chat_id": "1",
        "openai_api_key": "ENVKEY",
    }
    monkeypatch.setitem(sys.modules, "telegram_auto_poster.config", dummy_config)

    dummy_callbacks = ModuleType("telegram_auto_poster.bot.callbacks")
    dummy_callbacks.ok_callback = lambda *a, **k: None
    dummy_callbacks.push_callback = lambda *a, **k: None
    dummy_callbacks.notok_callback = lambda *a, **k: None
    dummy_callbacks.caption_select_callback = lambda *a, **k: None
    dummy_callbacks.load_config = lambda: {"target_channel": "@ch"}
    monkeypatch.setitem(
        sys.modules,
        "telegram_auto_poster.bot.callbacks",
        dummy_callbacks,
    )

    from telegram_auto_poster.bot.bot import TelegramMemeBot

    TelegramMemeBot()
    assert os.environ["OPENAI_API_KEY"] == "ENVKEY"

