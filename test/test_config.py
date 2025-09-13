from pathlib import Path
import importlib
import sys

import pytest
from pydantic import ValidationError


def write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_missing_sections(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
target_channels = @test
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    sys.modules.pop("telegram_auto_poster.config", None)
    with pytest.raises(ValidationError, match="(bot|web)"):
        importlib.import_module("telegram_auto_poster.config")


def test_missing_field(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
# target_channels missing
[Bot]
bot_token = token
bot_username = user
bot_chat_id = 1
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
[Web]
session_secret = secret
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    sys.modules.pop("telegram_auto_poster.config", None)
    with pytest.raises(ValidationError, match="target_channels"):
        importlib.import_module("telegram_auto_poster.config")


def test_valid_config(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
target_channels = @test
[Bot]
bot_token = token
bot_username = user
bot_chat_id = 1
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
[Web]
session_secret = secret
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf.telegram.api_id == 123
    assert conf.bot.bot_chat_id == 1
    assert conf.chats.selected_chats == ["@test1", "@test2"]
    assert conf.schedule.quiet_hours_start == 22
    assert conf.schedule.quiet_hours_end == 10
    assert conf.rate_limit.rate == 1
    assert conf.rate_limit.capacity == 5


def test_custom_schedule_config(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
target_channels = @test
[Bot]
bot_token = token
bot_username = user
bot_chat_id = 1
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
[Web]
session_secret = secret
[Schedule]
quiet_hours_start = 20
quiet_hours_end = 8
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf.schedule.quiet_hours_start == 20
    assert conf.schedule.quiet_hours_end == 8


def test_custom_rate_limit_config(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
target_channels = @test
[Bot]
bot_token = token
bot_username = user
bot_chat_id = 1
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
[Web]
session_secret = secret
[RateLimit]
rate = 2
capacity = 10
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf.rate_limit.rate == 2
    assert conf.rate_limit.capacity == 10


def test_invalid_port_env(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
target_channels = @test
[Bot]
bot_token = token
bot_username = user
bot_chat_id = 1
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
[Web]
session_secret = secret
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    monkeypatch.setenv("MINIO_PORT", "abc")
    sys.modules.pop("telegram_auto_poster.config", None)
    with pytest.raises(ValidationError, match=r"minio.*port"):
        importlib.import_module("telegram_auto_poster.config")


def test_env_override_precedence(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
target_channels = @test
[Bot]
bot_token = token
bot_username = user
bot_chat_id = 1
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
[Web]
session_secret = secret
[Schedule]
quiet_hours_start = 20
quiet_hours_end = 8
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    monkeypatch.setenv("SCHEDULE_QUIET_HOURS_START", "5")
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf.schedule.quiet_hours_start == 5


def test_prompt_target_channel_config(tmp_path, monkeypatch):
    write_config(
        tmp_path / "config.ini",
        """
[Telegram]
api_id = 123
api_hash = aaa
username = test
target_channels = @test
[Bot]
bot_token = token
bot_username = user
bot_chat_id = 1
prompt_target_channel = true
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf.bot.prompt_target_channel is True
