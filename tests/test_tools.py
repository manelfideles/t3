from typing import Any, cast
from unittest.mock import patch

from t3.tools.gcal import create_gcal_event, get_gcal_events
from t3.tools.intervals import create_planned_workout, get_activities
from t3.tools.registry import REGISTRY


# ── GCal ─────────────────────────────────────────────────────────────────────

def test_get_gcal_events_defaults_to_next_seven_days() -> None:
    with patch("t3.tools.gcal.list_events", return_value=[]) as mock:
        result = get_gcal_events()
    assert isinstance(result, list)
    assert mock.call_count == 1
    start_arg, end_arg = mock.call_args[0][:2]
    # both args are ISO datetime strings computed from now
    assert "T" in start_arg and "T" in end_arg


def test_get_gcal_events_passes_datetime_strings_through() -> None:
    with patch("t3.tools.gcal.list_events", return_value=[]) as mock:
        get_gcal_events(time_min="2026-06-01T00:00:00Z", time_max="2026-06-08T00:00:00Z")
    mock.assert_called_once_with("2026-06-01T00:00:00Z", "2026-06-08T00:00:00Z", db_path=mock.call_args[1]["db_path"])


def test_get_gcal_events_promotes_date_only_strings() -> None:
    with patch("t3.tools.gcal.list_events", return_value=[]) as mock:
        get_gcal_events(time_min="2026-06-01", time_max="2026-06-08")
    start_arg, end_arg = mock.call_args[0][:2]
    assert start_arg == "2026-06-01T00:00:00Z"
    assert end_arg == "2026-06-08T00:00:00Z"


def test_get_gcal_events_shapes_response() -> None:
    raw = [{"id": "evt1", "summary": "swim – easy", "start": {"dateTime": "2026-06-15T07:00:00"}, "end": {"dateTime": "2026-06-15T07:45:00"}, "status": "confirmed", "extra_field": "ignored"}]
    with patch("t3.tools.gcal.list_events", return_value=raw):
        result = get_gcal_events(time_min="2026-06-15T00:00:00Z", time_max="2026-06-15T23:59:59Z")
    assert result == [{"id": "evt1", "summary": "swim – easy", "start": "2026-06-15T07:00:00", "end": "2026-06-15T07:45:00"}]


def test_get_gcal_events_returns_error_when_not_connected() -> None:
    with patch("t3.tools.gcal.list_events", side_effect=RuntimeError("no creds")):
        result = get_gcal_events()
    assert isinstance(result, dict)
    assert result["error"] == "not_connected"
    assert "action" in result


def test_create_gcal_event_shapes_response() -> None:
    raw = {"id": "evt123", "summary": "T3 - Swim", "start": {"dateTime": "2026-06-11T07:00:00"}, "end": {"dateTime": "2026-06-11T07:45:00"}, "htmlLink": "https://..."}
    with patch("t3.tools.gcal.create_event", return_value=raw):
        result = create_gcal_event(summary="Swim", start="2026-06-11T07:00:00Z", end="2026-06-11T07:45:00Z")
    assert result == {"id": "evt123", "summary": "T3 - Swim", "start": "2026-06-11T07:00:00", "end": "2026-06-11T07:45:00"}


def test_create_gcal_event_returns_error_when_not_connected() -> None:
    with patch("t3.tools.gcal.create_event", side_effect=RuntimeError("no creds")):
        result = create_gcal_event(summary="Swim", start="2026-06-11T07:00:00Z", end="2026-06-11T07:45:00Z")
    assert isinstance(result, dict)
    assert result["error"] == "not_connected"


# ── Intervals ────────────────────────────────────────────────────────────────

def test_get_activities_returns_list() -> None:
    fake = [{"id": "a1", "name": "Morning Run", "type": "Run", "moving_time": 3600, "distance": 10000, "start_date_local": "2026-06-10T07:00:00"}]
    with patch("t3.tools.intervals._get_activities", return_value=fake):
        result = get_activities()
    assert isinstance(result, list)


