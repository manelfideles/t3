from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from t3.config import settings

_BASE = "https://intervals.icu/api/v1/athlete"


def _auth() -> tuple[str, str]:
    # Intervals.icu Basic Auth: username is the literal string "API_KEY",
    # password is the actual key value.
    return ("API_KEY", settings.intervals_api_key)


def _url(path: str) -> str:
    return f"{_BASE}/{settings.intervals_athlete_id}/{path}"


def get_athlete_settings() -> dict[str, Any]:
    with httpx.Client() as client:
        response = client.get(
            f"{_BASE}/{settings.intervals_athlete_id}",
            auth=_auth(),
        )
        response.raise_for_status()
        return response.json()


def get_events(oldest: str, newest: str) -> list[dict[str, Any]]:
    with httpx.Client() as client:
        response = client.get(
            _url("events"),
            auth=_auth(),
            params={"oldest": oldest, "newest": newest},
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []


def get_best_efforts(days: int = 28) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    oldest = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    newest = now.strftime("%Y-%m-%dT%H:%M:%S")
    with httpx.Client() as client:
        response = client.get(
            _url("activities"),
            auth=_auth(),
            params={"oldest": oldest, "newest": newest},
        )
        response.raise_for_status()
        activities = response.json()

    if not isinstance(activities, list):
        return {"avg_weekly_hours": None, "threshold_run_pace_per_km": None, "threshold_swim_pace_per_100m": None}

    total_seconds = sum(a.get("moving_time", 0) or 0 for a in activities)
    avg_weekly_hours = round(total_seconds / 3600 / (days / 7), 2)

    # Fastest pace from run activities >= 18 min (proxy for threshold effort)
    run_paces = []
    for a in activities:
        if a.get("type") == "Run":
            dist = a.get("distance", 0) or 0
            moving_time = a.get("moving_time", 0) or 0
            if dist > 0 and moving_time >= 1080:
                run_paces.append((moving_time / 60) / (dist / 1000))
    threshold_run = round(min(run_paces), 2) if run_paces else None

    # Fastest pace from swim activities >= 300m
    swim_paces = []
    for a in activities:
        if a.get("type") == "Swim":
            dist = a.get("distance", 0) or 0
            moving_time = a.get("moving_time", 0) or 0
            if dist >= 300 and moving_time > 0:
                swim_paces.append((moving_time / 60) / (dist / 100))
    threshold_swim = round(min(swim_paces), 2) if swim_paces else None

    return {
        "avg_weekly_hours": avg_weekly_hours,
        "threshold_run_pace_per_km": threshold_run,
        "threshold_swim_pace_per_100m": threshold_swim,
    }


def get_activities(limit: int = 10) -> list[dict[str, Any]]:
    # API requires 'oldest'; fetch last 90 days and slice to requested limit
    now = datetime.now(timezone.utc)
    oldest = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S")
    newest = now.strftime("%Y-%m-%dT%H:%M:%S")
    with httpx.Client() as client:
        response = client.get(
            _url("activities"),
            auth=_auth(),
            params={"oldest": oldest, "newest": newest},
        )
        response.raise_for_status()
        data = response.json()
        return data[:limit] if isinstance(data, list) else []


def update_workout_date(intervals_id: str, new_date: str) -> dict[str, Any]:
    start_dt = new_date if "T" in new_date else f"{new_date}T08:00:00"
    with httpx.Client() as client:
        response = client.put(
            _url(f"events/{intervals_id}"),
            auth=_auth(),
            json={"start_date_local": start_dt},
        )
        response.raise_for_status()
        return response.json()


def delete_workout(intervals_id: str) -> None:
    with httpx.Client() as client:
        response = client.delete(_url(f"events/{intervals_id}"), auth=_auth())
        response.raise_for_status()


def create_planned_workout(
    date: str,
    workout_type: str,
    title: str,
    description: str,
) -> dict[str, Any]:
    # API requires a full datetime string; append midnight if only a date was given
    start_dt = date if "T" in date else f"{date}T08:00:00"
    with httpx.Client() as client:
        response = client.post(
            _url("events"),
            auth=_auth(),
            json={
                "start_date_local": start_dt,
                "category": "WORKOUT",
                "type": workout_type,
                "name": f"T3 - {title}" if not title.startswith("T3 - ") else title,
                "description": description,
            },
        )
        response.raise_for_status()
        return response.json()
