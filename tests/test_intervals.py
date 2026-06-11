from unittest.mock import MagicMock, patch

import httpx
import pytest

# --- unit tests (mocked httpx) ---


def _mock_response(json_data: object, status_code: int = 200) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock


def _mock_client(get_response=None, post_response=None):
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    if get_response is not None:
        mock.get.return_value = get_response
    if post_response is not None:
        mock.post.return_value = post_response
    return mock


# --- get_athlete_settings ---


def test_get_athlete_settings_returns_athlete_data() -> None:
    from t3.integrations import intervals

    fake = {"id": "i12345", "ftp": 240, "weight": 75.0, "height": 178}
    with patch("t3.integrations.intervals.httpx.Client", return_value=_mock_client(get_response=_mock_response(fake))):
        result = intervals.get_athlete_settings()

    assert result == fake


def test_get_athlete_settings_uses_athlete_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from t3.integrations import intervals

    monkeypatch.setattr("t3.integrations.intervals.settings.intervals_athlete_id", "i99999")
    mock = _mock_client(get_response=_mock_response({}))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        intervals.get_athlete_settings()

    url = mock.get.call_args.args[0]
    assert url.endswith("/i99999")


def test_get_athlete_settings_uses_correct_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    from t3.integrations import intervals

    monkeypatch.setattr("t3.integrations.intervals.settings.intervals_api_key", "key-xyz")
    mock = _mock_client(get_response=_mock_response({}))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        intervals.get_athlete_settings()

    assert mock.get.call_args.kwargs["auth"] == ("API_KEY", "key-xyz")


# --- get_events ---


def test_get_events_returns_list() -> None:
    from t3.integrations import intervals

    fake = [{"id": "e1", "category": "RACE", "name": "Sprint Tri"}]
    mock = _mock_client(get_response=_mock_response(fake))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        result = intervals.get_events("2026-01-01T00:00:00", "2026-12-31T23:59:59")

    assert result == fake


def test_get_events_passes_oldest_and_newest_params() -> None:
    from t3.integrations import intervals

    mock = _mock_client(get_response=_mock_response([]))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        intervals.get_events("2026-01-01T00:00:00", "2026-12-31T00:00:00")

    params = mock.get.call_args.kwargs["params"]
    assert params["oldest"] == "2026-01-01T00:00:00"
    assert params["newest"] == "2026-12-31T00:00:00"


def test_get_events_returns_empty_list_on_non_list_response() -> None:
    from t3.integrations import intervals

    mock = _mock_client(get_response=_mock_response({"error": "bad"}))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        result = intervals.get_events("2026-01-01T00:00:00", "2026-12-31T00:00:00")

    assert result == []


# --- get_best_efforts ---

_FAKE_ACTIVITIES = [
    # Run 10km in 50min (pace = 5.0 min/km) — 3000s >= 1080s threshold
    {"type": "Run", "distance": 10000, "moving_time": 3000},
    # Run 5km in 22min (pace = 4.4 min/km) — 1320s >= 1080s — faster
    {"type": "Run", "distance": 5000, "moving_time": 1320},
    # Swim 1500m in 30min (pace = 2.0 min/100m) — 1800s
    {"type": "Swim", "distance": 1500, "moving_time": 1800},
    # Swim 400m in 7min (pace = 1.75 min/100m) — faster
    {"type": "Swim", "distance": 400, "moving_time": 420},
    # Bike 40km in 75min — contributes to avg hours only
    {"type": "Ride", "distance": 40000, "moving_time": 4500},
]


def test_get_best_efforts_returns_expected_keys() -> None:
    from t3.integrations import intervals

    mock = _mock_client(get_response=_mock_response(_FAKE_ACTIVITIES))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        result = intervals.get_best_efforts(days=28)

    assert "avg_weekly_hours" in result
    assert "threshold_run_pace_per_km" in result
    assert "threshold_swim_pace_per_100m" in result


def test_get_best_efforts_selects_fastest_run_pace() -> None:
    from t3.integrations import intervals

    mock = _mock_client(get_response=_mock_response(_FAKE_ACTIVITIES))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        result = intervals.get_best_efforts(days=28)

    # 5km in 22min = 4.4 min/km is faster than 10km in 50min = 5.0 min/km
    assert result["threshold_run_pace_per_km"] == pytest.approx(4.4, abs=0.01)


def test_get_best_efforts_selects_fastest_swim_pace() -> None:
    from t3.integrations import intervals

    mock = _mock_client(get_response=_mock_response(_FAKE_ACTIVITIES))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        result = intervals.get_best_efforts(days=28)

    # 400m in 7min = 1.75 min/100m is faster than 1500m in 30min = 2.0 min/100m
    assert result["threshold_swim_pace_per_100m"] == pytest.approx(1.75, abs=0.01)


def test_get_best_efforts_computes_avg_weekly_hours() -> None:
    from t3.integrations import intervals

    mock = _mock_client(get_response=_mock_response(_FAKE_ACTIVITIES))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        result = intervals.get_best_efforts(days=28)

    # Total moving_time = 3000 + 1320 + 1800 + 420 + 4500 = 11040s = 3.067h over 4 weeks = 0.77 h/week
    expected = round(11040 / 3600 / (28 / 7), 2)
    assert result["avg_weekly_hours"] == pytest.approx(expected, abs=0.01)


