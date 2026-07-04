from __future__ import annotations

from datetime import datetime

from t3.sync import CalendarChange, CalendarChangeType, ConflictInfo


def _fmt_date(iso: str) -> str:
    """'2026-06-22T07:00:00' → 'Mon, Jun 22 at 07:00'. Falls back to the raw date slice."""
    try:
        dt = datetime.fromisoformat(iso[:19])
        return dt.strftime("%a, %b %-d at %H:%M")
    except ValueError:
        return iso[:10] or "unknown date"


def conflict_prompt(
    conflict: ConflictInfo,
    moved_event_title: str | None = None,
    conflicting_event_title: str | None = None,
) -> str:
    original_fmt = _fmt_date(conflict.original_time)
    new_fmt = _fmt_date(conflict.new_time)

    return (
        f"⚠️ *Schedule conflict detected!*\n\n"
        f"Session '{moved_event_title}' was moved from *{original_fmt}* → *{new_fmt}*, "
        f"but a {conflicting_event_title} is already scheduled on *{new_fmt}*.\n\n"
        f"Choose a resolution:\n"
        f"1 - Revert move — put the {moved_event_title} back to {original_fmt}\n"
        f"2 - Keep move, remove other — keep the {moved_event_title} on {new_fmt}, delete the {conflicting_event_title}\n"
        f"3 - Remove moved — delete the {moved_event_title} you just moved\n"
        f"4 - Keep both — leave both sessions on {new_fmt}\n\n"
        f"Reply with 1, 2, 3, or 4."
    )


def sync_notification(change: CalendarChange, calendar: str = "Google Calendar") -> str:
    _notification_msg = {
        CalendarChangeType.CREATED: lambda c: f"Activity created at {_fmt_date(c.new_scheduled_at)}",
        CalendarChangeType.MOVED: lambda c: (
            f"Changed activity from {_fmt_date(c.old_scheduled_at)} to {_fmt_date(c.new_scheduled_at)}."
        ),
        CalendarChangeType.DELETED: lambda c: f"Activity was scheduled at {_fmt_date(c.old_scheduled_at)}",
    }
    return f"Synced: {change.type} session on {calendar}. {_notification_msg[change.type](change)}"


def weather_warning(location: str, forecast: str) -> str:
    raise NotImplementedError


def weekly_digest(summary: str) -> str:
    raise NotImplementedError


def vacation_probe(athlete_name: str) -> str:
    raise NotImplementedError
