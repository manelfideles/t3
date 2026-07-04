from __future__ import annotations

import dataclasses
import json
from collections.abc import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from t3.config import settings
from t3.logger import logger
from t3.sync import CalendarChangeType

_scheduler: AsyncIOScheduler | None = None


def _make_poll_job(db_path: str, notify: Callable[[int, str], Awaitable[None]]):  # type: ignore[return]
    poll_count = 0

    async def _poll_job() -> None:
        nonlocal poll_count
        poll_count += 1
        try:
            from t3.db import (
                ConversationState,
                ConversationStateRepo,
                SyncStateRepo,
                init_db,
            )
            from t3.notifications import conflict_prompt, sync_notification
            from t3.sync import detect_conflicts, poll_gcal

            conn = init_db(db_path)
            changes = poll_gcal(conn)
            moved = [c for c in changes if c.type == CalendarChangeType.MOVED]
            conflicts = detect_conflicts(conn, moved) if moved else []
            chat_id = SyncStateRepo(conn).get_telegram_chat_id()
            conflict_gcal_ids = {c.moved_gcal_id for c in conflicts}

            if chat_id:
                for change in changes:
                    if change.type == CalendarChangeType.MOVED and change.gcal_id in conflict_gcal_ids:
                        continue
                    await notify(chat_id, sync_notification(change))

                if conflicts:
                    conflict = conflicts[0]
                    row = conn.execute(
                        "SELECT intervals_id, event_type FROM calendar_events WHERE gcal_id = ?",
                        (conflict.moved_gcal_id,),
                    ).fetchone()
                    moved_iid = row[0] if row else None
                    moved_event_type = row[1] if row else None
                    row2 = conn.execute(
                        "SELECT intervals_id, event_type FROM calendar_events WHERE gcal_id = ?",
                        (conflict.conflicting_gcal_id,),
                    ).fetchone()
                    conflict_iid = row2[0] if row2 else None
                    conflicting_event_type = row2[1] if row2 else None

                    payload_json = json.dumps(
                        {
                            "conflict": dataclasses.asdict(conflict),
                            "moved_intervals_id": moved_iid,
                            "conflicting_intervals_id": conflict_iid,
                            "moved_event_type": moved_event_type,
                            "conflicting_event_type": conflicting_event_type,
                        }
                    )
                    ConversationStateRepo(conn).save(chat_id, ConversationState.CONFLICT_PENDING, payload_json)

                    text = conflict_prompt(
                        conflict,
                        moved_event_type=moved_event_type,
                        conflicting_event_type=conflicting_event_type,
                    )
                    await notify(chat_id, text)
                    logger.info("Conflict prompt sent.")
        except Exception:
            logger.exception("Poll cycle %d failed", poll_count)

    return _poll_job


def register_jobs(db_path: str, notify: Callable[[int, str], Awaitable[None]]) -> None:
    assert _scheduler is not None, "call start() first"
    _scheduler.add_job(
        _make_poll_job(db_path, notify),
        "interval",
        seconds=settings.poll_interval_seconds,
        id="gcal_poll",
        replace_existing=True,
    )


def start(db_path: str, notify: Callable[[int, str], Awaitable[None]]) -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    register_jobs(db_path, notify)
    _scheduler.start()


def stop() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
