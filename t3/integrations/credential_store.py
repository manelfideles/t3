from __future__ import annotations

from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from t3.config import settings
from t3.db import TokenRepo, init_db

GCAL_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CredentialStore:
    """Manages OAuth token persistence and refresh for a single service."""

    def __init__(self, db_path: str = "t3.db") -> None:
        self._db_path = db_path

    def _repo(self) -> TokenRepo:
        return TokenRepo(init_db(self._db_path))

    def store(self, creds: Credentials) -> None:
        assert creds.token is not None
        self._repo().store(
            "gcal",
            creds.token,
            creds.refresh_token,
            creds.expiry.isoformat() if creds.expiry else None,
        )

    def load(self) -> Credentials | None:
        row = self._repo().load("gcal")
        if row is None:
            return None
        expiry = None
        if row.expires_at:
            expiry = datetime.fromisoformat(row.expires_at)
            if expiry.tzinfo is not None:
                expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
        return Credentials(
            token=row.access_token,
            refresh_token=row.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=GCAL_SCOPES,
            expiry=expiry,
        )

    def get_valid(self) -> Credentials:
        creds = self.load()
        if creds is None:
            raise RuntimeError("Google Calendar not connected. Send /connect_gcal to authorize.")
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.store(creds)
        return creds
