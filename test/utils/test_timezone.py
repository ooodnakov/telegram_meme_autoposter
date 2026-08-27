import datetime
import pytest

from telegram_auto_poster.utils import timezone


def test_now_utc_is_timezone_aware():
    now = timezone.now_utc()
    assert now.tzinfo is timezone.UTC


def test_to_display_converts_naive():
    naive = datetime.datetime(2024, 1, 1, 12, 0)
    converted = timezone.to_display(naive)
    assert converted.tzinfo == timezone.DISPLAY_TZ
    assert converted.hour == 15


def test_format_display_uses_display_tz():
    dt = datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
    assert timezone.format_display(dt, "%H:%M") == "15:00"




def test_parse_to_utc_timestamp_default_format():
    dt_str = "2024-01-01 15:00"
    expected_timestamp = int(
        datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
    )
    assert timezone.parse_to_utc_timestamp(dt_str) == expected_timestamp


def test_parse_to_utc_timestamp_custom_format():
    dt_str = "01/01/2024 15:00"
    fmt = "%d/%m/%Y %H:%M"
    expected_timestamp = int(
        datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
    )
    assert timezone.parse_to_utc_timestamp(dt_str, fmt=fmt) == expected_timestamp


def test_parse_to_utc_timestamp_invalid_format():
    with pytest.raises(ValueError):
        timezone.parse_to_utc_timestamp("2024-01-01")
