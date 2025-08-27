import datetime

import pytest
from telegram_auto_poster.utils.scheduler import (
    _in_quiet_hours,
    find_next_available_slot,
)


@pytest.mark.parametrize(
    "now, scheduled, quiet_start, quiet_end, expected",
    [
        pytest.param(
            datetime.datetime(2024, 1, 1, 21, 30, tzinfo=datetime.timezone.utc),
            [],
            22,
            10,
            datetime.datetime(2024, 1, 2, 10, 0, tzinfo=datetime.timezone.utc),
            id="after_night_empty_schedule",
        ),
        pytest.param(
            datetime.datetime(2024, 1, 1, 21, 30, tzinfo=datetime.timezone.utc),
            [
                (
                    "foo",
                    datetime.datetime(
                        2024, 1, 2, 10, 0, tzinfo=datetime.timezone.utc
                    ).timestamp(),
                )
            ],
            22,
            10,
            datetime.datetime(2024, 1, 2, 11, 0, tzinfo=datetime.timezone.utc),
            id="skip_one_occupied_slot",
        ),
        pytest.param(
            datetime.datetime(2024, 1, 1, 21, 30, tzinfo=datetime.timezone.utc),
            [
                (
                    "foo",
                    datetime.datetime(
                        2024, 1, 2, 10, 0, tzinfo=datetime.timezone.utc
                    ).timestamp(),
                ),
                (
                    "bar",
                    datetime.datetime(
                        2024, 1, 2, 11, 0, tzinfo=datetime.timezone.utc
                    ).timestamp(),
                ),
            ],
            22,
            10,
            datetime.datetime(2024, 1, 2, 12, 0, tzinfo=datetime.timezone.utc),
            id="skip_multiple_occupied_slots",
        ),
        pytest.param(
            datetime.datetime(2024, 1, 1, 5, 30, tzinfo=datetime.timezone.utc),
            [],
            2,
            6,
            datetime.datetime(2024, 1, 1, 6, 0, tzinfo=datetime.timezone.utc),
            id="custom_quiet_hours",
        ),
    ],
)
def test_find_next_slot(now, scheduled, quiet_start, quiet_end, expected):
    slot = find_next_available_slot(
        now, scheduled, quiet_start=quiet_start, quiet_end=quiet_end
    )
    assert slot == expected


@pytest.mark.parametrize(
    "hour, quiet_start, quiet_end, expected",
    [
        pytest.param(3, 2, 6, True, id="in_quiet_hours_day"),
        pytest.param(7, 2, 6, False, id="outside_quiet_hours_day"),
        pytest.param(23, 22, 10, True, id="in_quiet_hours_overnight_start"),
        pytest.param(12, 22, 10, False, id="outside_quiet_hours_overnight"),
    ],
)
def test_in_quiet_hours(hour, quiet_start, quiet_end, expected):
    assert _in_quiet_hours(hour, quiet_start, quiet_end) is expected
