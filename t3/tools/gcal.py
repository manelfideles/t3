from typing import Any

from t3.gcal import create_event, list_events
from t3.tools.registry import tool


@tool
def get_gcal_events(time_min: str = "", time_max: str = "") -> list[dict[str, Any]]:
    """List Google Calendar events within a time range.

    Args:
        time_min: RFC3339 start datetime (e.g. '2026-06-11T00:00:00Z')
        time_max: RFC3339 end datetime (e.g. '2026-06-18T00:00:00Z')
    """
    return list_events(time_min, time_max)


@tool
def create_gcal_event(summary: str, start: str, end: str) -> dict[str, Any]:
    """Create a Google Calendar event.

    Args:
        summary: Event title
        start: RFC3339 start datetime
        end: RFC3339 end datetime
    """
    return create_event(summary, start, end)
