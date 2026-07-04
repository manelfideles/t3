from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class CalendarRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, gcal_id: str, intervals_id: str, scheduled_at: str, event_type: str) -> None:
        self._conn.execute(
            "INSERT INTO calendar_events (gcal_id, intervals_id, scheduled_at, event_type) VALUES (?, ?, ?, ?)",
            (gcal_id, intervals_id, scheduled_at, event_type),
        )
        self._conn.commit()

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()
        return row[0] if row else 0

    def update_last_synced_at(self, gcal_id: str, last_synced_at: str) -> None:
        self._conn.execute(
            "UPDATE calendar_events SET last_synced_at = ? WHERE gcal_id = ?",
            (last_synced_at, gcal_id),
        )
        self._conn.commit()

    def delete(self, gcal_id: str) -> None:
        self._conn.execute("DELETE FROM calendar_events WHERE gcal_id = ?", (gcal_id,))
        self._conn.commit()

    def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
    ) -> list:
        """
        Fetches all events from `time_min` to `time_max`
        Defaults to fetching all events within a 1-year period, starting now.
        """
        if not time_min:
            now = datetime.now(timezone.utc).isoformat()
            time_max = datetime(now.year + 1, now.month, now.day, tzinfo=timezone.utc).isoformat()
        events = self._conn.execute(
            "SELECT * FROM calendar_events WHERE scheduled_at BETWEEN ? AND ?",
            (time_min, time_max),
        ).fetchall()
        return events
