from __future__ import annotations

from unittest.mock import patch

import pytest

from t3.db import CalendarEventRepo, SyncStateRepo, init_db
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

    CalendarEventRepo(conn).insert(
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
    CalendarEventRepo(conn).insert(
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
    CalendarEventRepo(conn).insert(
        gcal_id="evt-gone",
        intervals_id="",
        scheduled_at="2026-06-20T05:00:00+00:00",
        event_type="bike",
    )

    with patch("t3.sync.list_events", return_value=[]):
        changes = poll_gcal(conn)

    assert len(changes) == 1
    assert changes[0].type == "deleted"
    assert changes[0].gcal_id == "evt-gone"


# --- detect_conflicts ---

def test_detect_conflicts_returns_conflict_when_dates_overlap(conn) -> None:
    date = "2026-07-15"
    CalendarEventRepo(conn).insert("evt-a", "iid-a", f"{date}T06:00:00+00:00", "run")
    CalendarEventRepo(conn).insert("evt-b", "iid-b", f"{date}T07:00:00+00:00", "bike")

    moved = [CalendarChange(type="moved", gcal_id="evt-a", old_scheduled_at="2026-07-14T06:00:00+00:00", new_scheduled_at=f"{date}T06:00:00+00:00")]
    conflicts = detect_conflicts(conn, moved)

    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.moved_gcal_id == "evt-a"
    assert c.conflicting_gcal_id == "evt-b"
    assert c.new_time == f"{date}T06:00:00+00:00"
    assert c.conflicting_time == f"{date}T07:00:00+00:00"
    assert c.original_time == "2026-07-14T06:00:00+00:00"


def test_detect_conflicts_no_conflict_when_dates_differ(conn) -> None:
    CalendarEventRepo(conn).insert("evt-a", "iid-a", "2026-07-15T06:00:00+00:00", "run")
    CalendarEventRepo(conn).insert("evt-b", "iid-b", "2026-07-16T07:00:00+00:00", "bike")

    moved = [CalendarChange(type="moved", gcal_id="evt-a", old_scheduled_at="2026-07-14T06:00:00+00:00", new_scheduled_at="2026-07-15T06:00:00+00:00")]
    conflicts = detect_conflicts(conn, moved)

    assert conflicts == []


def test_detect_conflicts_ignores_non_moved_changes(conn) -> None:
    CalendarEventRepo(conn).insert("evt-a", "iid-a", "2026-07-15T06:00:00+00:00", "run")
    CalendarEventRepo(conn).insert("evt-b", "iid-b", "2026-07-15T07:00:00+00:00", "bike")

    created = [CalendarChange(type="created", gcal_id="evt-a", old_scheduled_at=None, new_scheduled_at="2026-07-15T06:00:00+00:00")]
    assert detect_conflicts(conn, created) == []


def test_sync_state_repo_chat_id(conn) -> None:
    repo = SyncStateRepo(conn)
    assert repo.get_telegram_chat_id() is None
    repo.set_telegram_chat_id(123456789)
    assert repo.get_telegram_chat_id() == 123456789
    repo.set_telegram_chat_id(987654321)
    assert repo.get_telegram_chat_id() == 987654321
