from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from google import genai

from t3.config import settings
from t3.db import AthleteRepo, CalendarEventRepo, TrainingPlanRepo, TrainingPlanRow, init_db
from t3.integrations import gcal, intervals
from t3.planner import generate_plan
from t3.tools.registry import tool

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


def schedule_sessions(phases: list[TrainingPlanRow]) -> list[ScheduledSession]:
    """Resolve (week, day) offsets to absolute dates for every session across phases.

    Pure: no I/O, no external calls. Takes DB rows, returns ScheduledSession objects
    with computed session_date and pre-formatted summary strings.
    """
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


@tool
def generate_training_plan() -> dict[str, Any]:
    """Generate a periodized training plan from the athlete profile and persist it.

    Reads the athlete profile from the database, calls Gemini to produce a
    Base/Build/Peak/Race plan through the first A-race date, and saves each
    phase to the training_plan table.

    Returns the full plan as a dict with a 'phases' key.
    """
    conn = init_db(settings.database_url)
    athlete_repo = AthleteRepo(conn)
    profile = athlete_repo.load_latest()
    if profile is None:
        return {"error": "No athlete profile found. Please complete onboarding first."}

    client = genai.Client(api_key=settings.gemini_api_key)
    plan = generate_plan(profile, date.today(), client=client)

    plan_repo = TrainingPlanRepo(conn)
    for phase in plan.get("phases", []):
        plan_repo.insert(
            phase=phase.get("name", ""),
            blocks_json=json.dumps({k: v for k, v in phase.items() if k not in ("name", "sessions")}),
            sessions_json=json.dumps(phase.get("sessions", [])),
        )

    return plan


@tool
def confirm_plan() -> dict[str, Any]:
    """Schedule each session from the latest training plan to GCal and Intervals.icu.

    Resolves (week, day) offsets to absolute dates, then for each session:
    creates a GCal event, creates an Intervals.icu planned workout, and writes
    a calendar_events row with both external IDs.

    Call this after the athlete has reviewed and approved the training plan
    from generate_training_plan.

    Returns {"scheduled": N} where N is the number of sessions written.
    Returns {"error": "..."} if no plan exists.
    """
    conn = init_db(settings.database_url)
    phases = TrainingPlanRepo(conn).load_latest()
    if not phases:
        return {"error": "No training plan found. Run generate_training_plan first."}

    calendar_repo = CalendarEventRepo(conn)
    scheduled = 0

    for s in schedule_sessions(phases):
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
            scheduled_at=s.session_date.isoformat(),
            event_type=s.discipline,
        )
        scheduled += 1

    return {"scheduled": scheduled}
