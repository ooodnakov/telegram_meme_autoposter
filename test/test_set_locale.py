from unittest.mock import MagicMock, patch, mock_open
from io import BytesIO
from pathlib import Path
import gettext as _gettext
import sys

from telegram_auto_poster.utils.i18n import set_locale, _translator, _LOCALE_DIR

def test_set_locale_none():
    with patch("gettext.translation") as mock_translation:
        mock_trans_obj = MagicMock()
        mock_translation.return_value = mock_trans_obj

        set_locale(None)

        mock_translation.assert_called_with(
            "messages", localedir=_LOCALE_DIR, languages=None, fallback=True
        )
        assert _translator.get() == mock_trans_obj

def test_set_locale_mo_exists():
    with patch("telegram_auto_poster.utils.i18n.Path.exists", autospec=True) as mock_exists, \
         patch("gettext.translation") as mock_translation:

        mock_exists.side_effect = lambda self: str(self).endswith("messages.mo")
        mock_trans_obj = MagicMock()
        mock_translation.return_value = mock_trans_obj

        set_locale("en")

        mock_translation.assert_called_with(
            "messages",
            localedir=_LOCALE_DIR,
            languages=["en"],
            fallback=True,
        )
        assert _translator.get() == mock_trans_obj

def test_set_locale_po_exists_mo_missing():
    import babel.messages.pofile
    import babel.messages.mofile
    with patch("telegram_auto_poster.utils.i18n.Path.exists", autospec=True) as mock_exists, \
         patch("telegram_auto_poster.utils.i18n.Path.open", mock_open(read_data=b"po content")), \
         patch("telegram_auto_poster.utils.i18n.read_po") as mock_read_po, \
         patch("telegram_auto_poster.utils.i18n.write_mo") as mock_write_mo, \
         patch("gettext.GNUTranslations") as mock_gnu_translations:

        def side_effect(self):
            s = str(self)
            if s.endswith("messages.mo"):
                return False
            if s.endswith("messages.po"):
                return True
            return False

        mock_exists.side_effect = side_effect

        mock_catalog = MagicMock()
        mock_read_po.return_value = mock_catalog

        mock_trans_obj = MagicMock()
        mock_gnu_translations.return_value = mock_trans_obj

        set_locale("fr")

        mock_read_po.assert_called()
        mock_write_mo.assert_called()
        assert _translator.get() == mock_trans_obj

def test_set_locale_both_missing():
    with patch("telegram_auto_poster.utils.i18n.Path.exists", autospec=True) as mock_exists, \
         patch("gettext.translation") as mock_translation:

        mock_exists.return_value = False
        mock_trans_obj = MagicMock()
        mock_translation.return_value = mock_trans_obj

        set_locale("de")

        mock_translation.assert_called_with(
            "messages", localedir=_LOCALE_DIR, languages=["de"], fallback=True
        )
        assert _translator.get() == mock_trans_obj
