from pathlib import Path
import sys
import importlib

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from telegram_auto_poster import config as config_module
config_module = importlib.reload(config_module)


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
    with pytest.raises(RuntimeError, match="Missing section \\[Bot\\]"):
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
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
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
[Chats]
selected_chats = @test1, @test2
luba_chat = @luba
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    conf = config_module.load_config()
    assert conf["api_id"] == 123
    assert conf["bot_chat_id"] == "1"
    assert conf["selected_chats"] == ["@test1", "@test2"]
