from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Protocol

from t3.sync import ConflictInfo


@dataclass
class PendingConflict:
    conflict: ConflictInfo
    moved_intervals_id: str | None
    conflicting_intervals_id: str | None


def format_prompt(pending: PendingConflict) -> str:
    c = pending.conflict
    return (
        f"⚠️ *Schedule conflict detected!*\n\n"
        f"You moved a session to *{c.new_time[:10]}*, but another session is already scheduled that day.\n\n"
        f"Choose a resolution:\n"
        f"1️⃣ Revert move — put the moved session back to {c.original_time[:16]}\n"
        f"2️⃣ Keep move, remove other — keep the moved session, delete the conflicting one\n"
        f"3️⃣ Remove moved — delete the session you just moved\n\n"
        f"Reply with 1, 2, or 3."
    )


class _GCalClient(Protocol):
    def update_event_time(self, gcal_id: str, new_start: str) -> dict: ...
    def delete_event(self, gcal_id: str) -> None: ...


class _IntervalsClient(Protocol):
    def update_workout_date(self, intervals_id: str, new_date: str) -> dict: ...
    def delete_workout(self, intervals_id: str) -> None: ...


def resolve(
    choice: int,
    pending: PendingConflict,
    conn: sqlite3.Connection,
    gcal: _GCalClient,
    intervals: _IntervalsClient,
) -> str:
    c = pending.conflict
    if choice == 1:
        gcal.update_event_time(c.moved_gcal_id, c.original_time)
        conn.execute(
            "UPDATE calendar_events SET scheduled_at = ? WHERE gcal_id = ?",
            (c.original_time, c.moved_gcal_id),
        )
        conn.commit()
        if pending.moved_intervals_id:
            intervals.update_workout_date(pending.moved_intervals_id, c.original_time[:10])
        return "Done — moved session reverted to its original time."
    elif choice == 2:
        conn.execute("DELETE FROM calendar_events WHERE gcal_id = ?", (c.conflicting_gcal_id,))
        conn.commit()
        gcal.delete_event(c.conflicting_gcal_id)
        if pending.conflicting_intervals_id:
            intervals.delete_workout(pending.conflicting_intervals_id)
        return "Done — conflicting session removed; moved session stays."
    elif choice == 3:
        conn.execute("DELETE FROM calendar_events WHERE gcal_id = ?", (c.moved_gcal_id,))
        conn.commit()
        gcal.delete_event(c.moved_gcal_id)
        if pending.moved_intervals_id:
            intervals.delete_workout(pending.moved_intervals_id)
        return "Done — moved session removed."
    else:
        return "Invalid choice. Reply with 1, 2, or 3."
