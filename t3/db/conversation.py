from __future__ import annotations

import sqlite3
from enum import Enum


class ConversationState(str, Enum):
    IDLE = "IDLE"
    ONBOARDING_AWAITING_CONFIRMATION = "ONBOARDING_AWAITING_CONFIRMATION"
    CONFLICT_PENDING = "CONFLICT_PENDING"
    PLAN_PREVIEW_PENDING = "PLAN_PREVIEW_PENDING"
    DISRUPTION_OPTIONS_PENDING = "DISRUPTION_OPTIONS_PENDING"
    VACATION_PROBE_PENDING = "VACATION_PROBE_PENDING"


class ConversationStateRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, chat_id: int, state: ConversationState, payload_json: str | None = None) -> None:
        self._conn.execute(
            """
            INSERT INTO conversation_state (chat_id, state, payload_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                state        = excluded.state,
                payload_json = excluded.payload_json,
                updated_at   = excluded.updated_at
            """,
            (chat_id, state.value, payload_json),
        )
        self._conn.commit()

    def load(self, chat_id: int) -> tuple[ConversationState, str | None] | None:
        row = self._conn.execute(
            "SELECT state, payload_json FROM conversation_state WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        return (ConversationState(row[0]), row[1])

    def clear(self, chat_id: int) -> None:
        self._conn.execute(
            "DELETE FROM conversation_state WHERE chat_id = ?", (chat_id,)
        )
        self._conn.commit()
