"""Utilities for constructing Telegram UI elements."""

from collections.abc import Iterable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram_auto_poster.utils.i18n import _

# Callback data constants
CALLBACK_OK = "/ok"
CALLBACK_SCHEDULE = "/schedule"
CALLBACK_PUSH = "/push"
CALLBACK_NOTOK = "/notok"


def approval_keyboard(
    target_channels: Iterable[str] | None = None,
    prompt_channel: bool = False,
) -> InlineKeyboardMarkup:
    """Return the approval keyboard markup.

    When ``prompt_channel`` is ``True`` and multiple ``target_channels`` are
    provided, separate push buttons for each channel and an "all" option are
    included. Otherwise a single push button is shown.
    """
    rows = [
        [
            InlineKeyboardButton(_("Send to batch!"), callback_data=CALLBACK_OK),
            InlineKeyboardButton(_("Schedule"), callback_data=CALLBACK_SCHEDULE),
        ]
    ]
    channels = list(target_channels or [])
    if prompt_channel and len(channels) > 1:
        for ch in channels:
            rows.append(
                [
                    InlineKeyboardButton(
                        _("Push to {channel}").format(channel=ch),
                        callback_data=f"{CALLBACK_PUSH}:{ch}",
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    _("Push to all"), callback_data=f"{CALLBACK_PUSH}:all"
                ),
                InlineKeyboardButton(_("No!"), callback_data=CALLBACK_NOTOK),
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(_("Push!"), callback_data=CALLBACK_PUSH),
                InlineKeyboardButton(_("No!"), callback_data=CALLBACK_NOTOK),
            ]
        )
    return InlineKeyboardMarkup(rows)
