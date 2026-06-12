from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from t3.db import AthleteProfileRow, TrainingPlanRepo, TrainingPlanRow, init_db


def _fixture_profile() -> AthleteProfileRow:
    return AthleteProfileRow(
        name="Alice",
        age=32,
        sex="female",
        experience_level="intermediate",
        weekly_hours_json=None,
        ftp_watts=240,
        threshold_run_pace_per_km=5.2,
        threshold_swim_pace_per_100m=2.1,
        avg_weekly_hours=7.5,
        upcoming_races_json='[{"name": "City Olympic", "date": "2026-09-20", "type": "olympic", "priority": "A"}]',
        injury_history="None",
    )


def _fixture_plan() -> dict:
    return {
        "phases": [
            {"name": "Base", "start": "2026-06-11", "end": "2026-07-22", "weeks": 6, "weekly_hours": 7.5, "sessions": []},
            {"name": "Build", "start": "2026-07-23", "end": "2026-08-19", "weeks": 4, "weekly_hours": 9.0, "sessions": []},
            {"name": "Peak", "start": "2026-08-20", "end": "2026-09-09", "weeks": 3, "weekly_hours": 8.0, "sessions": []},
            {"name": "Race", "start": "2026-09-10", "end": "2026-09-20", "weeks": 1, "weekly_hours": 5.0, "sessions": []},
        ]
    }


