from __future__ import annotations

import sqlite3


class CalendarEventRepo:
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

    def all_scheduled_at(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT gcal_id, scheduled_at FROM calendar_events").fetchall()
        return {row[0]: row[1] for row in rows}
