from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from google import genai

from t3.config import settings
from t3.db import AthleteRepo, CalendarEventRepo, TrainingPlanRepo, init_db
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

    For each session: creates a GCal event, creates an Intervals.icu planned workout,
    then persists a calendar_events row with both external IDs.

    Returns {"scheduled": <count>} where count is the number of sessions written.
    """
    conn = init_db(settings.database_url)
    plan_repo = TrainingPlanRepo(conn)
    phases = plan_repo.load_latest()
    if not phases:
        return {"error": "No training plan found. Run generate_training_plan first."}

    calendar_repo = CalendarEventRepo(conn)
    scheduled = 0

    for phase in phases:
        blocks = json.loads(phase.blocks_json or "{}")
        phase_start = date.fromisoformat(blocks["start"])
        sessions = json.loads(phase.sessions_json or "[]")

        for session in sessions:
            week = session["week"]
            day_offset = _DAY_OFFSET.get(session["day"].lower(), 0)
            session_date = phase_start + timedelta(days=(week - 1) * 7 + day_offset)

            discipline = session["discipline"]
            session_type = session["type"]
            duration_min = session["duration_min"]
            intensity = session.get("intensity", "")
            notes = session.get("notes", "")

            summary = f"{discipline} – {session_type}"
            start_dt = datetime.fromisoformat(f"{session_date.isoformat()}T07:00:00")
            end_dt = start_dt + timedelta(minutes=duration_min)

            gcal_result = gcal.create_event(
                summary=summary,
                start=start_dt.isoformat(),
                end=end_dt.isoformat(),
                db_path=settings.database_url,
            )
            gcal_id = gcal_result["id"]

            workout_type = _DISCIPLINE_TO_WORKOUT_TYPE.get(discipline.lower(), discipline)
            description = f"Intensity: {intensity}"
            if notes:
                description += f"\n{notes}"

            intervals_result = intervals.create_planned_workout(
                date=session_date.isoformat(),
                workout_type=workout_type,
                title=summary,
                description=description,
            )
            intervals_id = intervals_result["id"]

            calendar_repo.insert(
                gcal_id=gcal_id,
                intervals_id=intervals_id,
                scheduled_at=session_date.isoformat(),
                event_type=discipline,
            )
            scheduled += 1

    return {"scheduled": scheduled}
