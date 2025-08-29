import datetime

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
