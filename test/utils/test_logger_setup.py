import pytest

from telegram_auto_poster.utils.logger_setup import custom_format

class MockFile:
    def __init__(self, path: str):
        self.path = path


def test_custom_format_with_absolute_path():
    record = {"file": MockFile("/my/absolute/path.py")}
    formatted = custom_format(record)
    assert "<cyan>my/absolute/path.py</cyan>" in formatted


def test_custom_format_missing_file_key():
    record = {}
    formatted = custom_format(record)
    assert "<cyan></cyan>" in formatted


def test_custom_format_missing_path_attribute():
    record = {"file": "not_a_mock_file_object"}
    formatted = custom_format(record)
    assert "<cyan></cyan>" in formatted


def test_custom_format_empty_path():
    record = {"file": MockFile("")}
    formatted = custom_format(record)
    assert "<cyan></cyan>" in formatted
