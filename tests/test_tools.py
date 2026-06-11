from t3.tools.gcal_tools import (
    GCAL_FUNCTIONS,
    GCAL_HANDLERS,
    create_gcal_event,
    get_gcal_events,
)
from t3.tools.intervals_tools import (
    INTERVALS_FUNCTIONS,
    INTERVALS_HANDLERS,
    create_planned_workout,
    get_activities,
)


# --- gcal stubs ---

def test_get_gcal_events_returns_list() -> None:
    assert isinstance(get_gcal_events(), list)


def test_get_gcal_events_accepts_time_range() -> None:
    result = get_gcal_events(time_min="2026-06-01T00:00:00Z", time_max="2026-06-08T00:00:00Z")
    assert isinstance(result, list)


def test_create_gcal_event_returns_dict() -> None:
    result = create_gcal_event(
        summary="Swim", start="2026-06-11T07:00:00Z", end="2026-06-11T08:00:00Z"
    )
    assert isinstance(result, dict)


# --- intervals stubs ---

def test_get_activities_returns_list() -> None:
    assert isinstance(get_activities(), list)
    assert isinstance(get_activities(limit=5), list)


def test_create_planned_workout_returns_dict() -> None:
    result = create_planned_workout(date="2026-06-11", type="Swim", description="2km easy")
    assert isinstance(result, dict)


# --- manifest shape ---

def test_gcal_functions_are_callables() -> None:
    assert len(GCAL_FUNCTIONS) == 2
    for f in GCAL_FUNCTIONS:
        assert callable(f)


def test_intervals_functions_are_callables() -> None:
    assert len(INTERVALS_FUNCTIONS) == 2
    for f in INTERVALS_FUNCTIONS:
        assert callable(f)


def test_all_handlers_are_callable() -> None:
    for name, handler in {**GCAL_HANDLERS, **INTERVALS_HANDLERS}.items():
        assert callable(handler), f"Handler {name!r} is not callable"


# --- dispatch ---

def test_dispatch_unknown_tool_returns_error_string() -> None:
    from t3.agent import dispatch_tool

    result = dispatch_tool("nonexistent_tool", {})
    assert "unknown tool" in str(result).lower()


def test_dispatch_get_activities_returns_list() -> None:
    from t3.agent import dispatch_tool

    result = dispatch_tool("get_activities", {"limit": 3})
    assert isinstance(result, list)
