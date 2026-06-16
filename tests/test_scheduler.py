from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from t3.bot.confirmation import _pending
from t3.db import CalendarEventRepo, SyncStateRepo, init_db
from t3.scheduler import _make_poll_job, set_bot


@pytest.fixture(autouse=True)
def clear_confirmation_state():
    _pending.clear()
    yield
    _pending.clear()


@pytest.fixture()
def conn(tmp_path):
    db_path = str(tmp_path / "t3.db")
    c = init_db(db_path)
    SyncStateRepo(c).set_telegram_chat_id(99999)
    yield db_path
    c.close()


@pytest.mark.asyncio
async def test_poll_sends_conflict_message_when_conflict_detected(conn) -> None:
    db_path = conn
    c = init_db(db_path)
    date = "2026-08-01"
    CalendarEventRepo(c).insert("evt-a", "iid-a", f"{date}T06:00:00+00:00", "run")
    CalendarEventRepo(c).insert("evt-b", "iid-b", f"{date}T07:00:00+00:00", "bike")
    c.commit()

    gcal_response = [
        {"id": "evt-a", "start": {"dateTime": f"{date}T08:00:00+00:00"}, "summary": "Run"},
        {"id": "evt-b", "start": {"dateTime": f"{date}T07:00:00+00:00"}, "summary": "Bike"},
    ]

    bot = MagicMock()
    bot.send_message = AsyncMock()
    set_bot(bot)

    poll_job = _make_poll_job(db_path)

    with patch("t3.sync.list_events", return_value=gcal_response):
        await poll_job()

    bot.send_message.assert_called_once()
    call_kwargs = bot.send_message.call_args
    assert call_kwargs.kwargs["chat_id"] == 99999
    text = call_kwargs.kwargs["text"]
    assert "1" in text and "2" in text and "3" in text
    assert 99999 in _pending


@pytest.mark.asyncio
async def test_poll_no_message_when_no_conflict(conn) -> None:
    db_path = conn
    c = init_db(db_path)
    CalendarEventRepo(c).insert("evt-a", "iid-a", "2026-08-01T06:00:00+00:00", "run")
    c.commit()

    gcal_response = [
        {"id": "evt-a", "start": {"dateTime": "2026-08-02T06:00:00+00:00"}, "summary": "Run"},
    ]

    bot = MagicMock()
    bot.send_message = AsyncMock()
    set_bot(bot)

    poll_job = _make_poll_job(db_path)
    with patch("t3.sync.list_events", return_value=gcal_response):
        await poll_job()

    bot.send_message.assert_not_called()
