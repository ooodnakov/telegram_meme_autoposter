import datetime

UTC = datetime.timezone.utc
DISPLAY_TZ = datetime.timezone(datetime.timedelta(hours=3))


def now_utc() -> datetime.datetime:
    """Return current time in UTC with timezone information attached.

    Returns:
        datetime.datetime: Timezone-aware ``datetime`` in UTC.
    """
    return datetime.datetime.now(UTC)


def to_display(dt: datetime.datetime) -> datetime.datetime:
    """Convert a datetime to the display timezone (UTC+3).

    Args:
        dt: Source ``datetime`` object. If naive, UTC is assumed.

    Returns:
        datetime.datetime: ``dt`` converted to the display timezone.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(DISPLAY_TZ)


def format_display(dt: datetime.datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Format ``dt`` for human display in the local timezone.

    Args:
        dt: Datetime to format.
        fmt: Format string for :func:`datetime.strftime`.

    Returns:
        str: Formatted date/time string.
    """
    return to_display(dt).strftime(fmt)
