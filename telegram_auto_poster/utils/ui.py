"""Utilities for constructing Telegram UI elements."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram_auto_poster.utils.i18n import _

# Callback data constants
CALLBACK_OK = "/ok"
CALLBACK_SCHEDULE = "/schedule"
CALLBACK_PUSH = "/push"
CALLBACK_NOTOK = "/notok"


def approval_keyboard() -> InlineKeyboardMarkup:
    """Return the standard approval keyboard markup.

    Contains buttons for sending to batch, scheduling, pushing immediately,
    or rejecting a submission.
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(_("Send to batch!"), callback_data=CALLBACK_OK),
                InlineKeyboardButton(_("Schedule"), callback_data=CALLBACK_SCHEDULE),
            ],
            [
                InlineKeyboardButton(_("Push!"), callback_data=CALLBACK_PUSH),
                InlineKeyboardButton(_("No!"), callback_data=CALLBACK_NOTOK),
            ],
        ]
    )
