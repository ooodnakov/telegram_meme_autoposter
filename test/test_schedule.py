import datetime

from telegram_auto_poster.utils.scheduler import find_next_available_slot


def test_find_next_slot_after_night():
    now = datetime.datetime(2024, 1, 1, 21, 30, tzinfo=datetime.timezone.utc)
    slot = find_next_available_slot(now, [])
    assert slot == datetime.datetime(2024, 1, 2, 10, 0, tzinfo=datetime.timezone.utc)


def test_find_next_slot_skips_occupied():
    now = datetime.datetime(2024, 1, 1, 21, 30, tzinfo=datetime.timezone.utc)
    occupied = [
        ("foo", datetime.datetime(2024, 1, 2, 10, 0, tzinfo=datetime.timezone.utc).timestamp())
    ]
    slot = find_next_available_slot(now, occupied)
    assert slot == datetime.datetime(2024, 1, 2, 11, 0, tzinfo=datetime.timezone.utc)


def test_find_next_slot_custom_hours():
    now = datetime.datetime(2024, 1, 1, 5, 30, tzinfo=datetime.timezone.utc)
    slot = find_next_available_slot(now, [], quiet_start=2, quiet_end=6)
    assert slot == datetime.datetime(2024, 1, 1, 6, 0, tzinfo=datetime.timezone.utc)
