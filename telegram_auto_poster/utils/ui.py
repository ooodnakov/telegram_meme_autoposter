from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def approval_keyboard() -> InlineKeyboardMarkup:
    """Return the standard approval keyboard markup.

    Contains buttons for sending to batch, scheduling, pushing immediately,
    or rejecting a submission.
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Send to batch!", callback_data="/ok"),
                InlineKeyboardButton("Schedule", callback_data="/schedule"),
            ],
            [
                InlineKeyboardButton("Push!", callback_data="/push"),
                InlineKeyboardButton("No!", callback_data="/notok"),
            ],
        ]
    )