def test_generate_training_plan_persists_four_phases(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")

    from t3.db import AthleteRepo, init_db as _init_db

    conn = _init_db(db_path)
    repo = AthleteRepo(conn)
    profile = _fixture_profile()
    repo.save_profile(
        name=profile.name,
        age=profile.age,
        sex=profile.sex,
        experience_level=profile.experience_level,
        weekly_hours_json=profile.weekly_hours_json,
        ftp_watts=profile.ftp_watts,
        threshold_run_pace_per_km=profile.threshold_run_pace_per_km,
        threshold_swim_pace_per_100m=profile.threshold_swim_pace_per_100m,
        avg_weekly_hours=profile.avg_weekly_hours,
        upcoming_races_json=profile.upcoming_races_json,
        injury_history=profile.injury_history,
    )
    conn.close()

    plan_data = _fixture_plan()

    with (
        patch("t3.tools.plan.settings") as mock_settings,
        patch("t3.tools.plan.init_db") as mock_init_db,
        patch("t3.tools.plan.generate_plan") as mock_generate_plan,
        patch("t3.tools.plan.genai"),
    ):
        mock_settings.database_url = db_path
        mock_settings.gemini_api_key = "fake"

        real_conn = _init_db(db_path)
        mock_init_db.return_value = real_conn
        mock_generate_plan.return_value = plan_data

        from t3.tools.plan import generate_training_plan

        result = generate_training_plan()

    assert "phases" in result
    assert len(result["phases"]) == 4

    plan_repo = TrainingPlanRepo(real_conn)
    rows = plan_repo.load_latest()
    assert len(rows) == 4
    assert [r.phase for r in rows] == ["Base", "Build", "Peak", "Race"]


def test_generate_training_plan_returns_error_when_no_profile(tmp_path) -> None:
    db_path = str(tmp_path / "empty.db")

    from t3.db import init_db as _init_db

    real_conn = _init_db(db_path)

    with (
        patch("t3.tools.plan.settings") as mock_settings,
        patch("t3.tools.plan.init_db") as mock_init_db,
        patch("t3.tools.plan.genai"),
    ):
        mock_settings.database_url = db_path
        mock_settings.gemini_api_key = "fake"
        mock_init_db.return_value = real_conn

        from t3.tools.plan import generate_training_plan

        result = generate_training_plan()

    assert "error" in result


def test_generate_training_plan_registered_in_registry() -> None:
    import t3.tools.plan  # noqa: F401
    from t3.tools.registry import REGISTRY

    names = [getattr(fn, "__name__", None) for fn in REGISTRY.functions]
    assert "generate_training_plan" in names


def test_schedule_sessions_computes_absolute_dates() -> None:
    from t3.tools.plan import schedule_sessions

    phases = [
        TrainingPlanRow(
            id=1,
            phase="Base",
            blocks_json='{"start": "2026-06-15", "end": "2026-06-28", "weeks": 2, "weekly_hours": 7.5}',
            sessions_json=json.dumps([
                {"week": 1, "day": "monday", "discipline": "swim", "type": "easy", "duration_min": 45, "intensity": "low"},
                {"week": 1, "day": "wednesday", "discipline": "run", "type": "threshold", "duration_min": 60, "intensity": "high"},
                {"week": 2, "day": "saturday", "discipline": "bike", "type": "long", "duration_min": 120, "intensity": "moderate"},
            ]),
            created_at="2026-06-12T00:00:00",
        )
    ]

    sessions = schedule_sessions(phases)

    assert len(sessions) == 3
    assert sessions[0].session_date == date(2026, 6, 15)   # week 1, monday
    assert sessions[0].summary == "swim – easy"
    assert sessions[1].session_date == date(2026, 6, 17)   # week 1, wednesday
    assert sessions[2].session_date == date(2026, 6, 27)   # week 2, saturday


def test_schedule_sessions_empty_phases_returns_empty() -> None:
    from t3.tools.plan import schedule_sessions
    assert schedule_sessions([]) == []


def _fixture_plan_with_sessions() -> dict:
    return {
        "phases": [
            {
                "name": "Base",
                "start": "2026-06-15",
                "end": "2026-06-28",
                "weeks": 2,
                "weekly_hours": 7.5,
                "sessions": [
                    {
                        "week": 1,
                        "day": "monday",
                        "discipline": "swim",
                        "type": "easy",
                        "duration_min": 45,
                        "intensity": "low",
                        "notes": "Warm up drills",
                    },
                    {
                        "week": 1,
                        "day": "wednesday",
                        "discipline": "run",
                        "type": "threshold",
                        "duration_min": 60,
                        "intensity": "high",
                        "notes": "",
                    },
                ],
            }
        ]
    }


def test_confirm_plan_schedules_sessions(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")

    from t3.db import AthleteRepo, CalendarEventRepo, TrainingPlanRepo, init_db as _init_db

    conn = _init_db(db_path)
    athlete_repo = AthleteRepo(conn)
    profile = _fixture_profile()
    athlete_repo.save_profile(
        name=profile.name,
        age=profile.age,
        sex=profile.sex,
        experience_level=profile.experience_level,
        weekly_hours_json=profile.weekly_hours_json,
        ftp_watts=profile.ftp_watts,
        threshold_run_pace_per_km=profile.threshold_run_pace_per_km,
        threshold_swim_pace_per_100m=profile.threshold_swim_pace_per_100m,
        avg_weekly_hours=profile.avg_weekly_hours,
        upcoming_races_json=profile.upcoming_races_json,
        injury_history=profile.injury_history,
    )

    plan_data = _fixture_plan_with_sessions()
    plan_repo = TrainingPlanRepo(conn)
    for phase in plan_data["phases"]:
        plan_repo.insert(
            phase=phase["name"],
            blocks_json=json.dumps({k: v for k, v in phase.items() if k not in ("name", "sessions")}),
            sessions_json=json.dumps(phase["sessions"]),
        )
    conn.close()

    gcal_responses = [{"id": "gcal-001"}, {"id": "gcal-002"}]
    intervals_responses = [{"id": "int-001"}, {"id": "int-002"}]

    real_conn = None

    def _fake_init_db(path):
        nonlocal real_conn
        from t3.db import init_db as _init_db
        real_conn = _init_db(path)
        return real_conn

    with (
        patch("t3.tools.plan.settings") as mock_settings,
        patch("t3.tools.plan.init_db", side_effect=_fake_init_db),
        patch("t3.tools.plan.gcal.create_event", side_effect=gcal_responses) as mock_gcal,
        patch("t3.tools.plan.intervals.create_planned_workout", side_effect=intervals_responses) as mock_intervals,
    ):
        mock_settings.database_url = db_path

        from t3.tools.plan import confirm_plan

        result = confirm_plan()

    assert result == {"scheduled": 2}
    assert mock_gcal.call_count == 2
    assert mock_intervals.call_count == 2

    assert real_conn is not None
    cal_repo = CalendarEventRepo(real_conn)
    assert cal_repo.count() == 2
