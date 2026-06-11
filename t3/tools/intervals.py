from typing import Any

from t3.integrations.intervals import (
    create_planned_workout as _create_planned_workout,
    get_activities as _get_activities,
)
from t3.tools.registry import tool


@tool
def get_activities(limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve recent Intervals.icu activities.

    Args:
        limit: Maximum number of activities to return (default 10)
    """
    return _get_activities(limit)


@tool
def create_planned_workout(date: str, type: str, title: str, description: str) -> dict[str, Any]:
    """Write a planned workout to Intervals.icu.

    Args:
        date: ISO date string (e.g. '2026-06-11')
        type: Workout type (Swim, Bike, Run)
        title: Short workout name (e.g. 'Easy run')
        description: Full workout description
    """
    return _create_planned_workout(date, type, title, description)
