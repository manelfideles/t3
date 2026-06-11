from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from t3.config import settings
from t3.db import init_db

GCAL_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CredentialStore:
    """Manages OAuth token persistence and refresh for a single service."""

    def __init__(self, db_path: str = "t3.db") -> None:
        self._db_path = db_path

    def store(self, creds: Credentials) -> None:
        conn = init_db(self._db_path)
        conn.execute(
            """
            INSERT INTO oauth_tokens (service, access_token, refresh_token, expires_at)
            VALUES ('gcal', ?, ?, ?)
            ON CONFLICT(service) DO UPDATE SET
                access_token  = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at    = excluded.expires_at
            """,
            (
                creds.token,
                creds.refresh_token,
                creds.expiry.isoformat() if creds.expiry else None,
            ),
        )
        conn.commit()

    def load(self) -> Credentials | None:
        conn = init_db(self._db_path)
        row = conn.execute(
            "SELECT access_token, refresh_token, expires_at FROM oauth_tokens WHERE service = 'gcal'"
        ).fetchone()
        if row is None:
            return None
        return Credentials(
            token=row[0],
            refresh_token=row[1],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=GCAL_SCOPES,
        )

    def get_valid(self) -> Credentials:
        creds = self.load()
        if creds is None:
            raise RuntimeError("Google Calendar not connected. Send /connect_gcal to authorize.")
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.store(creds)
        return creds
