from __future__ import annotations

import sqlite3


class SyncStateRepo:
    _KEY_LAST_POLLED = "last_polled_at"
    _KEY_CHAT_ID = "telegram_chat_id"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _get(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM sync_state WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def _set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO sync_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_last_polled_at(self) -> str | None:
        return self._get(self._KEY_LAST_POLLED)

    def set_last_polled_at(self, value: str) -> None:
        self._set(self._KEY_LAST_POLLED, value)

    def get_telegram_chat_id(self) -> int | None:
        raw = self._get(self._KEY_CHAT_ID)
        return int(raw) if raw is not None else None

    def set_telegram_chat_id(self, chat_id: int) -> None:
        self._set(self._KEY_CHAT_ID, str(chat_id))
