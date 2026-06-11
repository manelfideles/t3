from __future__ import annotations

import sqlite3
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS athlete_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    age INTEGER,
    sex TEXT,
    weight_kg REAL,
    height_cm REAL,
    experience_level TEXT,
    weekly_hours_json TEXT,
    swim_baseline TEXT,
    bike_baseline TEXT,
    run_baseline TEXT,
    upcoming_races_json TEXT,
    injury_history TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS training_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase TEXT NOT NULL,
    blocks_json TEXT,
    sessions_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gcal_id TEXT UNIQUE,
    intervals_id TEXT,
    scheduled_at TEXT NOT NULL,
    event_type TEXT,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS notification_prefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_mode INTEGER DEFAULT 1,
    post_session INTEGER DEFAULT 0,
    weather_warnings INTEGER DEFAULT 1,
    digest_day TEXT DEFAULT 'sunday',
    digest_time TEXT DEFAULT '20:00'
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT UNIQUE NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    expires_at TEXT
);
"""

EXPECTED_TABLES = frozenset(
    {
        "athlete_profile",
        "training_plan",
        "calendar_events",
        "notification_prefs",
        "oauth_tokens",
    }
)


def init_db(db_path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def get_tables(conn: sqlite3.Connection) -> frozenset[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    return frozenset(row[0] for row in rows)


@dataclass
class OAuthTokenRow:
    access_token: str
    refresh_token: str | None
    expires_at: str | None


class TokenRepo:
    """Read/write OAuth tokens for a single named service."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def store(
        self,
        service: str,
        access_token: str,
        refresh_token: str | None,
        expires_at: str | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO oauth_tokens (service, access_token, refresh_token, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(service) DO UPDATE SET
                access_token  = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at    = excluded.expires_at
            """,
            (service, access_token, refresh_token, expires_at),
        )
        self._conn.commit()

    def load(self, service: str) -> OAuthTokenRow | None:
        row = self._conn.execute(
            "SELECT access_token, refresh_token, expires_at FROM oauth_tokens WHERE service = ?",
            (service,),
        ).fetchone()
        if row is None:
            return None
        return OAuthTokenRow(access_token=row[0], refresh_token=row[1], expires_at=row[2])


class AthleteRepo:
    """Read/write athlete profile rows."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_profile(
        self,
        name: str | None,
        age: int | None,
        sex: str | None,
        experience_level: str | None,
        weekly_hours_json: str | None,
        swim_baseline: str | None,
        bike_baseline: str | None,
        run_baseline: str | None,
        upcoming_races_json: str | None,
        injury_history: str | None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO athlete_profile (
                name, age, sex, experience_level,
                weekly_hours_json, swim_baseline, bike_baseline, run_baseline,
                upcoming_races_json, injury_history
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                age,
                sex,
                experience_level,
                weekly_hours_json,
                swim_baseline,
                bike_baseline,
                run_baseline,
                upcoming_races_json,
                injury_history,
            ),
        )
        self._conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def load_latest(self) -> "AthleteProfileRow | None":
        row = self._conn.execute(
            """
            SELECT name, age, sex, experience_level,
                   weekly_hours_json, swim_baseline, bike_baseline, run_baseline,
                   upcoming_races_json, injury_history
            FROM athlete_profile ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return AthleteProfileRow(*row)


@dataclass
class AthleteProfileRow:
    name: str | None
    age: int | None
    sex: str | None
    experience_level: str | None
    weekly_hours_json: str | None
    swim_baseline: str | None
    bike_baseline: str | None
    run_baseline: str | None
    upcoming_races_json: str | None
    injury_history: str | None


@dataclass
class TrainingPlanRow:
    id: int
    phase: str
    blocks_json: str | None
    sessions_json: str | None
    created_at: str


class TrainingPlanRepo:
    """Persist and load training plan phases."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, phase: str, blocks_json: str | None, sessions_json: str | None) -> int:
        cursor = self._conn.execute(
            "INSERT INTO training_plan (phase, blocks_json, sessions_json) VALUES (?, ?, ?)",
            (phase, blocks_json, sessions_json),
        )
        self._conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def load_latest(self) -> list[TrainingPlanRow]:
        """Return all phases from the most recent plan generation (same created_at batch)."""
        latest_ts = self._conn.execute(
            "SELECT created_at FROM training_plan ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest_ts is None:
            return []
        rows = self._conn.execute(
            "SELECT id, phase, blocks_json, sessions_json, created_at FROM training_plan WHERE created_at = ? ORDER BY id",
            (latest_ts[0],),
        ).fetchall()
        return [TrainingPlanRow(*row) for row in rows]
