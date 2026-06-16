from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from t3.config import settings

if TYPE_CHECKING:
    import telegram

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_poll_count = 0
_bot: telegram.Bot | None = None


def set_bot(bot: telegram.Bot) -> None:
    global _bot
    _bot = bot


def _make_poll_job(db_path: str):  # type: ignore[return]
    async def _poll_job() -> None:
        global _poll_count
        _poll_count += 1
        logger.info("poll cycle %d", _poll_count)
        try:
            from t3.db import SyncStateRepo, init_db
            from t3.sync import detect_conflicts, poll_gcal

            def _run() -> tuple:
                conn = init_db(db_path)
                changes = poll_gcal(conn)
                moved = [c for c in changes if c.type == "moved"]
                conflicts = detect_conflicts(conn, moved) if moved else []
                chat_id = SyncStateRepo(conn).get_telegram_chat_id()
                return changes, conflicts, chat_id

            changes, conflicts, chat_id = await asyncio.get_event_loop().run_in_executor(None, _run)
            if changes:
                logger.info("poll cycle %d: %d change(s) detected", _poll_count, len(changes))
            if conflicts and _bot is not None and chat_id is not None:
                from t3.bot.confirmation import PendingConflict, add_pending_conflict, format_prompt

                conflict = conflicts[0]
                conn = __import__("t3.db", fromlist=["init_db"]).init_db(db_path)
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
                pending = PendingConflict(
                    conflict=conflict,
                    moved_intervals_id=moved_iid,
                    conflicting_intervals_id=conflict_iid,
                )
                add_pending_conflict(chat_id, pending)
                await _bot.send_message(chat_id=chat_id, text=format_prompt(pending), parse_mode="Markdown")
                logger.info("conflict prompt sent to chat_id=%d", chat_id)
        except Exception:
            logger.exception("poll cycle %d failed", _poll_count)

    return _poll_job


def register_jobs(db_path: str) -> None:
    assert _scheduler is not None, "call start() first"
    _scheduler.add_job(
        _make_poll_job(db_path),
        "interval",
        seconds=settings.poll_interval_seconds,
        id="gcal_poll",
        replace_existing=True,
    )


def start(db_path: str) -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    register_jobs(db_path)
    _scheduler.start()
    logger.info("scheduler started (poll interval: %ds)", settings.poll_interval_seconds)


def stop() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler stopped")
    _scheduler = None
