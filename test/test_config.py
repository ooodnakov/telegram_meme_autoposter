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
    config_module = importlib.import_module("telegram_auto_poster.config")
    with pytest.raises(ValidationError, match="(bot|web)"):
        config_module.get_config(refresh=True)


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
    config_module = importlib.import_module("telegram_auto_poster.config")
    with pytest.raises(ValidationError, match="target_channels"):
        config_module.get_config(refresh=True)


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


def test_config_proxy_repr_does_not_expose_secrets(tmp_path, monkeypatch):
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

    config_module.get_config(refresh=True)

    proxy_repr = repr(config_module.CONFIG)
    assert proxy_repr == "<_ConfigProxy(cached=True)>"
    assert "aaa" not in proxy_repr


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
    config_module = importlib.import_module("telegram_auto_poster.config")
    with pytest.raises(ValidationError, match=r"minio.*port"):
        config_module.get_config(refresh=True)


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


def test_env_admin_ids_cast_to_int(tmp_path, monkeypatch):
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
    monkeypatch.setenv("BOT_ADMIN_IDS", "10, 20")
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf.bot.admin_ids == [10, 20]


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
[Web]
session_secret = secret
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf.bot.prompt_target_channel is True


def test_branding_section(tmp_path, monkeypatch):
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
[Branding]
attribution = example.com/brand
suggestion_caption = Custom caption
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.ini"))
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf.branding.attribution == "example.com/brand"
    assert conf.branding.suggestion_caption == "Custom caption"


def test_watermark_env_overrides(tmp_path, monkeypatch):
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
    monkeypatch.setenv("WATERMARK_IMAGE_SIZE_RATIO", "0.25")
    monkeypatch.setenv("WATERMARK_VIDEO_MIN_SPEED", "10")
    monkeypatch.setenv("WATERMARK_VIDEO_MAX_SPEED", "20")
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf.watermark_image.size_ratio == 0.25
    assert conf.watermark_video.min_speed == 10
    assert conf.watermark_video.max_speed == 20


def test_ocr_env_overrides(tmp_path, monkeypatch):
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
    monkeypatch.setenv("OCR_ENABLED", "false")
    monkeypatch.setenv("OCR_LANGUAGES", "eng")
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")
    conf = config_module.load_config()
    assert conf.ocr.enabled is False
    assert conf.ocr.languages == "eng"


def test_i18n_users_default_dict_is_independent():
    from telegram_auto_poster.config import I18nConfig

    first = I18nConfig()
    second = I18nConfig()

    first.users[1] = "en"
    assert second.users == {}


def test_i18n_users_env_override_unchanged(tmp_path, monkeypatch):
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
    monkeypatch.setenv("I18N_USERS", "1:en, 2:ru")
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")

    conf = config_module.get_config(refresh=True)
    assert conf.i18n.users == {1: "en", 2: "ru"}


def test_get_config_caching_semantics(tmp_path, monkeypatch):
    config_path = tmp_path / "config.ini"
    write_config(
        config_path,
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
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    sys.modules.pop("telegram_auto_poster.config", None)
    config_module = importlib.import_module("telegram_auto_poster.config")

    first = config_module.get_config(refresh=True)
    second = config_module.get_config()
    assert first is second

    write_config(
        config_path,
        """
[Telegram]
api_id = 999
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

    cached = config_module.get_config()
    refreshed = config_module.get_config(refresh=True)

    assert cached.telegram.api_id == 123
    assert refreshed.telegram.api_id == 999
    assert refreshed is not first
