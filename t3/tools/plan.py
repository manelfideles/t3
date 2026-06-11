from __future__ import annotations

import json
from datetime import date
from typing import Any

from google import genai

from t3.config import settings
from t3.db import AthleteRepo, TrainingPlanRepo, init_db
from t3.planner import generate_plan
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
