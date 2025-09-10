"""Runtime internationalization utilities."""

from __future__ import annotations

import gettext as _gettext
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path
from typing import Optional

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
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
    """Set the active locale for the current context.

    Falls back to parsing ``.po`` files when compiled ``.mo`` files are
    unavailable. This allows translations to work even if message catalogs have
    not been precompiled.
    """
    if lang:
        mo_path = _LOCALE_DIR / lang / "LC_MESSAGES" / "messages.mo"
        if mo_path.exists():
            translation = _gettext.translation(
                "messages",
                localedir=_LOCALE_DIR,
                languages=[lang],
                fallback=True,
            )
        else:
            po_path = _LOCALE_DIR / lang / "LC_MESSAGES" / "messages.po"
            if po_path.exists():
                with po_path.open("rb") as fh:
                    catalog = read_po(fh)
                buffer = BytesIO()
                write_mo(buffer, catalog)
                buffer.seek(0)
                translation = _gettext.GNUTranslations(buffer)
            else:
                translation = _gettext.translation(
                    "messages", localedir=_LOCALE_DIR, languages=[lang], fallback=True
                )
    else:
        translation = _gettext.translation(
            "messages", localedir=_LOCALE_DIR, languages=None, fallback=True
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
