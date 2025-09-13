import types

from pydantic import SecretStr
from telegram_auto_poster.config import (
    Config,
    BotConfig,
    TelegramConfig,
    ChatsConfig,
    I18nConfig,
    WebConfig,
)
from telegram_auto_poster.utils.i18n import _, resolve_locale, set_locale, gettext

class DummyUser:
    def __init__(self, user_id, language_code=None):
        self.id = user_id
        self.language_code = language_code

class DummyUpdate:
    def __init__(self, user):
        self.effective_user = user


def minimal_config(i18n):
    return Config(
        telegram=TelegramConfig(
            api_id=1, api_hash="a", username="u", target_channels=["c"]
        ),
        bot=BotConfig(bot_token=SecretStr("t"), bot_username="b", bot_chat_id=1),
        web=WebConfig(session_secret=SecretStr("s")),
        chats=ChatsConfig(selected_chats=["a"], luba_chat="b"),
        i18n=i18n,
    )


def test_resolve_locale_precedence():
    cfg = minimal_config(I18nConfig(default="ru", users={1: "en"}))
    upd1 = DummyUpdate(DummyUser(1, "es"))
    upd2 = DummyUpdate(DummyUser(2, "es"))
    upd3 = DummyUpdate(DummyUser(3, None))
    assert resolve_locale(upd1, cfg) == "en"
    assert resolve_locale(upd2, cfg) == "es"
    assert resolve_locale(upd3, cfg) == "ru"


def test_gettext_translates():
    set_locale("en")
    assert _(
        "Привет! Присылай сюда свои мемы)"
    ) == "Hello! Send your memes here"
    set_locale("ru")
    assert _(
        "Привет! Присылай сюда свои мемы)"
    ) == "Привет! Присылай сюда свои мемы)"
