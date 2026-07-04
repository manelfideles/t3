from __future__ import annotations

from unittest.mock import patch

import pytest

from t3.db import CalendarRepo, SyncStateRepo, init_db
from t3.sync import CalendarChange, ConflictInfo, detect_conflicts, poll_gcal


def _gcal_item(gcal_id: str, scheduled_at: str) -> dict:
    return {
        "id": gcal_id,
        "start": {"dateTime": scheduled_at},
        "summary": "Test session",
    }


@pytest.fixture()
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def test_poll_gcal_moved_event(conn) -> None:
    original_time = "2026-07-01T06:00:00+00:00"
    new_time = "2026-07-01T07:00:00+00:00"

    CalendarRepo(conn).insert(
        gcal_id="evt-1",
        intervals_id="",
        scheduled_at=original_time,
        event_type="run",
    )

    gcal_response = [_gcal_item("evt-1", new_time)]

    with patch("t3.sync.list_events", return_value=gcal_response):
        changes = poll_gcal(conn)

    assert len(changes) == 1
    change = changes[0]
    assert change.type == "moved"
    assert change.gcal_id == "evt-1"
    assert change.old_scheduled_at == original_time
    assert change.new_scheduled_at == new_time


def test_poll_gcal_created_event(conn) -> None:
    scheduled_at = "2026-07-10T08:00:00+00:00"
    gcal_response = [_gcal_item("evt-new", scheduled_at)]

    with patch("t3.sync.list_events", return_value=gcal_response):
        changes = poll_gcal(conn)

    assert len(changes) == 1
    assert changes[0].type == "created"
    assert changes[0].gcal_id == "evt-new"
    assert changes[0].new_scheduled_at == scheduled_at


def test_poll_gcal_no_changes(conn) -> None:
    scheduled_at = "2026-07-05T09:00:00+00:00"
    CalendarRepo(conn).insert(
        gcal_id="evt-stable",
        intervals_id="",
        scheduled_at=scheduled_at,
        event_type="swim",
    )

    gcal_response = [_gcal_item("evt-stable", scheduled_at)]

    with patch("t3.sync.list_events", return_value=gcal_response):
        changes = poll_gcal(conn)

    assert changes == []


def test_poll_gcal_updates_last_polled_at(conn) -> None:
    with patch("t3.sync.list_events", return_value=[]):
        poll_gcal(conn)

    cursor = SyncStateRepo(conn).get_last_polled_at()
    assert cursor is not None
    assert "2026" in cursor


def test_poll_gcal_deleted_event_logs_only(conn) -> None:
    CalendarRepo(conn).insert(
        gcal_id="evt-gone",
        intervals_id="",
        scheduled_at="2026-07-20T05:00:00+00:00",
        event_type="bike",
    )

    with patch("t3.sync.list_events", return_value=[]):
        changes = poll_gcal(conn)

    assert len(changes) == 1
    assert changes[0].type == "deleted"
    assert changes[0].gcal_id == "evt-gone"


def test_poll_gcal_unmodified_event_not_classified_as_deleted(conn) -> None:
    """Pre-existing events absent from the poll response must not be wrongly
    deleted.  This was the root cause of the 'created + deleted' bug: using
    updatedMin caused GCal to omit unmodified events → they looked deleted,
    their DB rows were removed, and on the next poll (after user moves) they
    re-appeared as 'created'."""
    scheduled_at = "2026-08-01T07:00:00+00:00"
    CalendarRepo(conn).insert("evt-stable", "", scheduled_at, "run")

    # GCal correctly returns the event — simulates full-calendar fetch (no updatedMin)
    gcal_response = [_gcal_item("evt-stable", scheduled_at)]
    with patch("t3.sync.list_events", return_value=gcal_response):
        changes = poll_gcal(conn)

    assert changes == []


def test_poll_gcal_does_not_pass_updated_min(conn) -> None:
    """list_events must be called without updated_min so pre-existing events
    are always included in the comparison."""
    with patch("t3.sync.list_events", return_value=[]) as mock_list:
        poll_gcal(conn)

    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs.get("updated_min") is None


def test_poll_gcal_deleted_event_not_re_reported_on_next_poll(conn) -> None:
    CalendarRepo(conn).insert(
        gcal_id="evt-gone",
        intervals_id="",
        scheduled_at="2026-07-20T05:00:00+00:00",
        event_type="bike",
    )

    with patch("t3.sync.list_events", return_value=[]):
        first = poll_gcal(conn)
        second = poll_gcal(conn)

    assert len(first) == 1 and first[0].type == "deleted"
    assert second == []


