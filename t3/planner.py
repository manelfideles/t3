from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from t3.config import settings
from t3.db import AthleteProfileRow

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
- Upcoming races (JSON): {profile.upcoming_races_json}
- Injury history: {profile.injury_history}

## Instructions
Today is {today.isoformat()}.
Generate a complete periodized training plan from today through the athlete's first A-race date.
The plan must have exactly 4 phases in order: Base, Build, Peak, Race.
Follow the phase allocation formula and discipline weighting rules from the guide.
Return valid JSON matching the schema provided.
"""


def generate_plan(profile: AthleteProfileRow, today: date, client: genai.Client | None = None) -> dict[str, Any]:
    """Call Gemini to produce a periodized training plan from the athlete profile.

    Returns a dict with a 'phases' key containing the structured plan.
    """
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