def test_get_activities_shapes_response() -> None:
    fake = [{"id": "a1", "name": "Morning Run", "type": "Run", "moving_time": 3600, "distance": 10000, "start_date_local": "2026-06-10T07:00:00"}]
    with patch("t3.tools.intervals._get_activities", return_value=fake):
        result = get_activities(limit=1)
    assert result == [{"id": "a1", "date": "2026-06-10", "type": "Run", "name": "Morning Run", "duration_min": 60, "distance_m": 10000}]


def test_get_activities_passes_limit_when_no_filter() -> None:
    with patch("t3.tools.intervals._get_activities", return_value=[]) as mock:
        get_activities(limit=5)
    mock.assert_called_once_with(5)


def test_get_activities_filters_by_discipline() -> None:
    fake = [
        {"id": "a1", "type": "Run", "name": "Run", "moving_time": 3600, "distance": 10000, "start_date_local": "2026-06-10T07:00:00"},
        {"id": "a2", "type": "Swim", "name": "Swim", "moving_time": 2700, "distance": 2000, "start_date_local": "2026-06-09T07:00:00"},
    ]
    with patch("t3.tools.intervals._get_activities", return_value=fake):
        result = get_activities(limit=10, discipline="swim")
    assert len(result) == 1
    assert result[0]["type"] == "Swim"


def test_create_planned_workout_shapes_response() -> None:
    raw = {"id": "evt1", "start_date_local": "2026-06-11T08:00:00", "type": "Swim", "name": "T3 - 2km easy", "extra": "ignored"}
    with patch("t3.tools.intervals._create_planned_workout", return_value=raw):
        result = create_planned_workout(date="2026-06-11", workout_type="Swim", title="2km easy", description="easy")
    assert result == {"id": "evt1", "date": "2026-06-11", "type": "Swim", "name": "T3 - 2km easy"}


# ── Registry ─────────────────────────────────────────────────────────────────

def test_registry_contains_all_four_tools() -> None:
    names = {cast(Any, f).__name__ for f in REGISTRY.functions}
    assert names >= {"get_gcal_events", "create_gcal_event", "get_activities", "create_planned_workout"}


def test_registry_functions_are_callable() -> None:
    for fn in REGISTRY.functions:
        assert callable(fn)


def test_registry_dispatch_shapes_activities() -> None:
    fake = [{"id": "a1", "type": "Run", "name": "Run", "moving_time": 1800, "distance": 5000, "start_date_local": "2026-06-10T07:00:00"}]
    with patch("t3.tools.intervals._get_activities", return_value=fake) as mock:
        result = REGISTRY.dispatch("get_activities", {"limit": 3})
    mock.assert_called_once_with(3)
    assert result == [{"id": "a1", "date": "2026-06-10", "type": "Run", "name": "Run", "duration_min": 30, "distance_m": 5000}]


def test_registry_dispatch_unknown_returns_error_string() -> None:
    result = REGISTRY.dispatch("nonexistent_tool", {})
    assert "unknown tool" in str(result).lower()


def test_registry_discover_populates_all_tools() -> None:
    # agent.py calls REGISTRY.discover("t3.tools") at import time;
    # the tool-module imports in this file also trigger @tool registration.
    # Either way, after discovery the global REGISTRY must contain all tools.
    import t3.agent  # noqa: F401 — ensures discover() has been called
    names = {cast(Any, f).__name__ for f in REGISTRY.functions}
    assert names >= {"get_gcal_events", "create_gcal_event", "get_activities", "create_planned_workout", "generate_training_plan", "confirm_plan"}


def test_dispatch_unknown_tool_returns_error_string() -> None:
    from t3.agent import dispatch_tool
    result = dispatch_tool("nonexistent_tool", {})
    assert "unknown tool" in str(result).lower()


def test_dispatch_get_activities_shapes_result() -> None:
    from t3.agent import dispatch_tool
    fake = [{"id": "a1", "type": "Swim", "name": "Swim", "moving_time": 2700, "distance": 2000, "start_date_local": "2026-06-10T07:00:00"}]
    with patch("t3.tools.intervals._get_activities", return_value=fake):
        result = dispatch_tool("get_activities", {"limit": 3})
    assert result[0]["id"] == "a1"
    assert result[0]["duration_min"] == 45
