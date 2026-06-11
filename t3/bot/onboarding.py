from __future__ import annotations

import dataclasses
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from google import genai
from google.genai import types

from t3.config import settings
from t3.db import AthleteRepo
from t3.integrations.intervals import get_athlete_settings, get_best_efforts, get_events


@dataclass
class IntervalsDerivedProfile:
    name: str | None
    age: int | None
    sex: str | None
    ftp_watts: int | None
    weight_kg: float | None
    height_cm: float | None
    avg_weekly_hours: float | None
    threshold_run_pace_per_km: float | None
    threshold_swim_pace_per_100m: float | None
    upcoming_races: list[dict]
    injury_history: list[dict]
    experience_level: str | None


def _derive_experience_level(past_races: list[dict]) -> str:
    if not past_races:
        return "beginner"
    names = [r.get("name", "").lower() for r in past_races]
    full_im = sum(1 for n in names if "ironman" in n and "70.3" not in n)
    half_im = sum(1 for n in names if "70.3" in n)
    olympic = sum(1 for n in names if "olympic" in n)
    if full_im > 0:
        return "advanced"
    if half_im > 0:
        return "intermediate"
    if olympic > 0 or len(past_races) >= 3:
        return "intermediate"
    return "beginner"


def fetch_profile_from_intervals() -> IntervalsDerivedProfile:
    athlete = get_athlete_settings()

    now = datetime.now(timezone.utc)
    history_start = (now - timedelta(days=3 * 365)).strftime("%Y-%m-%dT%H:%M:%S")
    future_end = (now + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%S")
    now_str = now.strftime("%Y-%m-%dT%H:%M:%S")

    events = get_events(history_start, future_end)
    upcoming_races = [e for e in events if e.get("category") == "RACE" and e.get("start_date_local", "") >= now_str]
    injuries = [e for e in events if e.get("category") == "INJURED"]
    past_races = [e for e in events if e.get("category") == "RACE" and e.get("start_date_local", "") < now_str]

    efforts = get_best_efforts(days=28)

    return IntervalsDerivedProfile(
        name=athlete.get("name"),
        age=athlete.get("age"),
        sex=athlete.get("sex"),
        ftp_watts=athlete.get("ftp"),
        weight_kg=athlete.get("weight"),
        height_cm=athlete.get("height"),
        avg_weekly_hours=efforts.get("avg_weekly_hours"),
        threshold_run_pace_per_km=efforts.get("threshold_run_pace_per_km"),
        threshold_swim_pace_per_100m=efforts.get("threshold_swim_pace_per_100m"),
        upcoming_races=upcoming_races,
        injury_history=injuries,
        experience_level=_derive_experience_level(past_races),
    )


def format_confirmation_message(profile: IntervalsDerivedProfile) -> str:
    lines = ["*Your derived athlete profile:*\n"]
    if profile.name:
        lines.append(f"• Name: {profile.name}")
    if profile.age is not None:
        lines.append(f"• Age: {profile.age}")
    if profile.sex:
        lines.append(f"• Sex: {profile.sex}")
    if profile.experience_level:
        lines.append(f"• Experience: {profile.experience_level}")
    if profile.ftp_watts is not None:
        lines.append(f"• FTP: {profile.ftp_watts}W")
    if profile.avg_weekly_hours is not None:
        lines.append(f"• Avg weekly training hours: {profile.avg_weekly_hours}h")
    if profile.threshold_run_pace_per_km is not None:
        lines.append(f"• Threshold run pace: {profile.threshold_run_pace_per_km} min/km")
    if profile.threshold_swim_pace_per_100m is not None:
        lines.append(f"• Threshold swim pace: {profile.threshold_swim_pace_per_100m} min/100m")
    if profile.weight_kg is not None:
        lines.append(f"• Weight: {profile.weight_kg} kg")
    if profile.height_cm is not None:
        lines.append(f"• Height: {profile.height_cm} cm")
    race_count = len(profile.upcoming_races)
    lines.append(f"• Upcoming races: {race_count}")
    if profile.injury_history:
        lines.append(f"• Injury events on record: {len(profile.injury_history)}")
    lines.append("\nDoes this look right? Reply *yes* to proceed, or tell me what to correct.")
    return "\n".join(lines)


def apply_corrections(
    profile: IntervalsDerivedProfile,
    user_text: str,
    gemini_client: genai.Client,
) -> IntervalsDerivedProfile:
    profile_dict = dataclasses.asdict(profile)
    prompt = f"""The user wants to correct their athlete profile.

Current profile (JSON):
{json.dumps(profile_dict, indent=2)}

User correction: {user_text}

Apply the correction and return the updated profile as JSON with exactly the same keys."""

    response = gemini_client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )

    updated: dict[str, Any] = json.loads(response.text or "{}")
    field_names = {f.name for f in dataclasses.fields(IntervalsDerivedProfile)}
    merged = {k: updated.get(k, getattr(profile, k)) for k in field_names}
    return IntervalsDerivedProfile(**merged)


def flush_to_db(profile: IntervalsDerivedProfile, conn: sqlite3.Connection) -> int:
    return AthleteRepo(conn).save_profile(
        name=profile.name,
        age=profile.age,
        sex=profile.sex,
        experience_level=profile.experience_level,
        weekly_hours_json=None,
        ftp_watts=profile.ftp_watts,
        threshold_run_pace_per_km=profile.threshold_run_pace_per_km,
        threshold_swim_pace_per_100m=profile.threshold_swim_pace_per_100m,
        avg_weekly_hours=profile.avg_weekly_hours,
        upcoming_races_json=json.dumps(profile.upcoming_races) if profile.upcoming_races else None,
        injury_history=json.dumps(profile.injury_history) if profile.injury_history else None,
    )
