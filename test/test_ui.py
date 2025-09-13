from telegram_auto_poster.utils.ui import approval_keyboard, CALLBACK_PUSH


def test_approval_keyboard_default_push():
    markup = approval_keyboard()
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert CALLBACK_PUSH in callbacks


def test_approval_keyboard_channel_prompt():
    channels = ["@c1", "@c2"]
    markup = approval_keyboard(channels, True)
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert f"{CALLBACK_PUSH}:@c1" in callbacks
    assert f"{CALLBACK_PUSH}:@c2" in callbacks
    assert f"{CALLBACK_PUSH}:all" in callbacks
