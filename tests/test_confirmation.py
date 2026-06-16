from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from t3.bot.confirmation import (
    PendingConflict,
    add_pending_conflict,
    clear_pending,
    format_prompt,
    has_pending,
    resolve,
    _pending,
)
from t3.db import CalendarEventRepo, init_db
from t3.sync import ConflictInfo


@pytest.fixture(autouse=True)
def clear_state():
    _pending.clear()
    yield
    _pending.clear()


@pytest.fixture()
def conn():
    c = init_db(":memory:")
    CalendarEventRepo(c).insert("moved-id", "iid-moved", "2026-07-15T06:00:00+00:00", "run")
    CalendarEventRepo(c).insert("conflict-id", "iid-conflict", "2026-07-15T07:00:00+00:00", "bike")
    yield c
    c.close()


def _make_pending() -> PendingConflict:
    return PendingConflict(
        conflict=ConflictInfo(
            moved_gcal_id="moved-id",
            conflicting_gcal_id="conflict-id",
            original_time="2026-07-14T06:00:00+00:00",
            new_time="2026-07-15T06:00:00+00:00",
            conflicting_time="2026-07-15T07:00:00+00:00",
        ),
        moved_intervals_id="iid-moved",
        conflicting_intervals_id="iid-conflict",
    )


def test_add_and_has_pending():
    assert not has_pending(42)
    add_pending_conflict(42, _make_pending())
    assert has_pending(42)
    clear_pending(42)
    assert not has_pending(42)


def test_format_prompt_contains_options():
    prompt = format_prompt(_make_pending())
    assert "1" in prompt
    assert "2" in prompt
    assert "3" in prompt
    assert "2026-07-15" in prompt
    assert "2026-07-14" in prompt


def test_resolve_choice_1_reverts_move(conn):
    gcal = MagicMock()
    ints = MagicMock()
    msg = resolve(1, _make_pending(), conn, gcal, ints)
    gcal.update_event_time.assert_called_once_with("moved-id", "2026-07-14T06:00:00+00:00")
    ints.update_workout_date.assert_called_once_with("iid-moved", "2026-07-14")
    row = conn.execute("SELECT scheduled_at FROM calendar_events WHERE gcal_id = 'moved-id'").fetchone()
    assert row[0] == "2026-07-14T06:00:00+00:00"
    assert "reverted" in msg


def test_resolve_choice_2_removes_conflicting(conn):
    gcal = MagicMock()
    ints = MagicMock()
    msg = resolve(2, _make_pending(), conn, gcal, ints)
    gcal.delete_event.assert_called_once_with("conflict-id")
    ints.delete_workout.assert_called_once_with("iid-conflict")
    row = conn.execute("SELECT gcal_id FROM calendar_events WHERE gcal_id = 'conflict-id'").fetchone()
    assert row is None
    assert "conflicting" in msg


def test_resolve_choice_3_removes_moved(conn):
    gcal = MagicMock()
    ints = MagicMock()
    msg = resolve(3, _make_pending(), conn, gcal, ints)
    gcal.delete_event.assert_called_once_with("moved-id")
    ints.delete_workout.assert_called_once_with("iid-moved")
    row = conn.execute("SELECT gcal_id FROM calendar_events WHERE gcal_id = 'moved-id'").fetchone()
    assert row is None
    assert "moved session removed" in msg


def test_resolve_invalid_choice_returns_message(conn):
    gcal = MagicMock()
    ints = MagicMock()
    msg = resolve(9, _make_pending(), conn, gcal, ints)
    gcal.update_event_time.assert_not_called()
    gcal.delete_event.assert_not_called()
    assert "Invalid" in msg


def test_resolve_choice_1_no_intervals_id(conn):
    pending = PendingConflict(
        conflict=ConflictInfo("moved-id", "conflict-id", "2026-07-14T06:00:00+00:00", "2026-07-15T06:00:00+00:00", "2026-07-15T07:00:00+00:00"),
        moved_intervals_id=None,
        conflicting_intervals_id=None,
    )
    gcal = MagicMock()
    ints = MagicMock()
    resolve(1, pending, conn, gcal, ints)
    ints.update_workout_date.assert_not_called()
