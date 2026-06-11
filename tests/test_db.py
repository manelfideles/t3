import sqlite3

import pytest

from t3.db import EXPECTED_TABLES, TrainingPlanRepo, get_tables, init_db


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
    conn.execute("INSERT INTO calendar_events (gcal_id, scheduled_at) VALUES ('evt1', '2026-06-11T08:00:00')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO calendar_events (gcal_id, scheduled_at) VALUES ('evt1', '2026-06-12T08:00:00')")


def test_init_db_is_idempotent() -> None:
    conn = init_db()
    # Running schema again should not raise or duplicate tables
    conn.executescript("CREATE TABLE IF NOT EXISTS athlete_profile (id INTEGER PRIMARY KEY AUTOINCREMENT);")
    assert get_tables(conn) == EXPECTED_TABLES


def test_training_plan_repo_insert_and_load_latest() -> None:
    conn = init_db()
    repo = TrainingPlanRepo(conn)

    repo.insert("Base", '{"weeks":8}', '[]')
    repo.insert("Build", '{"weeks":6}', '[]')
    repo.insert("Peak", '{"weeks":3}', '[]')
    repo.insert("Race", '{"weeks":1}', '[]')

    rows = repo.load_latest()
    assert len(rows) == 4
    assert [r.phase for r in rows] == ["Base", "Build", "Peak", "Race"]
    assert rows[0].blocks_json == '{"weeks":8}'


def test_training_plan_repo_load_latest_returns_empty_when_no_rows() -> None:
    conn = init_db()
    repo = TrainingPlanRepo(conn)
    assert repo.load_latest() == []


def test_training_plan_repo_load_latest_returns_most_recent_batch() -> None:
    """load_latest groups by created_at; only the latest timestamp batch is returned."""
    conn = init_db()
    repo = TrainingPlanRepo(conn)

    # First batch — insert with an explicit older timestamp
    conn.execute(
        "INSERT INTO training_plan (phase, blocks_json, sessions_json, created_at) VALUES (?, ?, ?, ?)",
        ("Base", "{}", "[]", "2026-01-01 00:00:00"),
    )
    conn.commit()

    # Second batch — inserted via repo (uses CURRENT_TIMESTAMP)
    repo.insert("Base", '{"weeks":8}', "[]")
    repo.insert("Build", '{"weeks":6}', "[]")

    rows = repo.load_latest()
    assert len(rows) == 2
    assert rows[0].phase == "Base"
    assert rows[1].phase == "Build"
