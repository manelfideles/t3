from __future__ import annotations

import dataclasses
import json
from datetime import date
from typing import Any

from google import genai

from t3.config import settings
from t3.db import AthleteRepo, TrainingPlanRepo, init_db
from t3.planner import generate_plan, schedule_plan, schedule_sessions
from t3.tools.registry import tool


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

    Delegates to schedule_plan() in t3.planner. Best-effort: failed sessions are
    reported but do not abort the run.

    Call this after the athlete has reviewed and approved the training plan
    from generate_training_plan.

    Returns {"scheduled": N, "failed": [...]} where N is the number of sessions written.
    Returns {"error": "..."} if no plan exists.
    """
    conn = init_db(settings.database_url)
    phases = TrainingPlanRepo(conn).load_latest()
    if not phases:
        return {"error": "No training plan found. Run generate_training_plan first."}

    result = schedule_plan(conn, phases)
    return {
        "scheduled": result.scheduled,
        "failed": [dataclasses.asdict(f) for f in result.failed],
    }
