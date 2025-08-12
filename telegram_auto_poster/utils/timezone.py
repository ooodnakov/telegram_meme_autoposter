import datetime

UTC = datetime.timezone.utc
DISPLAY_TZ = datetime.timezone(datetime.timedelta(hours=3))

def now_utc() -> datetime.datetime:
    """Return current time in UTC with timezone information."""
    return datetime.datetime.now(UTC)


def to_display(dt: datetime.datetime) -> datetime.datetime:
    """Convert a UTC or naive datetime to display timezone (+3)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(DISPLAY_TZ)


def format_display(dt: datetime.datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Format datetime for display in +3 timezone."""
    return to_display(dt).strftime(fmt)

