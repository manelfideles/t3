from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from t3.config import settings
from t3.db import CalendarEventRepo, SyncStateRepo
from t3.integrations.gcal import list_events

logger = logging.getLogger(__name__)


@dataclass
class CalendarChange:
    type: Literal["moved", "created", "deleted"]
    gcal_id: str
    old_scheduled_at: str | None
    new_scheduled_at: str | None


def poll_gcal(conn: sqlite3.Connection) -> list[CalendarChange]:
    sync_repo = SyncStateRepo(conn)
    event_repo = CalendarEventRepo(conn)

    last_polled_at = sync_repo.get_last_polled_at()
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    if last_polled_at is None:
        last_polled_at = now_str

    # One-year window for the mandatory timeMin/timeMax params.
    time_min = last_polled_at if last_polled_at < now_str else now_str
    time_max_dt = datetime(now.year + 1, now.month, now.day, tzinfo=timezone.utc)
    time_max = time_max_dt.isoformat()

    gcal_items = list_events(
        time_min=time_min,
        time_max=time_max,
        db_path=settings.database_url,
        updated_min=last_polled_at,
    )

    gcal_map: dict[str, str] = {}
    for item in gcal_items:
        gcal_id = item.get("id", "")
        start = item.get("start", {})
        scheduled_at = start.get("dateTime") or start.get("date") or ""
        if gcal_id:
            gcal_map[gcal_id] = scheduled_at

    db_map = event_repo.all_scheduled_at()

    changes: list[CalendarChange] = []
    for gcal_id, new_scheduled_at in gcal_map.items():
        if gcal_id not in db_map:
            changes.append(CalendarChange(type="created", gcal_id=gcal_id, old_scheduled_at=None, new_scheduled_at=new_scheduled_at))
        elif db_map[gcal_id] != new_scheduled_at:
            changes.append(CalendarChange(type="moved", gcal_id=gcal_id, old_scheduled_at=db_map[gcal_id], new_scheduled_at=new_scheduled_at))

    for gcal_id in db_map:
        if gcal_id not in gcal_map:
            changes.append(CalendarChange(type="deleted", gcal_id=gcal_id, old_scheduled_at=db_map[gcal_id], new_scheduled_at=None))

    for change in changes:
        if change.type in ("created", "moved") and change.new_scheduled_at is not None:
            conn.execute(
                """
                INSERT INTO calendar_events (gcal_id, scheduled_at, last_synced_at)
                VALUES (?, ?, ?)
                ON CONFLICT(gcal_id) DO UPDATE SET
                    scheduled_at = excluded.scheduled_at,
                    last_synced_at = excluded.last_synced_at
                """,
                (change.gcal_id, change.new_scheduled_at, now_str),
            )
        elif change.type == "deleted":
            event_repo.update_last_synced_at(change.gcal_id, now_str)

    conn.commit()
    sync_repo.set_last_polled_at(now_str)

    if changes:
        logger.info("poll detected %d change(s): %s", len(changes), [c.type for c in changes])
    else:
        logger.debug("poll: no changes detected")

    return changes
