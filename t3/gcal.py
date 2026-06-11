from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs, urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from t3.config import settings
from t3.db import init_db

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def _client_config() -> dict:
    return {
        "installed": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


async def _wait_for_callback(port: int, timeout: float = 300.0) -> str:
    loop = asyncio.get_event_loop()
    code_future: asyncio.Future[str] = loop.create_future()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(8192)
        try:
            path = data.decode(errors="replace").split("\n")[0].split(" ")[1]
            params = parse_qs(urlparse(path).query)
            code = params.get("code", [""])[0]
        except IndexError:
            code = ""
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
            b"<h2>Google Calendar connected! You can close this tab.</h2>"
        )
        await writer.drain()
        writer.close()
        if code and not code_future.done():
            code_future.set_result(code)

    server = await asyncio.start_server(handle, "localhost", port)
    try:
        return await asyncio.wait_for(code_future, timeout=timeout)
    finally:
        server.close()
        await server.wait_closed()


async def run_oauth_flow(
    send_url_fn: Callable[[str], Awaitable[None]],
    db_path: str = "t3.db",
) -> None:
    """Run the OAuth flow end-to-end.

    send_url_fn is called with the auth URL so the caller can forward it to the user.
    Blocks until authorization completes or times out (300 s).
    """
    port = _free_port()
    redirect_uri = f"http://localhost:{port}"

    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")

    await send_url_fn(auth_url)

    code = await _wait_for_callback(port)
    # fetch_token is a blocking HTTP call — run in thread to avoid stalling the event loop
    await asyncio.to_thread(flow.fetch_token, code=code)
    _store_tokens(flow.credentials, db_path)


def _store_tokens(creds: Credentials, db_path: str = "t3.db") -> None:
    conn = init_db(db_path)
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


def _load_credentials(db_path: str = "t3.db") -> Credentials | None:
    conn = init_db(db_path)
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
        scopes=SCOPES,
    )


def _get_valid_credentials(db_path: str = "t3.db") -> Credentials:
    creds = _load_credentials(db_path)
    if creds is None:
        raise RuntimeError("Google Calendar not connected. Send /connect_gcal to authorize.")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _store_tokens(creds, db_path)
    return creds


def list_events(time_min: str, time_max: str, db_path: str = "t3.db") -> list[dict]:
    creds = _get_valid_credentials(db_path)
    service = build("calendar", "v3", credentials=creds)
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return result.get("items", [])


def create_event(summary: str, start: str, end: str, db_path: str = "t3.db") -> dict:
    creds = _get_valid_credentials(db_path)
    service = build("calendar", "v3", credentials=creds)
    event = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
    }
    return service.events().insert(calendarId="primary", body=event).execute()
