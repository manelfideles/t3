from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from t3.db import (
    CalendarRepo,
    ConversationState,
    ConversationStateRepo,
    SyncStateRepo,
    init_db,
)
from t3.scheduler import _make_poll_job


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "t3.db")
    c = init_db(path)
    SyncStateRepo(c).set_telegram_chat_id(99999)
    c.close()
    return path


@pytest.mark.asyncio
async def test_poll_sends_conflict_message_when_conflict_detected(db_path) -> None:
    c = init_db(db_path)
    date = "2026-08-01"
    CalendarRepo(c).insert("evt-a", "iid-a", f"{date}T06:00:00+00:00", "run")
    CalendarRepo(c).insert("evt-b", "iid-b", f"{date}T07:00:00+00:00", "bike")
    c.commit()

    gcal_response = [
        {"id": "evt-a", "start": {"dateTime": f"{date}T08:00:00+00:00"}, "summary": "Run"},
        {"id": "evt-b", "start": {"dateTime": f"{date}T07:00:00+00:00"}, "summary": "Bike"},
    ]

    notify = AsyncMock()
    poll_job = _make_poll_job(db_path, notify)

    with patch("t3.sync.list_events", return_value=gcal_response):
        await poll_job()

    notify.assert_called_once()
    chat_id, text = notify.call_args.args
    assert chat_id == 99999
    assert "1" in text and "2" in text and "3" in text
    assert "Run" in text or "run" in text
    assert "Bike" in text or "bike" in text
    assert "2026-08-01" in text or "Aug 1" in text

    # State persisted in DB
    conn = init_db(db_path)
    result = ConversationStateRepo(conn).load(99999)
    assert result is not None
    state, payload = result
    assert state == ConversationState.CONFLICT_PENDING
    assert payload is not None


@pytest.mark.asyncio
async def test_poll_sends_sync_notification_for_moved_without_conflict(db_path) -> None:
    c = init_db(db_path)
    CalendarRepo(c).insert("evt-a", "iid-a", "2026-08-01T06:00:00+00:00", "run")
    c.commit()

    gcal_response = [
        {"id": "evt-a", "start": {"dateTime": "2026-08-02T06:00:00+00:00"}, "summary": "T3 - Run"},
    ]

    notify = AsyncMock()
    poll_job = _make_poll_job(db_path, notify)
    with patch("t3.sync.list_events", return_value=gcal_response):
        await poll_job()

    notify.assert_called_once()
    _, text = notify.call_args.args
    assert text == 'Synced: moved "Run" on Google Calendar'


@pytest.mark.asyncio
async def test_poll_sends_sync_notification_for_deleted(db_path) -> None:
    c = init_db(db_path)
    CalendarRepo(c).insert("evt-a", "iid-a", "2026-08-01T06:00:00+00:00", "swim")
    c.commit()

    cancelled_item = {"id": "evt-a", "status": "cancelled", "summary": "T3 - Swim", "start": {}}

    notify = AsyncMock()
    poll_job = _make_poll_job(db_path, notify)
    with patch("t3.sync.list_events", return_value=[cancelled_item]):
        await poll_job()

    notify.assert_called_once()
    _, text = notify.call_args.args
    assert text == 'Synced: deleted "Swim" on Google Calendar'


@pytest.mark.asyncio
async def test_poll_sends_sync_notification_for_created(db_path) -> None:
    gcal_response = [
        {"id": "evt-new", "start": {"dateTime": "2026-08-05T07:00:00+00:00"}, "summary": "T3 - Bike"},
    ]

    notify = AsyncMock()
    poll_job = _make_poll_job(db_path, notify)
    with patch("t3.sync.list_events", return_value=gcal_response):
        await poll_job()

    notify.assert_called_once()
    _, text = notify.call_args.args
    assert text == 'Synced: created "Bike" on Google Calendar'


@pytest.mark.asyncio
async def test_poll_no_message_when_no_changes(db_path) -> None:
    c = init_db(db_path)
    CalendarRepo(c).insert("evt-a", "iid-a", "2026-08-01T06:00:00+00:00", "run")
    c.commit()

    gcal_response = [
        {"id": "evt-a", "start": {"dateTime": "2026-08-01T06:00:00+00:00"}, "summary": "Run"},
    ]

    notify = AsyncMock()
    poll_job = _make_poll_job(db_path, notify)
    with patch("t3.sync.list_events", return_value=gcal_response):
        await poll_job()

    notify.assert_not_called()
