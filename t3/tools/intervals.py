from __future__ import annotations

from typing import Any

import httpx

from t3.integrations.intervals import (
    create_planned_workout as _create_planned_workout,
    get_activities as _get_activities,
)
from t3.tools.registry import tool


def _shape_activity(raw: dict) -> dict:
    moving_time = raw.get("moving_time") or 0
    return {
        "id": raw.get("id", ""),
        "date": (raw.get("start_date_local") or "")[:10],
        "type": raw.get("type", ""),
        "name": raw.get("name", ""),
        "duration_min": round(moving_time / 60),
        "distance_m": raw.get("distance") or 0,
    }


def _shape_planned_workout(raw: dict) -> dict:
    return {
        "id": raw.get("id", ""),
        "date": (raw.get("start_date_local") or "")[:10],
        "type": raw.get("type", ""),
        "name": raw.get("name", ""),
    }


@tool
def get_activities(limit: int = 10, discipline: str = "all") -> list[dict[str, Any]] | dict[str, Any]:
    """Retrieve recent Intervals.icu training activities.

    Call this when the user asks about recent training, wants to review past
    sessions, or needs performance data (paces, durations, distances).

    limit: maximum activities to return (default 10).
    discipline: filter to "swim", "bike", "run", or "all" (default).
      When a discipline is specified, up to limit*3 activities are fetched
      before filtering to return a full result set.

    Returns a list of {id, date, type, name, duration_min, distance_m} dicts.
    Returns {"error": "not_connected", "action": "..."} if the API key is invalid.

    Do NOT call this to retrieve the training plan — use generate_training_plan.
    """
    try:
        if discipline == "all":
            raw = _get_activities(limit)
        else:
            raw = _get_activities(limit * 3)
            raw = [a for a in raw if a.get("type", "").lower() == discipline.lower()][:limit]
        return [_shape_activity(a) for a in raw]
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            return {"error": "not_connected", "action": "Ask the user to check their Intervals.icu API key."}
        raise


@tool
def create_planned_workout(date: str, workout_type: str, title: str, description: str) -> dict[str, Any]:
    """Write a single planned workout to Intervals.icu.

    Call this when the user explicitly asks to schedule one workout.
    To schedule an entire training plan use confirm_plan instead.

    date: ISO date string, e.g. "2026-06-15"
    workout_type: "Swim", "Ride", or "Run"
    title: short workout name, e.g. "Threshold bike"
    description: full workout details — sets, paces, or effort notes

    Returns {id, date, type, name} for the created workout.
    """
    return _shape_planned_workout(_create_planned_workout(date, workout_type, title, description))
