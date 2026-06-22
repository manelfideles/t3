from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class OAuthTokenRow:
    access_token: str
    refresh_token: str | None
    expires_at: str | None


class TokenRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def store(
        self,
        service: str,
        access_token: str,
        refresh_token: str | None,
        expires_at: str | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO oauth_tokens (service, access_token, refresh_token, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(service) DO UPDATE SET
                access_token  = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at    = excluded.expires_at
            """,
            (service, access_token, refresh_token, expires_at),
        )
        self._conn.commit()

    def load(self, service: str) -> OAuthTokenRow | None:
        row = self._conn.execute(
            "SELECT access_token, refresh_token, expires_at FROM oauth_tokens WHERE service = ?",
            (service,),
        ).fetchone()
        if row is None:
            return None
        return OAuthTokenRow(access_token=row[0], refresh_token=row[1], expires_at=row[2])
