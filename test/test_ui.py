from types import SimpleNamespace

from telegram_auto_poster.utils.ui import (
    CALLBACK_COMMENT,
    CALLBACK_PUSH,
    approval_keyboard,
    comment_enabled_from_message,
)


def test_approval_keyboard_default_push():
    markup = approval_keyboard()
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert CALLBACK_PUSH in callbacks
    assert f"{CALLBACK_COMMENT}:1" in callbacks
    assert markup.inline_keyboard[-1][0].text == "comment ✔️"


def test_approval_keyboard_can_disable_comment():
    markup = approval_keyboard(comment_enabled=False)
    assert markup.inline_keyboard[-1][0].callback_data == f"{CALLBACK_COMMENT}:0"
    assert markup.inline_keyboard[-1][0].text == "comment ✖️"


def test_comment_enabled_from_message_defaults_on_for_legacy_markup():
    assert comment_enabled_from_message(SimpleNamespace(reply_markup=None)) is True


def test_comment_enabled_from_message_reads_toggle_state():
    markup = approval_keyboard(comment_enabled=False)
    assert comment_enabled_from_message(SimpleNamespace(reply_markup=markup)) is False


def test_approval_keyboard_channel_prompt():
    channels = ["@c1", "@c2"]
    markup = approval_keyboard(channels, True)
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert f"{CALLBACK_PUSH}:@c1" in callbacks
    assert f"{CALLBACK_PUSH}:@c2" in callbacks
    assert f"{CALLBACK_PUSH}:all" in callbacks
