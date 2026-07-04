from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock

from t3.db import AthleteProfileRow
from t3.planner import generate_plan


def _mock_client(plan_dict: dict) -> MagicMock:
    """Return a Gemini client mock whose generate_content returns plan_dict as JSON text."""
    response = MagicMock()
    response.text = json.dumps(plan_dict)
    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


def _fixture_profile() -> AthleteProfileRow:
    return AthleteProfileRow(
        name="Alice",
        age=32,
        sex="female",
        experience_level="intermediate",
        weekly_hours=None,
        ftp_watts=240,
        threshold_run_pace_per_km=5.2,
        threshold_swim_pace_per_100m=2.1,
        avg_weekly_hours=7.5,
        upcoming_races=[{"name": "City Olympic", "date": "2026-09-20", "type": "olympic", "priority": "A"}],
        injury_history="None",
    )


def _fixture_plan() -> dict:
    phases = [
        {
            "name": "Base",
            "start": "2026-06-11",
            "end": "2026-07-22",
            "weeks": 6,
            "weekly_hours": 7.5,
            "sessions": [
                {
                    "week": 1,
                    "day": "Monday",
                    "discipline": "swim",
                    "type": "endurance",
                    "duration_min": 45,
                    "intensity": "zone2",
                    "notes": "Easy pace, focus on stroke mechanics",
                }
            ],
        },
        {
            "name": "Build",
            "start": "2026-07-23",
            "end": "2026-08-19",
            "weeks": 4,
            "weekly_hours": 9.0,
            "sessions": [],
        },
        {
            "name": "Peak",
            "start": "2026-08-20",
            "end": "2026-09-09",
            "weeks": 3,
            "weekly_hours": 8.0,
            "sessions": [],
        },
        {
            "name": "Race",
            "start": "2026-09-10",
            "end": "2026-09-20",
            "weeks": 1,
            "weekly_hours": 5.0,
            "sessions": [],
        },
    ]
    return {"phases": phases}


def test_generate_plan_returns_four_phases() -> None:
    plan = _fixture_plan()
    client = _mock_client(plan)
    result = generate_plan(_fixture_profile(), date(2026, 6, 11), client=client)

    assert "phases" in result
    assert len(result["phases"]) == 4


def test_generate_plan_phase_names_are_base_build_peak_race() -> None:
    plan = _fixture_plan()
    client = _mock_client(plan)
    result = generate_plan(_fixture_profile(), date(2026, 6, 11), client=client)

    names = [p["name"] for p in result["phases"]]
    assert names == ["Base", "Build", "Peak", "Race"]


def test_generate_plan_date_coverage_spans_today_to_race() -> None:
    today = date(2026, 6, 11)
    a_race = date(2026, 9, 20)
    plan = _fixture_plan()
    client = _mock_client(plan)
    result = generate_plan(_fixture_profile(), today, client=client)

    phases = result["phases"]
    plan_start = date.fromisoformat(phases[0]["start"])
    plan_end = date.fromisoformat(phases[-1]["end"])

    assert plan_start == today
    assert plan_end == a_race


def test_generate_plan_calls_gemini_once() -> None:
    client = _mock_client(_fixture_plan())
    generate_plan(_fixture_profile(), date(2026, 6, 11), client=client)
    client.models.generate_content.assert_called_once()


def test_generate_plan_prompt_includes_profile_and_guide(tmp_path, monkeypatch) -> None:
    """Verify the prompt sent to Gemini contains athlete data and the guide."""
    client = _mock_client(_fixture_plan())
    generate_plan(_fixture_profile(), date(2026, 6, 11), client=client)

    call_args = client.models.generate_content.call_args
    prompt: str = call_args.kwargs.get("contents") or call_args.args[1]

    assert "Alice" in prompt
    assert "intermediate" in prompt
    assert "Periodization Guide" in prompt
