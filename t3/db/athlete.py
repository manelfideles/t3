from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass
class AthleteProfileRow:
    name: str | None
    age: int | None
    sex: str | None
    experience_level: str | None
    weekly_hours: dict | None
    ftp_watts: int | None
    threshold_run_pace_per_km: float | None
    threshold_swim_pace_per_100m: float | None
    avg_weekly_hours: float | None
    upcoming_races: list | None
    injury_history: str | None


class AthleteRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_profile(
        self,
        name: str | None,
        age: int | None,
        sex: str | None,
        experience_level: str | None,
        weekly_hours: dict | None,
        ftp_watts: int | None,
        threshold_run_pace_per_km: float | None,
        threshold_swim_pace_per_100m: float | None,
        avg_weekly_hours: float | None,
        upcoming_races: list | None,
        injury_history: str | None,
    ) -> int:
        weekly_hours_json = json.dumps(weekly_hours) if weekly_hours is not None else None
        upcoming_races_json = json.dumps(upcoming_races) if upcoming_races is not None else None
        cursor = self._conn.execute(
            """
            INSERT INTO athlete_profile (
                name, age, sex, experience_level,
                weekly_hours_json, ftp_watts, threshold_run_pace_per_km,
                threshold_swim_pace_per_100m, avg_weekly_hours,
                upcoming_races_json, injury_history
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                age,
                sex,
                experience_level,
                weekly_hours_json,
                ftp_watts,
                threshold_run_pace_per_km,
                threshold_swim_pace_per_100m,
                avg_weekly_hours,
                upcoming_races_json,
                injury_history,
            ),
        )
        self._conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def load_latest(self) -> AthleteProfileRow | None:
        row = self._conn.execute(
            """
            SELECT name, age, sex, experience_level,
                   weekly_hours_json, ftp_watts, threshold_run_pace_per_km,
                   threshold_swim_pace_per_100m, avg_weekly_hours,
                   upcoming_races_json, injury_history
            FROM athlete_profile ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        name, age, sex, experience_level, weekly_hours_json, ftp_watts, \
            threshold_run_pace_per_km, threshold_swim_pace_per_100m, avg_weekly_hours, \
            upcoming_races_json, injury_history = row
        return AthleteProfileRow(
            name=name,
            age=age,
            sex=sex,
            experience_level=experience_level,
            weekly_hours=json.loads(weekly_hours_json) if weekly_hours_json else None,
            ftp_watts=ftp_watts,
            threshold_run_pace_per_km=threshold_run_pace_per_km,
            threshold_swim_pace_per_100m=threshold_swim_pace_per_100m,
            avg_weekly_hours=avg_weekly_hours,
            upcoming_races=json.loads(upcoming_races_json) if upcoming_races_json else None,
            injury_history=injury_history,
        )
