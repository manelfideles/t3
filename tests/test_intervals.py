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
    assert payload["name"] == "2km steady"
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
        description="T3 test workout — safe to delete",
    )
    assert isinstance(result, dict)
