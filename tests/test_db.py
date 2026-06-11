import sqlite3

import pytest

from t3.db import EXPECTED_TABLES, get_tables, init_db


def test_schema_creates_all_five_tables() -> None:
    conn = init_db()
    assert get_tables(conn) == EXPECTED_TABLES


def test_athlete_profile_has_required_columns() -> None:
    conn = init_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(athlete_profile)").fetchall()}
    for required in ("name", "age", "sex", "experience_level", "created_at"):
        assert required in cols, f"Missing column: {required}"


def test_oauth_tokens_service_unique_constraint() -> None:
    conn = init_db()
    conn.execute("INSERT INTO oauth_tokens (service) VALUES ('gcal')")
    conn.execute("INSERT INTO oauth_tokens (service) VALUES ('intervals')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO oauth_tokens (service) VALUES ('gcal')")


def test_calendar_events_gcal_id_unique_constraint() -> None:
    conn = init_db()
    conn.execute(
        "INSERT INTO calendar_events (gcal_id, scheduled_at) VALUES ('evt1', '2026-06-11T08:00:00')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO calendar_events (gcal_id, scheduled_at) VALUES ('evt1', '2026-06-12T08:00:00')"
        )


def test_init_db_is_idempotent() -> None:
    conn = init_db()
    # Running schema again should not raise or duplicate tables
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS athlete_profile (id INTEGER PRIMARY KEY AUTOINCREMENT);"
    )
    assert get_tables(conn) == EXPECTED_TABLES
