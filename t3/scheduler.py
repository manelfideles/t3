from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from t3.config import settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def _make_poll_job(db_path: str, notify: Callable[[int, str], Awaitable[None]]):  # type: ignore[return]
    poll_count = 0

    async def _poll_job() -> None:
        nonlocal poll_count
        poll_count += 1
        logger.info("poll cycle %d", poll_count)
        try:
            from t3.db import ConversationState, ConversationStateRepo, SyncStateRepo, init_db
            from t3.sync import detect_conflicts, poll_gcal
            from t3.notifications import conflict_prompt

            conn = init_db(db_path)
            changes = poll_gcal(conn)
            moved = [c for c in changes if c.type == "moved"]
            conflicts = detect_conflicts(conn, moved) if moved else []
            chat_id = SyncStateRepo(conn).get_telegram_chat_id()

            if changes:
                logger.info("poll cycle %d: %d change(s) detected", poll_count, len(changes))

            if conflicts and chat_id is not None:
                conflict = conflicts[0]
                row = conn.execute(
                    "SELECT intervals_id FROM calendar_events WHERE gcal_id = ?",
                    (conflict.moved_gcal_id,),
                ).fetchone()
                moved_iid = row[0] if row else None
                row2 = conn.execute(
                    "SELECT intervals_id FROM calendar_events WHERE gcal_id = ?",
                    (conflict.conflicting_gcal_id,),
                ).fetchone()
                conflict_iid = row2[0] if row2 else None

                payload_json = json.dumps({
                    "conflict": dataclasses.asdict(conflict),
                    "moved_intervals_id": moved_iid,
                    "conflicting_intervals_id": conflict_iid,
                })
                ConversationStateRepo(conn).save(chat_id, ConversationState.CONFLICT_PENDING, payload_json)

                text = conflict_prompt(conflict, conflict.original_time, conflict.new_time)
                await notify(chat_id, text)
                logger.info("conflict prompt sent to chat_id=%d", chat_id)
        except Exception:
            logger.exception("poll cycle %d failed", poll_count)

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
    logger.info("scheduler started (poll interval: %ds)", settings.poll_interval_seconds)


def stop() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler stopped")
    _scheduler = None
