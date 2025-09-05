from __future__ import annotations

import gettext as _gettext
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path
from typing import Optional

import polib
from telegram import Update
from telegram_auto_poster.config import CONFIG, Config

# Path to locales directory
_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locales"

# Context variable storing the current translator


def _load_translation(lang: Optional[str]) -> _gettext.NullTranslations:
    """Load translation for a given language, compiling ``.po`` if needed."""
    if lang is None:
        return _gettext.translation("messages", localedir=_LOCALE_DIR, fallback=True)
    mo_path = _LOCALE_DIR / lang / "LC_MESSAGES" / "messages.mo"
    if mo_path.exists():
        with mo_path.open("rb") as fh:
            return _gettext.GNUTranslations(fh)
    po_path = mo_path.with_suffix(".po")
    if po_path.exists():
        po = polib.pofile(str(po_path))
        mo_data = BytesIO(po.to_binary())
        return _gettext.GNUTranslations(mo_data)
    return _gettext.NullTranslations()


_translator: ContextVar[_gettext.NullTranslations] = ContextVar(
    "translator",
    default=_load_translation(None),
)


def set_locale(lang: Optional[str]) -> None:
    """Set the active locale for the current context."""
    _translator.set(_load_translation(lang))


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
