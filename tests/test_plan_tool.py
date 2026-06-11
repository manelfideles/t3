from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from t3.db import AthleteProfileRow, TrainingPlanRepo, init_db


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
