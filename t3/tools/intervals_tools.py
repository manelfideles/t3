from typing import Any


def get_activities(limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve recent Intervals.icu activities.

    Args:
        limit: Maximum number of activities to return (default 10)
    """
    return []  # stub — full implementation in S6


def create_planned_workout(date: str, type: str, description: str) -> dict[str, Any]:
    """Write a planned workout to Intervals.icu.

    Args:
        date: ISO date string (e.g. '2026-06-11')
        type: Workout type (Swim, Bike, Run)
        description: Workout description
    """
    return {}  # stub — full implementation in S6


INTERVALS_FUNCTIONS = [get_activities, create_planned_workout]

INTERVALS_HANDLERS: dict[str, Any] = {
    "get_activities": get_activities,
    "create_planned_workout": create_planned_workout,
}
