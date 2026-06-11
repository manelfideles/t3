from typing import Any


def get_gcal_events(time_min: str = "", time_max: str = "") -> list[dict[str, Any]]:
    """List Google Calendar events within a time range.

    Args:
        time_min: RFC3339 start datetime (e.g. '2026-06-11T00:00:00Z')
        time_max: RFC3339 end datetime (e.g. '2026-06-18T00:00:00Z')
    """
    return []  # stub — full implementation in S5


def create_gcal_event(summary: str, start: str, end: str) -> dict[str, Any]:
    """Create a Google Calendar event.

    Args:
        summary: Event title
        start: RFC3339 start datetime
        end: RFC3339 end datetime
    """
    return {}  # stub — full implementation in S5


GCAL_FUNCTIONS = [get_gcal_events, create_gcal_event]

GCAL_HANDLERS: dict[str, Any] = {
    "get_gcal_events": get_gcal_events,
    "create_gcal_event": create_gcal_event,
}