def test_poll_gcal_cancelled_event_treated_as_deleted_not_moved(conn) -> None:
    """GCal returns status=cancelled (with no start) for deleted events when
    updatedMin is set. Must classify as deleted, not moved, so conflict
    detection is not triggered."""
    CalendarRepo(conn).insert(
        gcal_id="evt-del",
        intervals_id="",
        scheduled_at="2026-06-25T07:00:00+00:00",
        event_type="swim",
    )
    CalendarRepo(conn).insert(
        gcal_id="evt-other",
        intervals_id="",
        scheduled_at="2026-06-26T07:00:00+00:00",
        event_type="swim",
    )

    cancelled_item = {"id": "evt-del", "status": "cancelled", "start": {}}

    with patch("t3.sync.list_events", return_value=[cancelled_item]):
        changes = poll_gcal(conn)

    deleted = [c for c in changes if c.gcal_id == "evt-del"]
    assert len(deleted) == 1
    assert deleted[0].type == "deleted"

    moved = [c for c in changes if c.type == "moved"]
    assert moved == []


# --- detect_conflicts ---


def test_detect_conflicts_returns_conflict_when_dates_overlap(conn) -> None:
    date = "2026-07-15"
    CalendarRepo(conn).insert("evt-a", "iid-a", f"{date}T06:00:00+00:00", "run")
    CalendarRepo(conn).insert("evt-b", "iid-b", f"{date}T07:00:00+00:00", "bike")

    moved = [
        CalendarChange(
            type="moved",
            gcal_id="evt-a",
            old_scheduled_at="2026-07-14T06:00:00+00:00",
            new_scheduled_at=f"{date}T06:00:00+00:00",
        )
    ]
    conflicts = detect_conflicts(conn, moved)

    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.moved_gcal_id == "evt-a"
    assert c.conflicting_gcal_id == "evt-b"
    assert c.new_time == f"{date}T06:00:00+00:00"
    assert c.conflicting_time == f"{date}T07:00:00+00:00"
    assert c.original_time == "2026-07-14T06:00:00+00:00"


def test_detect_conflicts_no_conflict_when_dates_differ(conn) -> None:
    CalendarRepo(conn).insert("evt-a", "iid-a", "2026-07-15T06:00:00+00:00", "run")
    CalendarRepo(conn).insert("evt-b", "iid-b", "2026-07-16T07:00:00+00:00", "bike")

    moved = [
        CalendarChange(
            type="moved",
            gcal_id="evt-a",
            old_scheduled_at="2026-07-14T06:00:00+00:00",
            new_scheduled_at="2026-07-15T06:00:00+00:00",
        )
    ]
    conflicts = detect_conflicts(conn, moved)

    assert conflicts == []


def test_detect_conflicts_ignores_non_moved_changes(conn) -> None:
    CalendarRepo(conn).insert("evt-a", "iid-a", "2026-07-15T06:00:00+00:00", "run")
    CalendarRepo(conn).insert("evt-b", "iid-b", "2026-07-15T07:00:00+00:00", "bike")

    created = [
        CalendarChange(
            type="created", gcal_id="evt-a", old_scheduled_at=None, new_scheduled_at="2026-07-15T06:00:00+00:00"
        )
    ]
    assert detect_conflicts(conn, created) == []


def test_sync_state_repo_chat_id(conn) -> None:
    repo = SyncStateRepo(conn)
    assert repo.get_telegram_chat_id() is None
    repo.set_telegram_chat_id(123456789)
    assert repo.get_telegram_chat_id() == 123456789
    repo.set_telegram_chat_id(987654321)
    assert repo.get_telegram_chat_id() == 987654321


# --- Integration: inject conflicting rows, detect ---


def test_integration_detect_conflicts_with_sqlite(conn) -> None:
    date = "2026-09-10"
    CalendarRepo(conn).insert("gcal-x", "iid-x", f"{date}T06:00:00+00:00", "swim")
    CalendarRepo(conn).insert("gcal-y", "iid-y", f"{date}T09:00:00+00:00", "run")

    moved = [
        CalendarChange(
            type="moved",
            gcal_id="gcal-x",
            old_scheduled_at="2026-09-09T06:00:00+00:00",
            new_scheduled_at=f"{date}T06:00:00+00:00",
        )
    ]
    conflicts = detect_conflicts(conn, moved)

    assert len(conflicts) == 1
    assert conflicts[0].moved_gcal_id == "gcal-x"
    assert conflicts[0].conflicting_gcal_id == "gcal-y"
