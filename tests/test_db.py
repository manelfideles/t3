import sqlite3

import pytest

from t3.db import EXPECTED_TABLES, AthleteRepo, TrainingPlanRepo, get_tables, init_db


def test_init_db_adds_missing_columns_to_existing_table(tmp_path) -> None:
    """init_db must migrate a pre-existing DB that lacks columns added after initial creation."""
    db_path = str(tmp_path / "old.db")
    # Create the table WITHOUT ftp_watts and the threshold columns — simulating an old DB
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE athlete_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            age INTEGER,
            sex TEXT,
            experience_level TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

    # init_db must detect and add the missing columns
    conn = init_db(db_path)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(athlete_profile)").fetchall()}
    for expected in ("ftp_watts", "threshold_run_pace_per_km", "threshold_swim_pace_per_100m", "avg_weekly_hours"):
        assert expected in cols, f"Migration failed to add column: {expected}"

    # Must also be usable — no OperationalError
    repo = AthleteRepo(conn)
    repo.save_profile(
        name="Alice", age=32, sex="female", experience_level="intermediate",
        weekly_hours_json=None, ftp_watts=240, threshold_run_pace_per_km=5.2,
        threshold_swim_pace_per_100m=2.1, avg_weekly_hours=7.5,
        upcoming_races_json=None, injury_history=None,
    )
    assert repo.load_latest() is not None


def test_schema_creates_all_five_tables() -> None:
    conn = init_db()
    assert get_tables(conn) == EXPECTED_TABLES


def test_athlete_profile_has_required_columns() -> None:
    conn = init_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(athlete_profile)").fetchall()}
    for required in ("name", "age", "sex", "experience_level", "created_at"):
        assert required in cols, f"Missing column: {required}"


def test_athlete_profile_has_typed_fitness_columns() -> None:
    conn = init_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(athlete_profile)").fetchall()}
    for col in ("ftp_watts", "threshold_run_pace_per_km", "threshold_swim_pace_per_100m", "avg_weekly_hours"):
        assert col in cols, f"Missing column: {col}"


def test_athlete_profile_has_no_freetext_baseline_columns() -> None:
    conn = init_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(athlete_profile)").fetchall()}
    for removed in ("swim_baseline", "bike_baseline", "run_baseline"):
        assert removed not in cols, f"Column should have been removed: {removed}"


def test_athlete_repo_save_and_load_typed_fields() -> None:
    conn = init_db()
    repo = AthleteRepo(conn)
    row_id = repo.save_profile(
        name="Alice",
        age=32,
        sex="female",
        experience_level="intermediate",
        weekly_hours_json=None,
        ftp_watts=240,
        threshold_run_pace_per_km=5.2,
        threshold_swim_pace_per_100m=2.1,
        avg_weekly_hours=7.5,
        upcoming_races_json='[{"name": "City Olympic"}]',
        injury_history=None,
    )
    assert row_id == 1
    profile = repo.load_latest()
    assert profile is not None
    assert profile.ftp_watts == 240
    assert profile.threshold_run_pace_per_km == pytest.approx(5.2)
    assert profile.threshold_swim_pace_per_100m == pytest.approx(2.1)
    assert profile.avg_weekly_hours == pytest.approx(7.5)
    assert profile.name == "Alice"


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
