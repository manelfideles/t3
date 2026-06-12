from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from t3.config import settings
from t3.integrations.gcal import create_event, list_events
from t3.tools.registry import tool

_UTC = timezone.utc


def _parse_dt(s: str) -> str:
    """Promote a date-only string to midnight UTC; pass datetime strings through."""
    return s if "T" in s else f"{s}T00:00:00Z"


def _shape_event(raw: dict) -> dict:
    start = raw.get("start", {})
    end = raw.get("end", {})
    return {
        "id": raw.get("id", ""),
        "summary": raw.get("summary", ""),
        "start": start.get("dateTime") or start.get("date", ""),
        "end": end.get("dateTime") or end.get("date", ""),
    }


@tool
def get_gcal_events(time_min: str = "", time_max: str = "") -> list[dict[str, Any]] | dict[str, Any]:
    """List T3 training sessions from Google Calendar.

    Call this when the user asks what's on their schedule, wants to review
    upcoming sessions, or asks if a specific day is free.

    time_min / time_max accept ISO 8601 date ("2026-06-15") or datetime
    ("2026-06-15T07:00:00Z"). Omit both to return the next 7 days.

    Returns a list of {id, summary, start, end} dicts, newest-first.
    Returns {"error": "not_connected", "action": "..."} when Google Calendar
    is not authorised — relay the action message to the user.

    Do NOT call this to check whether a training plan has been generated;
    use generate_training_plan or confirm_plan for that.
    """
    now = datetime.now(_UTC)
    start = _parse_dt(time_min) if time_min else now.isoformat()
    end = _parse_dt(time_max) if time_max else (now + timedelta(days=7)).isoformat()
    try:
        return [_shape_event(e) for e in list_events(start, end, db_path=settings.database_url)]
    except RuntimeError:
        return {"error": "not_connected", "action": "Ask the user to connect Google Calendar first."}


@tool
def create_gcal_event(summary: str, start: str, end: str) -> dict[str, Any]:
    """Create a single event in the T3 Google Calendar.

    Call this when the user explicitly asks to add one session or event to
    their calendar. To schedule an entire training plan use confirm_plan.

    summary: short event title, e.g. "Brick session — bike + run"
    start / end: ISO 8601 datetime, e.g. "2026-06-15T07:00:00Z"

    Returns {id, summary, start, end} for the created event.
    Returns {"error": "not_connected", "action": "..."} if not authorised.
    """
    try:
        return _shape_event(create_event(summary, start, end, db_path=settings.database_url))
    except RuntimeError:
        return {"error": "not_connected", "action": "Ask the user to connect Google Calendar first."}
