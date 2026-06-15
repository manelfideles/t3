from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from t3.bot.onboarding import (
    IntervalsDerivedProfile,
    _derive_experience_level,
    _extract_age,
    _extract_ftp,
    _extract_height_cm,
    _normalise_sex,
    apply_corrections,
    fetch_profile_from_intervals,
    flush_to_db,
    format_confirmation_message,
)
from t3.db import AthleteRepo, init_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ATHLETE = {
    "name": "Manuel",
    "age": 32,
    "sex": "male",
    "ftp": 240,
    "weight": 74.5,
    "height": 178,
}

_EVENTS = [
    # upcoming race — real API uses RACE_A/B/C
    {"category": "RACE_A", "name": "City Olympic", "start_date_local": "2026-09-20T08:00:00"},
    # past race
    {"category": "RACE_C", "name": "Sprint Tri 2025", "start_date_local": "2025-06-01T08:00:00"},
    # injury
    {"category": "INJURED", "name": "Knee tendinitis", "start_date_local": "2025-03-01T00:00:00"},
]

_EFFORTS = {
    "avg_weekly_hours": 8.5,
    "threshold_run_pace_per_km": 4.8,
    "threshold_swim_pace_per_100m": 1.9,
}


def _fixture_profile() -> IntervalsDerivedProfile:
    return IntervalsDerivedProfile(
        name="Manuel",
        age=32,
        sex="male",
        ftp_watts=240,
        weight_kg=74.5,
        height_cm=178.0,
        avg_weekly_hours=8.5,
        threshold_run_pace_per_km=4.8,
        threshold_swim_pace_per_100m=1.9,
        upcoming_races=[{"category": "RACE", "name": "City Olympic", "start_date_local": "2026-09-20T08:00:00"}],
        injury_history=[{"category": "INJURED", "name": "Knee tendinitis"}],
        experience_level="beginner",
    )


# ---------------------------------------------------------------------------
# _derive_experience_level
# ---------------------------------------------------------------------------


def test_derive_experience_no_races_returns_beginner() -> None:
    assert _derive_experience_level([]) == "beginner"


def test_derive_experience_sprint_only_returns_beginner() -> None:
    assert _derive_experience_level([{"name": "Sprint Tri 2025"}]) == "beginner"


def test_derive_experience_olympic_returns_intermediate() -> None:
    assert _derive_experience_level([{"name": "City Olympic Tri"}]) == "intermediate"


def test_derive_experience_three_or_more_races_returns_intermediate() -> None:
    races = [{"name": "Sprint"}, {"name": "Sprint"}, {"name": "Sprint"}]
    assert _derive_experience_level(races) == "intermediate"


def test_derive_experience_half_ironman_returns_intermediate() -> None:
    assert _derive_experience_level([{"name": "Ironman 70.3 Cascais"}]) == "intermediate"


def test_derive_experience_full_ironman_returns_advanced() -> None:
    assert _derive_experience_level([{"name": "Ironman Wales"}]) == "advanced"


# ---------------------------------------------------------------------------
# _extract_ftp / _extract_age / _normalise_sex / _extract_height_cm
# ---------------------------------------------------------------------------


def test_extract_ftp_reads_sport_settings_ride() -> None:
    athlete = {"sportSettings": [{"types": ["Ride", "VirtualRide"], "ftp": 239, "mmp_model": None}]}
    assert _extract_ftp(athlete) == 239


def test_extract_ftp_falls_back_to_mmp_model() -> None:
    athlete = {"sportSettings": [{"types": ["Ride"], "ftp": None, "mmp_model": {"ftp": 243}}]}
    assert _extract_ftp(athlete) == 243


def test_extract_ftp_falls_back_to_top_level_ftp() -> None:
    assert _extract_ftp({"ftp": 240}) == 240


def test_extract_ftp_returns_none_when_absent() -> None:
    assert _extract_ftp({}) is None


def test_extract_age_from_dob() -> None:
    athlete = {"icu_date_of_birth": "2000-03-18"}
    age = _extract_age(athlete)
    assert age is not None and 25 <= age <= 27


def test_extract_age_falls_back_to_age_field() -> None:
    assert _extract_age({"age": 32}) == 32


def test_normalise_sex_upper_M() -> None:
    assert _normalise_sex("M") == "male"


def test_normalise_sex_upper_F() -> None:
    assert _normalise_sex("F") == "female"


def test_normalise_sex_already_word() -> None:
    assert _normalise_sex("male") == "male"


