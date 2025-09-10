"""Helpers for scheduling posts while respecting quiet hours."""

from __future__ import annotations

import datetime
from collections.abc import Iterable

from telegram_auto_poster.utils.db import get_scheduled_posts
from telegram_auto_poster.utils.timezone import now_utc


def _in_quiet_hours(hour: int, quiet_start: int, quiet_end: int) -> bool:
    """Return ``True`` if ``hour`` falls within quiet hours."""
    if quiet_start < quiet_end:
        return quiet_start <= hour < quiet_end
    return hour >= quiet_start or hour < quiet_end


def find_next_available_slot(
    now: datetime.datetime,
    scheduled_posts: Iterable[tuple[str, float]],
    quiet_start: int = 22,
    quiet_end: int = 10,
) -> datetime.datetime:
    """Return the next free posting slot respecting quiet hours.

    Args:
        now: Current time in UTC.
        scheduled_posts: Existing posts represented as ``(path, timestamp)``
            tuples.
        quiet_start: Hour when quiet period begins (inclusive).
        quiet_end: Hour when quiet period ends (exclusive).

    Returns:
        ``datetime`` of the next slot that is free and outside quiet hours.

    """
    next_slot = (now + datetime.timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )

    if _in_quiet_hours(next_slot.hour, quiet_start, quiet_end):
        if quiet_start < quiet_end:
            next_slot = next_slot.replace(hour=quiet_end)
        elif next_slot.hour >= quiet_start:
            next_slot = (next_slot + datetime.timedelta(days=1)).replace(hour=quiet_end)
        else:
            next_slot = next_slot.replace(hour=quiet_end)

    occupied_slots = {int(post[1]) for post in scheduled_posts}
    while True:
        if _in_quiet_hours(next_slot.hour, quiet_start, quiet_end):
            if quiet_start < quiet_end:
                next_slot = next_slot.replace(hour=quiet_end)
            elif next_slot.hour >= quiet_start:
                next_slot = (next_slot + datetime.timedelta(days=1)).replace(
                    hour=quiet_end
                )
            else:
                next_slot = next_slot.replace(hour=quiet_end)
            continue

        if int(next_slot.timestamp()) in occupied_slots:
            next_slot += datetime.timedelta(hours=1)
            continue

        break

    return next_slot


def get_due_posts(now: datetime.datetime | None = None) -> list[tuple[str, float]]:
    """Return scheduled posts that are due for publishing.

    Args:
        now: Time to evaluate against. Defaults to current UTC time.

    Returns:
        List of ``(file_path, timestamp)`` pairs that are due.

    """
    current = now or now_utc()
    ts = int(current.timestamp())
    return get_scheduled_posts(max_score=ts)
