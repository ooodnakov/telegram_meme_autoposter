import logging
import sys
from typing import Any, Mapping

from pytest_mock import MockerFixture

from telegram_auto_poster.utils.logger_setup import (
    PropagateHandler,
    custom_format,
    setup_logger,
)


def test_custom_format() -> None:
    """Test that custom_format returns the expected string with relative path."""

    class FakeFile:
        def __init__(self, path: str):
            self.path = path

    record: Mapping[str, Any] = {"file": FakeFile("/some/absolute/path.py")}

    result = custom_format(record)

    # Path should have the first character stripped (e.g. "/some/..." -> "some/...")
    expected_path_segment = "some/absolute/path.py"

    assert f"<cyan>{expected_path_segment}</cyan>" in result
    assert "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>" in result
    assert "<level>{message}</level>" in result


def test_custom_format_no_path() -> None:
    """Test custom_format when record does not have a valid file path."""
    record: Mapping[str, Any] = {"file": None}
    result = custom_format(record)
    assert "<cyan></cyan>:<cyan>{line}</cyan>" in result


def test_propagate_handler(mocker: MockerFixture) -> None:
    """Test that PropagateHandler forwards loguru records to standard logging."""
    handler = PropagateHandler()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="path.py",
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None,
    )

    mock_logger = mocker.Mock()
    mock_get_logger = mocker.patch("logging.getLogger", return_value=mock_logger)

    handler.emit(record)

    mock_get_logger.assert_called_once_with("test_logger")
    mock_logger.handle.assert_called_once_with(record)


def test_setup_logger(mocker: MockerFixture) -> None:
    """Test that setup_logger configures loguru correctly."""
    mock_remove = mocker.patch("telegram_auto_poster.utils.logger_setup.logger.remove")
    mock_add = mocker.patch("telegram_auto_poster.utils.logger_setup.logger.add")

    logger_instance = setup_logger()

    # Assert logger.remove() was called to clear defaults
    mock_remove.assert_called_once_with()

    # Assert logger.add() was called twice: once for stderr, once for PropagateHandler
    assert mock_add.call_count == 2

    # Check stderr handler
    call_args_1 = mock_add.call_args_list[0]
    assert call_args_1.args[0] is sys.stderr
    assert call_args_1.kwargs.get("format") == custom_format
    assert call_args_1.kwargs.get("colorize") is True

    # Check PropagateHandler
    call_args_2 = mock_add.call_args_list[1]
    assert isinstance(call_args_2.args[0], PropagateHandler)
    assert call_args_2.kwargs.get("format") == "{message}"

    # Make sure it returns the logger
    from loguru import logger as expected_logger

    assert logger_instance is expected_logger