def test_normalise_sex_none() -> None:
    assert _normalise_sex(None) is None


def test_extract_height_cm_converts_meters() -> None:
    assert _extract_height_cm({"height": 1.75}) == pytest.approx(175.0)


def test_extract_height_cm_passes_through_cm() -> None:
    assert _extract_height_cm({"height": 178}) == pytest.approx(178.0)


def test_extract_height_cm_none() -> None:
    assert _extract_height_cm({}) is None


# ---------------------------------------------------------------------------
# fetch_profile_from_intervals
# ---------------------------------------------------------------------------


def test_fetch_profile_returns_intervals_derived_profile() -> None:
    with (
        patch("t3.bot.onboarding.get_athlete_settings", return_value=_ATHLETE),
        patch("t3.bot.onboarding.get_events", return_value=_EVENTS),
        patch("t3.bot.onboarding.get_best_efforts", return_value=_EFFORTS),
    ):
        profile = fetch_profile_from_intervals()

    assert isinstance(profile, IntervalsDerivedProfile)


def test_fetch_profile_maps_athlete_fields() -> None:
    with (
        patch("t3.bot.onboarding.get_athlete_settings", return_value=_ATHLETE),
        patch("t3.bot.onboarding.get_events", return_value=_EVENTS),
        patch("t3.bot.onboarding.get_best_efforts", return_value=_EFFORTS),
    ):
        profile = fetch_profile_from_intervals()

    assert profile.name == "Manuel"
    assert profile.age == 32
    assert profile.ftp_watts == 240
    assert profile.weight_kg == 74.5


def test_fetch_profile_maps_best_effort_fields() -> None:
    with (
        patch("t3.bot.onboarding.get_athlete_settings", return_value=_ATHLETE),
        patch("t3.bot.onboarding.get_events", return_value=_EVENTS),
        patch("t3.bot.onboarding.get_best_efforts", return_value=_EFFORTS),
    ):
        profile = fetch_profile_from_intervals()

    assert profile.avg_weekly_hours == 8.5
    assert profile.threshold_run_pace_per_km == pytest.approx(4.8)
    assert profile.threshold_swim_pace_per_100m == pytest.approx(1.9)


def test_fetch_profile_detects_race_with_race_a_category() -> None:
    events_with_lowercase = [
        {"category": "race_a", "name": "Sunday Sprint", "start_date_local": "2026-09-14T08:00:00"},
    ]
    with (
        patch("t3.bot.onboarding.get_athlete_settings", return_value=_ATHLETE),
        patch("t3.bot.onboarding.get_events", return_value=events_with_lowercase),
        patch("t3.bot.onboarding.get_best_efforts", return_value=_EFFORTS),
    ):
        profile = fetch_profile_from_intervals()
    assert len(profile.upcoming_races) == 1
    assert profile.upcoming_races[0]["name"] == "Sunday Sprint"


def test_fetch_profile_separates_upcoming_and_past_races() -> None:
    with (
        patch("t3.bot.onboarding.get_athlete_settings", return_value=_ATHLETE),
        patch("t3.bot.onboarding.get_events", return_value=_EVENTS),
        patch("t3.bot.onboarding.get_best_efforts", return_value=_EFFORTS),
    ):
        profile = fetch_profile_from_intervals()

    assert len(profile.upcoming_races) == 1
    assert profile.upcoming_races[0]["name"] == "City Olympic"


def test_fetch_profile_captures_injury_history() -> None:
    with (
        patch("t3.bot.onboarding.get_athlete_settings", return_value=_ATHLETE),
        patch("t3.bot.onboarding.get_events", return_value=_EVENTS),
        patch("t3.bot.onboarding.get_best_efforts", return_value=_EFFORTS),
    ):
        profile = fetch_profile_from_intervals()

    assert len(profile.injury_history) == 1
    assert "Knee" in profile.injury_history[0]["name"]


def test_fetch_profile_derives_experience_level() -> None:
    with (
        patch("t3.bot.onboarding.get_athlete_settings", return_value=_ATHLETE),
        patch("t3.bot.onboarding.get_events", return_value=_EVENTS),
        patch("t3.bot.onboarding.get_best_efforts", return_value=_EFFORTS),
    ):
        profile = fetch_profile_from_intervals()

    # _EVENTS has one past sprint race → beginner
    assert profile.experience_level == "beginner"


# ---------------------------------------------------------------------------
# format_confirmation_message
# ---------------------------------------------------------------------------


