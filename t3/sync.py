from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pprint import pprint

from t3.config import settings
from t3.db import CalendarRepo, SyncStateRepo
from t3.integrations.gcal import list_events
from t3.logger import logger


class CalendarChangeType(StrEnum):
    MOVED = "moved"
    CREATED = "created"
    DELETED = "deleted"


@dataclass(frozen=True)
class CalendarChange:
    type: CalendarChangeType
    gcal_id: str
    old_scheduled_at: str | None
    new_scheduled_at: str | None
    title: str = "session"


@dataclass
class ConflictInfo:
    moved_gcal_id: str
    conflicting_gcal_id: str
    original_time: str
    new_time: str
    conflicting_time: str


def detect_conflicts(conn: sqlite3.Connection, moved_changes: list[CalendarChange]) -> list[ConflictInfo]:
    """Return ConflictInfo for each moved event whose new date is shared by another event."""
    conflicts: list[ConflictInfo] = []
    for change in moved_changes:
        if change.type != "moved" or not change.new_scheduled_at:
            continue
        date_prefix = change.new_scheduled_at[:10]
        rows = conn.execute(
            "SELECT gcal_id, scheduled_at FROM calendar_events WHERE scheduled_at LIKE ? AND gcal_id != ?",
            (f"{date_prefix}%", change.gcal_id),
        ).fetchall()
        for gcal_id, scheduled_at in rows:
            conflicts.append(
                ConflictInfo(
                    moved_gcal_id=change.gcal_id,
                    conflicting_gcal_id=gcal_id,
                    original_time=change.old_scheduled_at or "",
                    new_time=change.new_scheduled_at,
                    conflicting_time=scheduled_at,
                )
            )
    return conflicts


def sync_changes(
    conn: sqlite3.Connection,
    calendar_repo: CalendarRepo,
    now_str: str,
    changes: list[CalendarChange],
):
    for change in changes:
        if change.type != CalendarChangeType.DELETED and change.new_scheduled_at is not None:
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
        else:
            calendar_repo.delete(change.gcal_id)
            calendar_repo.update_last_synced_at(change.gcal_id, last_synced_at=now_str)
    conn.commit()


def poll_gcal(conn: sqlite3.Connection) -> list[CalendarChange]:
    """
    Fetches all T3 events from today onwards, from both calendars,
    to synchronize changes across calendars.
    """
    sync_repo = SyncStateRepo(conn)
    calendar_repo = CalendarRepo(conn)

    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    today = f"{now_str[:10]}T00:00:00+00:00"
    time_max = datetime(now.year + 1, now.month, now.day, tzinfo=timezone.utc).isoformat()
    gcal_events: list[dict[str, str | dict]] = list_events(
        time_min=today,
        time_max=time_max,
        db_path=settings.database_url,
    )
    calendar_events: list[tuple] = calendar_repo.list_events(today, time_max)

    changes: list[CalendarChange] = []
    for gcal_event in gcal_events:
        if gcal_event["id"] not in [e[1] for e in calendar_events]:
            changes.append(
                CalendarChange(
                    type=CalendarChangeType.CREATED,
                    gcal_id=gcal_event["id"],
                    old_scheduled_at=None,
                    new_scheduled_at=gcal_event["start"]["dateTime"],
                    title=gcal_event.get("summary"),
                )
            )
        else:
            _, _, _, scheduled_at, _, _ = list(filter(lambda t: t[1] == gcal_event["id"], calendar_events)).pop(0)
            if scheduled_at != gcal_event["start"]["dateTime"]:
                changes.append(
                    CalendarChange(
                        type=CalendarChangeType.MOVED,
                        gcal_id=gcal_event["id"],
                        old_scheduled_at=scheduled_at,
                        new_scheduled_at=gcal_event["start"]["dateTime"],
                        title=gcal_event["summary"],
                    )
                )

    for _, gcal_id, _, scheduled_at, _, _ in calendar_events:
        if gcal_id not in [e["id"] for e in gcal_events]:
            changes.append(
                CalendarChange(
                    type=CalendarChangeType.DELETED,
                    gcal_id=gcal_id,
                    old_scheduled_at=scheduled_at,
                    new_scheduled_at=None,
                )
            )

    logger.info("Poll detected %d change(s): %s", len(changes), [c for c in changes])
    sync_changes(conn, calendar_repo, now_str, changes)
    sync_repo.set_last_polled_at(now_str)

    return changes
