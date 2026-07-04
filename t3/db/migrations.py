from __future__ import annotations

import sqlite3

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

CREATE TABLE IF NOT EXISTS conversation_state (
    chat_id INTEGER PRIMARY KEY,
    state TEXT NOT NULL,
    payload_json TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
        "conversation_state",
    }
)

# Columns that must exist on each table. Additive-only — never drop or rename.
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
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return frozenset(row[0] for row in rows)
