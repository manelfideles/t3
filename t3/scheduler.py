from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from t3.config import settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_poll_count = 0


def _make_poll_job(db_path: str):  # type: ignore[return]
    async def _poll_job() -> None:
        global _poll_count
        _poll_count += 1
        logger.info("poll cycle %d", _poll_count)
        try:
            from t3.sync import poll_gcal
            from t3.db import init_db

            def _run() -> list:
                conn = init_db(db_path)
                return poll_gcal(conn)

            changes = await asyncio.get_event_loop().run_in_executor(None, _run)
            if changes:
                logger.info("poll cycle %d: %d change(s) detected", _poll_count, len(changes))
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
