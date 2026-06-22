from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class TrainingPlanRow:
    id: int
    phase: str
    blocks_json: str | None
    sessions_json: str | None
    created_at: str


class TrainingPlanRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, phase: str, blocks_json: str | None, sessions_json: str | None) -> int:
        cursor = self._conn.execute(
            "INSERT INTO training_plan (phase, blocks_json, sessions_json) VALUES (?, ?, ?)",
            (phase, blocks_json, sessions_json),
        )
        self._conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def load_latest(self) -> list[TrainingPlanRow]:
        latest_ts = self._conn.execute(
            "SELECT created_at FROM training_plan ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest_ts is None:
            return []
        rows = self._conn.execute(
            "SELECT id, phase, blocks_json, sessions_json, created_at FROM training_plan WHERE created_at = ? ORDER BY id",
            (latest_ts[0],),
        ).fetchall()
        return [TrainingPlanRow(*row) for row in rows]