def test_get_best_efforts_returns_none_paces_when_no_qualifying_activities() -> None:
    from t3.integrations import intervals

    activities = [{"type": "Ride", "distance": 30000, "moving_time": 3600}]
    mock = _mock_client(get_response=_mock_response(activities))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        result = intervals.get_best_efforts(days=28)

    assert result["threshold_run_pace_per_km"] is None
    assert result["threshold_swim_pace_per_100m"] is None


def test_get_best_efforts_excludes_short_runs() -> None:
    from t3.integrations import intervals

    # Run only 5 min — below 18-min threshold, should not count
    activities = [{"type": "Run", "distance": 1000, "moving_time": 300}]
    mock = _mock_client(get_response=_mock_response(activities))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        result = intervals.get_best_efforts(days=28)

    assert result["threshold_run_pace_per_km"] is None


def test_get_best_efforts_passes_oldest_newest_params() -> None:
    from t3.integrations import intervals

    mock = _mock_client(get_response=_mock_response([]))
    with patch("t3.integrations.intervals.httpx.Client", return_value=mock):
        intervals.get_best_efforts(days=14)

    params = mock.get.call_args.kwargs["params"]
    assert "oldest" in params
    assert "newest" in params


# --- existing tests ---


def test_get_activities_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from t3.integrations import intervals

    fake_activities = [{"id": "a1", "name": "Morning Run", "type": "Run"}]
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = _mock_response(fake_activities)

    with patch("t3.integrations.intervals.httpx.Client", return_value=mock_client):
        result = intervals.get_activities(limit=5)

    assert result == fake_activities
    mock_client.get.assert_called_once()
    # oldest/newest sent; limit applied client-side
    call_kwargs = mock_client.get.call_args
    params = call_kwargs.kwargs.get("params", {})
    assert "oldest" in params
    assert "newest" in params


def test_get_activities_uses_correct_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    from t3.integrations import intervals

    monkeypatch.setattr("t3.integrations.intervals.settings.intervals_api_key", "test-key-abc")
    monkeypatch.setattr("t3.integrations.intervals.settings.intervals_athlete_id", "i99999")

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = _mock_response([])

    with patch("t3.integrations.intervals.httpx.Client", return_value=mock_client):
        intervals.get_activities()

    call_kwargs = mock_client.get.call_args
    assert call_kwargs.kwargs["auth"] == ("API_KEY", "test-key-abc")
    assert "i99999" in call_kwargs.args[0]


def test_get_activities_uses_correct_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from t3.integrations import intervals

    monkeypatch.setattr("t3.integrations.intervals.settings.intervals_athlete_id", "i12345")

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = _mock_response([])

    with patch("t3.integrations.intervals.httpx.Client", return_value=mock_client):
        intervals.get_activities()

    url = mock_client.get.call_args.args[0]
    assert "intervals.icu" in url
    assert "i12345" in url
    assert "activities" in url


def test_create_planned_workout_posts_correct_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from t3.integrations import intervals

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = _mock_response({"id": "evt1"})

    with patch("t3.integrations.intervals.httpx.Client", return_value=mock_client):
        result = intervals.create_planned_workout(
            date="2026-06-15", workout_type="Swim", title="2km steady", description="2x750m @ Z2"
        )

    assert result == {"id": "evt1"}
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["start_date_local"] == "2026-06-15T08:00:00"
    assert payload["type"] == "Swim"
    assert payload["name"] == "T3 - 2km steady"
    assert payload["description"] == "2x750m @ Z2"
    assert payload["category"] == "WORKOUT"


def test_get_activities_raises_on_http_error() -> None:
    from t3.integrations import intervals

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    error_response = _mock_response({}, status_code=401)
    error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401", request=MagicMock(), response=error_response
    )
    mock_client.get.return_value = error_response

    with patch("t3.integrations.intervals.httpx.Client", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            intervals.get_activities()


# --- integration tests (require live credentials) ---


@pytest.mark.integration
def test_get_activities_live() -> None:
    from t3.config import settings
    from t3.integrations import intervals

    if not settings.intervals_api_key or not settings.intervals_athlete_id:
        pytest.skip("INTERVALS_API_KEY / INTERVALS_ATHLETE_ID not set")

    activities = intervals.get_activities(limit=3)
    assert isinstance(activities, list)
    if activities:
        assert "id" in activities[0]


@pytest.mark.integration
def test_create_and_verify_workout_live() -> None:
    from t3.config import settings
    from t3.integrations import intervals

    if not settings.intervals_api_key or not settings.intervals_athlete_id:
        pytest.skip("INTERVALS_API_KEY / INTERVALS_ATHLETE_ID not set")

    result = intervals.create_planned_workout(
        date="2026-06-20",
        workout_type="Swim",
        title="T3 test workout",
        description="T3 test workout — safe to delete",
    )
    assert isinstance(result, dict)
