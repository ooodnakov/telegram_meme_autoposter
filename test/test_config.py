from pathlib import Path
import importlib
import sys

import pytest



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
target_channel = @test
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    monkeypatch.setenv("DB_MYSQL_USER", "user")
    monkeypatch.setenv("DB_MYSQL_PASSWORD", "pass")
    monkeypatch.setenv("DB_MYSQL_NAME", "db")
    sys.modules.pop("telegram_auto_poster.config", None)
    with pytest.raises(RuntimeError, match="Missing section \\[Bot\\]"):
        importlib.import_module("telegram_auto_poster.config")


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
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    monkeypatch.setenv("DB_MYSQL_USER", "user")
    monkeypatch.setenv("DB_MYSQL_PASSWORD", "pass")
    monkeypatch.setenv("DB_MYSQL_NAME", "db")
    sys.modules.pop("telegram_auto_poster.config", None)
    with pytest.raises(RuntimeError, match="target_channel"):
        importlib.import_module("telegram_auto_poster.config")


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
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    monkeypatch.setenv("DB_MYSQL_USER", "user")
    monkeypatch.setenv("DB_MYSQL_PASSWORD", "pass")
    monkeypatch.setenv("DB_MYSQL_NAME", "db")
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf["api_id"] == 123
    assert conf["bot_chat_id"] == "1"
    assert conf["selected_chats"] == ["@test1", "@test2"]
    assert conf["quiet_hours_start"] == 22
    assert conf["quiet_hours_end"] == 10


def test_custom_schedule_config(tmp_path, monkeypatch):
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
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
[Schedule]
quiet_hours_start = 20
quiet_hours_end = 8
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    monkeypatch.setenv("DB_MYSQL_USER", "user")
    monkeypatch.setenv("DB_MYSQL_PASSWORD", "pass")
    monkeypatch.setenv("DB_MYSQL_NAME", "db")
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf["quiet_hours_start"] == 20
    assert conf["quiet_hours_end"] == 8


def test_invalid_port_env(tmp_path, monkeypatch):
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
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    monkeypatch.setenv("DB_MYSQL_USER", "user")
    monkeypatch.setenv("DB_MYSQL_PASSWORD", "pass")
    monkeypatch.setenv("DB_MYSQL_NAME", "db")
    monkeypatch.setenv("MINIO_PORT", "abc")
    sys.modules.pop("telegram_auto_poster.config", None)
    with pytest.raises(RuntimeError, match="Port environment variables must be integers"):
        importlib.import_module("telegram_auto_poster.config")