def test_format_confirmation_message_contains_all_key_fields() -> None:
    profile = _fixture_profile()
    msg = format_confirmation_message(profile)

    assert "Manuel" in msg
    assert "240" in msg   # FTP
    assert "4:48" in msg  # run pace: 4.8 min/km → 4:48
    assert "1:54" in msg  # swim pace: 1.9 min/100m → 1:54
    assert "8.5" in msg   # weekly hours
    assert "yes" in msg.lower()


def test_format_confirmation_message_shows_upcoming_race_count() -> None:
    profile = _fixture_profile()
    msg = format_confirmation_message(profile)
    assert "1" in msg  # 1 upcoming race


def test_format_confirmation_message_shows_injury_count_when_present() -> None:
    profile = _fixture_profile()
    msg = format_confirmation_message(profile)
    assert "Injury" in msg or "injury" in msg


def test_format_confirmation_message_omits_none_fields() -> None:
    profile = IntervalsDerivedProfile(
        name=None,
        age=None,
        sex=None,
        ftp_watts=None,
        weight_kg=None,
        height_cm=None,
        avg_weekly_hours=None,
        threshold_run_pace_per_km=None,
        threshold_swim_pace_per_100m=None,
        upcoming_races=[],
        injury_history=[],
        experience_level=None,
    )
    msg = format_confirmation_message(profile)
    # Should not blow up and should still have confirmation prompt
    assert "yes" in msg.lower()


# ---------------------------------------------------------------------------
# apply_corrections
# ---------------------------------------------------------------------------


def _mock_gemini_client(response_dict: dict) -> MagicMock:
    response = MagicMock()
    response.text = json.dumps(response_dict)
    client = MagicMock(spec=["models"])
    client.models.generate_content.return_value = response
    return client


def test_apply_corrections_updates_ftp() -> None:
    profile = _fixture_profile()
    updated_dict = {
        **{f.name: getattr(profile, f.name) for f in profile.__dataclass_fields__.values()},  # type: ignore[attr-defined]
        "ftp_watts": 260,
    }
    client = _mock_gemini_client(updated_dict)

    result = apply_corrections(profile, "my FTP is actually 260", client)

    assert result.ftp_watts == 260
    client.models.generate_content.assert_called_once()


def test_apply_corrections_preserves_unchanged_fields() -> None:
    profile = _fixture_profile()
    updated_dict = {
        **{f.name: getattr(profile, f.name) for f in profile.__dataclass_fields__.values()},  # type: ignore[attr-defined]
        "ftp_watts": 260,
    }
    client = _mock_gemini_client(updated_dict)

    result = apply_corrections(profile, "my FTP is actually 260", client)

    assert result.name == "Manuel"
    assert result.avg_weekly_hours == pytest.approx(8.5)


def test_apply_corrections_falls_back_to_original_on_missing_key() -> None:
    profile = _fixture_profile()
    # Gemini returns only partial dict — missing most keys
    client = _mock_gemini_client({"ftp_watts": 270})

    result = apply_corrections(profile, "FTP is 270", client)

    assert result.ftp_watts == 270
    assert result.name == "Manuel"  # falls back to original


# ---------------------------------------------------------------------------
# flush_to_db
# ---------------------------------------------------------------------------


def test_flush_to_db_writes_row_and_returns_id() -> None:
    conn = init_db()
    profile = _fixture_profile()
    row_id = flush_to_db(profile, conn)
    assert row_id == 1


def test_flush_to_db_persists_typed_fields() -> None:
    conn = init_db()
    profile = _fixture_profile()
    flush_to_db(profile, conn)
    saved = AthleteRepo(conn).load_latest()
    assert saved is not None
    assert saved.ftp_watts == 240
    assert saved.threshold_run_pace_per_km == pytest.approx(4.8)
    assert saved.avg_weekly_hours == pytest.approx(8.5)
    assert saved.experience_level == "beginner"


def test_flush_to_db_serialises_upcoming_races_as_json() -> None:
    conn = init_db()
    profile = _fixture_profile()
    flush_to_db(profile, conn)
    row = conn.execute("SELECT upcoming_races_json FROM athlete_profile WHERE id=1").fetchone()
    races = json.loads(row[0])
    assert isinstance(races, list)
    assert races[0]["name"] == "City Olympic"


def test_flush_to_db_multiple_profiles_get_separate_rows() -> None:
    conn = init_db()
    profile = _fixture_profile()
    flush_to_db(profile, conn)
    flush_to_db(profile, conn)
    count = conn.execute("SELECT COUNT(*) FROM athlete_profile").fetchone()[0]
    assert count == 2
