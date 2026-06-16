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
    ftp_watts INTEGER,
    threshold_run_pace_per_km REAL,
    threshold_swim_pace_per_100m REAL,
    avg_weekly_hours REAL,
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

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT UNIQUE NOT NULL,
    value TEXT
);
"""

EXPECTED_TABLES = frozenset(
    {
        "athlete_profile",
        "training_plan",
        "calendar_events",
        "notification_prefs",
        "oauth_tokens",
        "sync_state",
    }
)


# Columns that must exist on each table. Any column present here but missing
# from an existing table is added via ALTER TABLE so old DBs are never stranded.
_REQUIRED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "athlete_profile": [
        ("name", "TEXT"),
        ("age", "INTEGER"),
        ("sex", "TEXT"),
        ("weight_kg", "REAL"),
        ("height_cm", "REAL"),
        ("experience_level", "TEXT"),
        ("weekly_hours_json", "TEXT"),
        ("ftp_watts", "INTEGER"),
        ("threshold_run_pace_per_km", "REAL"),
        ("threshold_swim_pace_per_100m", "REAL"),
        ("avg_weekly_hours", "REAL"),
        ("upcoming_races_json", "TEXT"),
        ("injury_history", "TEXT"),
        ("created_at", "TEXT"),
        ("updated_at", "TEXT"),
    ],
    "training_plan": [
        ("phase", "TEXT"),
        ("blocks_json", "TEXT"),
        ("sessions_json", "TEXT"),
        ("created_at", "TEXT"),
    ],
    "calendar_events": [
        ("gcal_id", "TEXT"),
        ("intervals_id", "TEXT"),
        ("scheduled_at", "TEXT"),
        ("event_type", "TEXT"),
        ("last_synced_at", "TEXT"),
    ],
    "notification_prefs": [
        ("digest_mode", "INTEGER"),
        ("post_session", "INTEGER"),
        ("weather_warnings", "INTEGER"),
        ("digest_day", "TEXT"),
        ("digest_time", "TEXT"),
    ],
    "oauth_tokens": [
        ("service", "TEXT"),
        ("access_token", "TEXT"),
        ("refresh_token", "TEXT"),
        ("expires_at", "TEXT"),
    ],
}


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Add any columns present in _REQUIRED_COLUMNS that are missing from existing tables."""
    for table, columns in _REQUIRED_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col_name, col_type in columns:
            if col_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
    conn.commit()


def init_db(db_path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    _apply_migrations(conn)
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
        ftp_watts: int | None,
        threshold_run_pace_per_km: float | None,
        threshold_swim_pace_per_100m: float | None,
        avg_weekly_hours: float | None,
        upcoming_races_json: str | None,
        injury_history: str | None,
    ) -> int:
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

    def load_latest(self) -> "AthleteProfileRow | None":
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
        return AthleteProfileRow(*row)


@dataclass
class AthleteProfileRow:
    name: str | None
    age: int | None
    sex: str | None
    experience_level: str | None
    weekly_hours_json: str | None
    ftp_watts: int | None
    threshold_run_pace_per_km: float | None
    threshold_swim_pace_per_100m: float | None
    avg_weekly_hours: float | None
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


class CalendarEventRepo:
    """Read/write calendar_events rows written by confirm_plan."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, gcal_id: str, intervals_id: str, scheduled_at: str, event_type: str) -> None:
        self._conn.execute(
            "INSERT INTO calendar_events (gcal_id, intervals_id, scheduled_at, event_type) VALUES (?, ?, ?, ?)",
            (gcal_id, intervals_id, scheduled_at, event_type),
        )
        self._conn.commit()

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()
        return row[0] if row else 0

    def update_last_synced_at(self, gcal_id: str, last_synced_at: str) -> None:
        self._conn.execute(
            "UPDATE calendar_events SET last_synced_at = ? WHERE gcal_id = ?",
            (last_synced_at, gcal_id),
        )
        self._conn.commit()

    def all_scheduled_at(self) -> dict[str, str]:
        """Return {gcal_id: scheduled_at} for all known events."""
        rows = self._conn.execute("SELECT gcal_id, scheduled_at FROM calendar_events").fetchall()
        return {row[0]: row[1] for row in rows}


class SyncStateRepo:
    """Read/write the sync cursor (last_polled_at) from the sync_state table."""

    _KEY = "last_polled_at"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_last_polled_at(self) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM sync_state WHERE key = ?", (self._KEY,)
        ).fetchone()
        return row[0] if row else None

    def set_last_polled_at(self, value: str) -> None:
        self._conn.execute(
            "INSERT INTO sync_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self._KEY, value),
        )
        self._conn.commit()
