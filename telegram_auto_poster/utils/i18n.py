from __future__ import annotations

import gettext as _gettext
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram_auto_poster.config import CONFIG, Config

# Path to locales directory
_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locales"

# Context variable storing the current translator
_translator: ContextVar[_gettext.NullTranslations] = ContextVar(
    "translator",
    default=_gettext.translation("messages", localedir=_LOCALE_DIR, fallback=True),
)


def set_locale(lang: Optional[str]) -> None:
    """Set the active locale for the current context."""
    translation = _gettext.translation(
        "messages",
        localedir=_LOCALE_DIR,
        languages=[lang] if lang else None,
        fallback=True,
    )
    _translator.set(translation)


def gettext(message: str) -> str:
    """Translate ``message`` using the active locale."""
    return _translator.get().gettext(message)


_ = gettext


def resolve_locale(update: Optional[Update], config: Config = CONFIG) -> str:
    """Resolve the locale for a given Telegram update.

    Priority:
    1. Per-user preference from configuration.
    2. Telegram's ``language_code`` from the update.
    3. Configured default language.
    """

    user = getattr(update, "effective_user", None)
    user_id = getattr(user, "id", None)
    if user_id is not None:
        user_pref = config.i18n.users.get(user_id)
        if user_pref:
            return user_pref
        lang = getattr(user, "language_code", None)
        if lang:
            return lang
    return config.i18n.default
