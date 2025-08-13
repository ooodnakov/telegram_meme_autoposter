import datetime


def _in_quiet_hours(hour: int, quiet_start: int, quiet_end: int) -> bool:
    """Return True if ``hour`` falls within quiet hours."""
    if quiet_start < quiet_end:
        return quiet_start <= hour < quiet_end
    return hour >= quiet_start or hour < quiet_end


def find_next_available_slot(
    now: datetime.datetime,
    scheduled_posts,
    quiet_start: int = 22,
    quiet_end: int = 10,
):
    """Return the next free posting slot respecting quiet hours."""
    next_slot = (now + datetime.timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )

    if _in_quiet_hours(next_slot.hour, quiet_start, quiet_end):
        if quiet_start < quiet_end:
            next_slot = next_slot.replace(hour=quiet_end)
        elif next_slot.hour >= quiet_start:
            next_slot = (next_slot + datetime.timedelta(days=1)).replace(
                hour=quiet_end
            )
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
