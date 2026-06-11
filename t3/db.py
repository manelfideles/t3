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

EXPECTED_TABLES = frozenset({
    "athlete_profile",
    "training_plan",
    "calendar_events",
    "notification_prefs",
    "oauth_tokens",
})


def init_db(db_path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def get_tables(conn: sqlite3.Connection) -> frozenset[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return frozenset(row[0] for row in rows)
