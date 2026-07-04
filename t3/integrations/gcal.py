from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from t3.config import settings
from t3.integrations.credential_store import GCAL_SCOPES, CredentialStore

T3_CALENDAR_NAME = "T3"


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


def _get_calendar(service, calendar_id: str) -> str:
    """Return the calendarId for the 'T3' calendar, creating it if it doesn't exist."""
    calendars = service.calendarList().list().execute()
    for cal in calendars.get("items", []):
        if cal.get("summary") == calendar_id:
            return cal["id"]
    created = service.calendars().insert(body={"summary": calendar_id}).execute()
    return created["id"]


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

    flow = Flow.from_client_config(_client_config(), scopes=GCAL_SCOPES, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")

    await send_url_fn(auth_url)

    code = await _wait_for_callback(port)
    await asyncio.to_thread(flow.fetch_token, code=code)
    CredentialStore(db_path).store(flow.credentials)


def list_events(
    time_min: str,
    time_max: str,
    db_path: str = "t3.db",
    updated_min: str | None = None,
) -> list[dict]:
    creds = CredentialStore(db_path).get_valid()
    service = build("calendar", "v3", credentials=creds)
    calendar_id = _get_calendar(service, T3_CALENDAR_NAME)
    kwargs: dict = {
        "calendarId": calendar_id,
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if updated_min is not None:
        kwargs["updatedMin"] = updated_min
    result = service.events().list(**kwargs).execute()
    return result.get("items", [])


def create_event(summary: str, start: str, end: str, db_path: str = "t3.db") -> dict:
    creds = CredentialStore(db_path).get_valid()
    service = build("calendar", "v3", credentials=creds)
    calendar_id = _get_calendar(service, T3_CALENDAR_NAME)
    event = {
        "summary": f"T3 - {summary}" if not summary.startswith("T3 - ") else summary,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
    }
    return service.events().insert(calendarId=calendar_id, body=event).execute()


def update_event_time(gcal_id: str, new_start: str, db_path: str = "t3.db") -> dict:
    from datetime import datetime, timedelta

    creds = CredentialStore(db_path).get_valid()
    service = build("calendar", "v3", credentials=creds)
    calendar_id = _get_calendar(service, T3_CALENDAR_NAME)
    event = service.events().get(calendarId=calendar_id, eventId=gcal_id).execute()

    orig_start_str = event["start"].get("dateTime") or event["start"].get("date", "")
    orig_end_str = event["end"].get("dateTime") or event["end"].get("date", "")
    try:
        duration = datetime.fromisoformat(orig_end_str) - datetime.fromisoformat(orig_start_str)
    except (ValueError, KeyError):
        duration = timedelta(hours=1)

    new_start_dt = datetime.fromisoformat(new_start)
    new_end = (new_start_dt + duration).isoformat()

    event["start"] = {"dateTime": new_start, "timeZone": "UTC"}
    event["end"] = {"dateTime": new_end, "timeZone": "UTC"}
    return service.events().update(calendarId=calendar_id, eventId=gcal_id, body=event).execute()


def delete_event(gcal_id: str, db_path: str = "t3.db") -> None:
    creds = CredentialStore(db_path).get_valid()
    service = build("calendar", "v3", credentials=creds)
    calendar_id = _get_calendar(service, T3_CALENDAR_NAME)
    service.events().delete(calendarId=calendar_id, eventId=gcal_id).execute()
