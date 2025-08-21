import logging

from telegram_auto_poster.utils.logger_setup import get_logger, setup_logger


def test_logger_binding(caplog):
    setup_logger()
    with caplog.at_level(logging.INFO):
        log = get_logger(chat_id=1, user_id=2, object_name="obj", operation="op")
        log.info("hello")
    record = caplog.records[0]
    extra = record.__dict__.get("extra", {})
    assert extra["chat_id"] == 1
    assert extra["user_id"] == 2
    assert extra["object_name"] == "obj"
    assert extra["operation"] == "op"
