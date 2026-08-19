"""Utilities for constructing Telegram UI elements."""

from collections.abc import Iterable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram_auto_poster.utils.i18n import _

# Callback data constants
CALLBACK_OK = "/ok"
CALLBACK_SCHEDULE = "/schedule"
CALLBACK_PUSH = "/push"
CALLBACK_NOTOK = "/notok"
CALLBACK_RESTORE = "/restore"
CALLBACK_COMMENT = "/comment"


def comment_enabled_from_message(message: object) -> bool:
    """Read the comment toggle state encoded in a review message keyboard.

    Review messages carry the state in the callback data so the setting survives
    until the admin presses Push without introducing another storage dependency.
    New or legacy messages default to comments enabled.
    """
    markup = getattr(message, "reply_markup", None)
    for row in getattr(markup, "inline_keyboard", ()):
        for button in row:
            callback_data = getattr(button, "callback_data", "")
            if callback_data == f"{CALLBACK_COMMENT}:0":
                return False
            if callback_data == f"{CALLBACK_COMMENT}:1":
                return True
    return True


def approval_keyboard(
    target_channels: Iterable[str] | None = None,
    prompt_channel: bool = False,
    comment_enabled: bool = True,
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
    rows.append(
        [
            InlineKeyboardButton(
                f"comment {'✔️' if comment_enabled else '✖️'}",
                callback_data=f"{CALLBACK_COMMENT}:{int(comment_enabled)}",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def trashed_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard markup for trashed items."""

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(_("Restore"), callback_data=CALLBACK_RESTORE)]]
    )
