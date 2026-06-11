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


def create_planned_workout(date: str, type: str, description: str) -> dict[str, Any]:
    # API requires a full datetime string; append midnight if only a date was given
    start_dt = date if "T" in date else f"{date}T08:00:00"
    with httpx.Client() as client:
        response = client.post(
            _url("events"),
            auth=_auth(),
            json={
                "start_date_local": start_dt,
                "category": "WORKOUT",
                "type": type,
                "name": description,
            },
        )
        response.raise_for_status()
        return response.json()
