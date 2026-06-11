from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from t3.db import AthleteRepo


class OnboardingState(Enum):
    START = auto()
    ASK_NAME = auto()
    ASK_AGE = auto()
    ASK_SEX = auto()
    ASK_EXPERIENCE = auto()
    ASK_WEEKLY_HOURS = auto()
    ASK_SWIM_BASELINE = auto()
    ASK_BIKE_BASELINE = auto()
    ASK_RUN_BASELINE = auto()
    ASK_UPCOMING_RACES = auto()
    ASK_INJURY_HISTORY = auto()
    ASK_NOTIFICATIONS = auto()
    COMPLETE = auto()


QUESTIONS: dict[OnboardingState, str] = {
    OnboardingState.ASK_NAME: "What's your name?",
    OnboardingState.ASK_AGE: "How old are you?",
    OnboardingState.ASK_SEX: "What's your biological sex? (male/female/other)",
    OnboardingState.ASK_EXPERIENCE: ("What's your triathlon experience level? (beginner/intermediate/advanced)"),
    OnboardingState.ASK_WEEKLY_HOURS: "How many hours per week can you train? (e.g. 8)",
    OnboardingState.ASK_SWIM_BASELINE: ("Describe your current swim fitness (e.g. '1500m in 30min')"),
    OnboardingState.ASK_BIKE_BASELINE: ("Describe your current bike fitness (e.g. '40km in 75min')"),
    OnboardingState.ASK_RUN_BASELINE: ("Describe your current run fitness (e.g. '10km in 55min')"),
    OnboardingState.ASK_UPCOMING_RACES: ("Any upcoming races? (e.g. 'Sprint triathlon July 2026') — or 'none'"),
    OnboardingState.ASK_INJURY_HISTORY: ("Any injury history I should know about? — or 'none'"),
    OnboardingState.ASK_NOTIFICATIONS: (
        "Notification preference: 'digest' (weekly summary) or 'full' (post-session + weekly)"
    ),
}

TRANSITIONS: dict[OnboardingState, OnboardingState] = {
    OnboardingState.START: OnboardingState.ASK_NAME,
    OnboardingState.ASK_NAME: OnboardingState.ASK_AGE,
    OnboardingState.ASK_AGE: OnboardingState.ASK_SEX,
    OnboardingState.ASK_SEX: OnboardingState.ASK_EXPERIENCE,
    OnboardingState.ASK_EXPERIENCE: OnboardingState.ASK_WEEKLY_HOURS,
    OnboardingState.ASK_WEEKLY_HOURS: OnboardingState.ASK_SWIM_BASELINE,
    OnboardingState.ASK_SWIM_BASELINE: OnboardingState.ASK_BIKE_BASELINE,
    OnboardingState.ASK_BIKE_BASELINE: OnboardingState.ASK_RUN_BASELINE,
    OnboardingState.ASK_RUN_BASELINE: OnboardingState.ASK_UPCOMING_RACES,
    OnboardingState.ASK_UPCOMING_RACES: OnboardingState.ASK_INJURY_HISTORY,
    OnboardingState.ASK_INJURY_HISTORY: OnboardingState.ASK_NOTIFICATIONS,
    OnboardingState.ASK_NOTIFICATIONS: OnboardingState.COMPLETE,
}


@dataclass
class OnboardingSession:
    state: OnboardingState = OnboardingState.START
    answers: dict[str, Any] = field(default_factory=dict)

    def is_complete(self) -> bool:
        return self.state == OnboardingState.COMPLETE

    def current_question(self) -> str | None:
        return QUESTIONS.get(self.state)

    def advance(self, answer: str) -> OnboardingState:
        key = self.state.name.lower().removeprefix("ask_")
        self.answers[key] = answer.strip()
        self.state = TRANSITIONS.get(self.state, OnboardingState.COMPLETE)
        return self.state


def flush_to_db(session: OnboardingSession, conn: sqlite3.Connection) -> int:
    a = session.answers
    return AthleteRepo(conn).save_profile(
        name=a.get("name"),
        age=int(a["age"]) if a.get("age", "").isdigit() else None,
        sex=a.get("sex"),
        experience_level=a.get("experience"),
        weekly_hours_json=json.dumps({"weekly": a.get("weekly_hours")}),
        swim_baseline=a.get("swim_baseline"),
        bike_baseline=a.get("bike_baseline"),
        run_baseline=a.get("run_baseline"),
        upcoming_races_json=json.dumps([a["upcoming_races"]]) if a.get("upcoming_races") else None,
        injury_history=a.get("injury_history"),
    )
