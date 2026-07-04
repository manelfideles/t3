from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from t3.config import settings
from t3.db import AthleteProfileRow, TrainingPlanRow
from t3.integrations import gcal, intervals
from t3.logger import logger

_GUIDE_PATH = Path(__file__).parent / "knowledge" / "periodization.md"

_PLAN_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=["phases"],
    properties={
        "phases": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                required=["name", "start", "end", "weeks", "weekly_hours", "sessions"],
                properties={
                    "name": types.Schema(type=types.Type.STRING),
                    "start": types.Schema(type=types.Type.STRING),
                    "end": types.Schema(type=types.Type.STRING),
                    "weeks": types.Schema(type=types.Type.INTEGER),
                    "weekly_hours": types.Schema(type=types.Type.NUMBER),
                    "sessions": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            required=["week", "day", "discipline", "type", "duration_min", "intensity"],
                            properties={
                                "week": types.Schema(type=types.Type.INTEGER),
                                "day": types.Schema(type=types.Type.STRING),
                                "discipline": types.Schema(type=types.Type.STRING),
                                "type": types.Schema(type=types.Type.STRING),
                                "duration_min": types.Schema(type=types.Type.INTEGER),
                                "intensity": types.Schema(type=types.Type.STRING),
                                "notes": types.Schema(type=types.Type.STRING),
                            },
                        ),
                    ),
                },
            ),
        )
    },
)

_DAY_OFFSET = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_DISCIPLINE_TO_WORKOUT_TYPE = {
    "swim": "Swim",
    "bike": "Ride",
    "run": "Run",
}


@dataclass
class ScheduledSession:
    session_date: date
    discipline: str
    session_type: str
    duration_min: int
    intensity: str
    notes: str
    summary: str


@dataclass
class FailedSession:
    session_date: str
    discipline: str
    error: str


@dataclass
class ScheduleResult:
    scheduled: int
    failed: list[FailedSession]


def schedule_sessions(phases: list[TrainingPlanRow]) -> list[ScheduledSession]:
    result: list[ScheduledSession] = []
    for phase in phases:
        blocks = json.loads(phase.blocks_json or "{}")
        phase_start = date.fromisoformat(blocks["start"])
        for s in json.loads(phase.sessions_json or "[]"):
            day_offset = _DAY_OFFSET.get(s["day"].lower(), 0)
            session_date = phase_start + timedelta(days=(s["week"] - 1) * 7 + day_offset)
            discipline = s["discipline"]
            result.append(
                ScheduledSession(
                    session_date=session_date,
                    discipline=discipline,
                    session_type=s["type"],
                    duration_min=s["duration_min"],
                    intensity=s.get("intensity", ""),
                    notes=s.get("notes", ""),
                    summary=f"{discipline} – {s['type']}",
                )
            )
    return result


def schedule_plan(conn: sqlite3.Connection, phases: list[TrainingPlanRow]) -> ScheduleResult:
    from t3.db import CalendarRepo

    calendar_repo = CalendarRepo(conn)
    scheduled = 0
    failed: list[FailedSession] = []

    for s in schedule_sessions(phases):
        try:
            start_dt = datetime.fromisoformat(f"{s.session_date.isoformat()}T07:00:00")
            end_dt = start_dt + timedelta(minutes=s.duration_min)

            gcal_result = gcal.create_event(
                summary=s.summary,
                start=start_dt.isoformat(),
                end=end_dt.isoformat(),
                db_path=settings.database_url,
            )

            description = f"Intensity: {s.intensity}"
            if s.notes:
                description += f"\n{s.notes}"

            intervals_result = intervals.create_planned_workout(
                date=s.session_date.isoformat(),
                workout_type=_DISCIPLINE_TO_WORKOUT_TYPE.get(s.discipline.lower(), s.discipline),
                title=s.summary,
                description=description,
            )

            calendar_repo.insert(
                gcal_id=gcal_result["id"],
                intervals_id=intervals_result["id"],
                scheduled_at=start_dt.isoformat(),
                event_type=s.discipline,
            )
            scheduled += 1
        except Exception as exc:
            logger.warning("session %s/%s failed: %s", s.session_date, s.discipline, exc)
            failed.append(
                FailedSession(
                    session_date=s.session_date.isoformat(),
                    discipline=s.discipline,
                    error=str(exc),
                )
            )

    return ScheduleResult(scheduled=scheduled, failed=failed)


def _build_prompt(profile: AthleteProfileRow, today: date, guide: str) -> str:
    return f"""You are a triathlon coach. Use the periodization guide below to generate a structured training plan.

## Periodization Guide
{guide}

## Athlete Profile
- Name: {profile.name}
- Age: {profile.age}
- Sex: {profile.sex}
- Experience level: {profile.experience_level}
- Average weekly training hours: {profile.avg_weekly_hours}
- FTP (watts): {profile.ftp_watts}
- Threshold run pace (min/km): {profile.threshold_run_pace_per_km}
- Threshold swim pace (min/100m): {profile.threshold_swim_pace_per_100m}
- Upcoming races (JSON): {profile.upcoming_races}
- Injury history: {profile.injury_history}

## Instructions
Today is {today.isoformat()}.
Generate a complete periodized training plan from today through the athlete's first A-race date.
The plan must have exactly 4 phases in order: Base, Build, Peak, Race.
Follow the phase allocation formula and discipline weighting rules from the guide.
Return valid JSON matching the schema provided.
"""


def generate_plan(profile: AthleteProfileRow, today: date, client: genai.Client | None = None) -> dict[str, Any]:
    if client is None:
        client = genai.Client(api_key=settings.gemini_api_key)

    guide = _GUIDE_PATH.read_text()
    prompt = _build_prompt(profile, today, guide)

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_PLAN_SCHEMA,
        ),
    )

    raw = response.text or "{}"
    return json.loads(raw)
