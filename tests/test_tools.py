from unittest.mock import patch

from t3.tools.gcal import create_gcal_event, get_gcal_events
from t3.tools.intervals import create_planned_workout, get_activities
from t3.tools.registry import REGISTRY


def test_get_gcal_events_returns_list() -> None:
    with patch("t3.tools.gcal.list_events", return_value=[]) as mock:
        result = get_gcal_events()
    assert isinstance(result, list)
    mock.assert_called_once_with("", "")


def test_get_gcal_events_passes_time_range() -> None:
    with patch("t3.tools.gcal.list_events", return_value=[]) as mock:
        get_gcal_events(time_min="2026-06-01T00:00:00Z", time_max="2026-06-08T00:00:00Z")
    mock.assert_called_once_with("2026-06-01T00:00:00Z", "2026-06-08T00:00:00Z")


def test_create_gcal_event_returns_dict() -> None:
    fake = {"id": "evt123", "htmlLink": "https://calendar.google.com/..."}
    with patch("t3.tools.gcal.create_event", return_value=fake):
        result = create_gcal_event(summary="Swim", start="2026-06-11T07:00:00Z", end="2026-06-11T08:00:00Z")
    assert result == fake


def test_get_activities_returns_list() -> None:
    fake = [{"id": "a1", "name": "Morning Run"}]
    with patch("t3.tools.intervals._get_activities", return_value=fake):
        result = get_activities()
    assert isinstance(result, list)


def test_get_activities_passes_limit() -> None:
    with patch("t3.tools.intervals._get_activities", return_value=[]) as mock:
        get_activities(limit=5)
    mock.assert_called_once_with(5)


def test_create_planned_workout_returns_dict() -> None:
    fake = {"id": "evt1"}
    with patch("t3.tools.intervals._create_planned_workout", return_value=fake):
        result = create_planned_workout(date="2026-06-11", type="Swim", description="2km easy")
    assert result == fake


def test_registry_contains_all_four_tools() -> None:
    names = {f.__name__ for f in REGISTRY.functions}
    assert names >= {
        "get_gcal_events",
        "create_gcal_event",
        "get_activities",
        "create_planned_workout",
    }


def test_registry_functions_are_callable() -> None:
    for fn in REGISTRY.functions:
        assert callable(fn)


def test_registry_dispatch_calls_handler() -> None:
    with patch("t3.tools.intervals._get_activities", return_value=[{"id": "a1"}]) as mock:
        result = REGISTRY.dispatch("get_activities", {"limit": 3})
    mock.assert_called_once_with(3)
    assert result == [{"id": "a1"}]


def test_registry_dispatch_unknown_returns_error_string() -> None:
    result = REGISTRY.dispatch("nonexistent_tool", {})
    assert "unknown tool" in str(result).lower()


def test_dispatch_unknown_tool_returns_error_string() -> None:
    from t3.agent import dispatch_tool

    result = dispatch_tool("nonexistent_tool", {})
    assert "unknown tool" in str(result).lower()


def test_dispatch_get_activities_calls_client() -> None:
    from t3.agent import dispatch_tool

    with patch("t3.tools.intervals._get_activities", return_value=[{"id": "a1"}]) as mock:
        result = dispatch_tool("get_activities", {"limit": 3})

    mock.assert_called_once_with(3)
    assert result == [{"id": "a1"}]
