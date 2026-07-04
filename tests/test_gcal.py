from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.oauth2.credentials import Credentials

from t3.integrations.credential_store import CredentialStore
from t3.db import init_db
from t3.integrations.gcal import _client_config, _free_port

# --- helpers ---


def _fake_creds(
    token: str = "access-token",
    refresh: str = "refresh-token",
    expiry: datetime | None = None,
) -> Credentials:
    return Credentials(
        token=token,
        refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        scopes=["https://www.googleapis.com/auth/calendar"],
        expiry=expiry,
    )


# --- unit tests ---


def test_free_port_returns_open_port() -> None:
    import socket

    port = _free_port()
    assert 1024 < port < 65536
    with socket.socket() as s:
        s.bind(("localhost", port))


def test_client_config_has_correct_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.integrations.gcal.settings.google_client_id", "test-client-id")
    monkeypatch.setattr("t3.integrations.gcal.settings.google_client_secret", "test-secret")
    cfg = _client_config()
    assert "installed" in cfg
    assert cfg["installed"]["client_id"] == "test-client-id"
    assert cfg["installed"]["client_secret"] == "test-secret"
    assert "auth_uri" in cfg["installed"]
    assert "token_uri" in cfg["installed"]


def test_store_and_load_tokens_roundtrip(tmp_path: Path) -> None:
    db = str(tmp_path / "test.db")
    init_db(db)
    creds = _fake_creds(expiry=datetime(2026, 12, 31, tzinfo=timezone.utc))
    store = CredentialStore(db)

    store.store(creds)
    loaded = store.load()

    assert loaded is not None
    assert loaded.token == "access-token"
    assert loaded.refresh_token == "refresh-token"


def test_load_credentials_returns_none_when_not_connected(tmp_path: Path) -> None:
    db = str(tmp_path / "empty.db")
    init_db(db)
    assert CredentialStore(db).load() is None


def test_store_tokens_upserts_on_reconnect(tmp_path: Path) -> None:
    db = str(tmp_path / "test.db")
    init_db(db)
    store = CredentialStore(db)

    store.store(_fake_creds(token="old-token"))
    store.store(_fake_creds(token="new-token"))

    loaded = store.load()
    assert loaded is not None
    assert loaded.token == "new-token"


def test_store_tokens_handles_missing_expiry(tmp_path: Path) -> None:
    db = str(tmp_path / "test.db")
    init_db(db)
    store = CredentialStore(db)
    store.store(_fake_creds(expiry=None))
    assert store.load() is not None


# --- bot handler unit tests ---


@pytest.mark.anyio
async def test_connect_gcal_handler_success() -> None:
    from t3.bot import connect_gcal

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    with patch("t3.integrations.gcal.run_oauth_flow", new=AsyncMock()) as mock_flow:
        await connect_gcal(update, context)

    mock_flow.assert_called_once()
    last_reply = update.message.reply_text.call_args_list[-1].args[0]
    assert "connected" in last_reply.lower()


@pytest.mark.anyio
async def test_connect_gcal_handler_timeout() -> None:
    import asyncio

    from t3.bot import connect_gcal

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    with patch("t3.integrations.gcal.run_oauth_flow", side_effect=asyncio.TimeoutError):
        await connect_gcal(update, context)

    last_reply = update.message.reply_text.call_args_list[-1].args[0]
    assert "timed out" in last_reply.lower()


def test_update_event_time_preserves_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from t3.integrations.gcal import update_event_time

    fake_event = {
        "id": "evt1",
        "summary": "T3 - Swim",
        "start": {"dateTime": "2026-06-10T07:00:00Z", "timeZone": "UTC"},
        "end": {"dateTime": "2026-06-10T08:30:00Z", "timeZone": "UTC"},
    }

    mock_service = MagicMock()
    mock_service.calendarList().list().execute.return_value = {
        "items": [{"summary": "T3", "id": "cal123"}]
    }
    mock_service.events().get().execute.return_value = fake_event
    updated_body: dict = {}

    def capture_update(**kwargs):
        updated_body.update(kwargs)
        return MagicMock(**{"execute.return_value": fake_event})

    mock_service.events().update = capture_update

    monkeypatch.setattr("t3.integrations.gcal.CredentialStore", MagicMock())
    monkeypatch.setattr("t3.integrations.gcal.build", lambda *a, **kw: mock_service)

    update_event_time("evt1", "2026-06-15T07:00:00Z")

    body = updated_body["body"]
    assert body["start"]["dateTime"] == "2026-06-15T07:00:00Z"
    # duration was 1.5 h → end must be 08:30, not 07:00
    assert body["end"]["dateTime"] != body["start"]["dateTime"]
    assert "2026-06-15T08:30:00" in body["end"]["dateTime"]


# --- integration tests ---


@pytest.mark.integration
def test_list_events_live() -> None:
    from t3.config import settings
    from t3.integrations.gcal import list_events

    if not settings.google_client_id:
        pytest.skip("GOOGLE_CLIENT_ID not set")

    events = list_events(
        time_min="2026-06-01T00:00:00Z",
        time_max="2026-06-30T23:59:59Z",
    )
    assert isinstance(events, list)


@pytest.mark.integration
def test_create_event_live() -> None:
    from t3.config import settings
    from t3.integrations.gcal import create_event

    if not settings.google_client_id:
        pytest.skip("GOOGLE_CLIENT_ID not set")

    result = create_event(
        summary="T3 test event — safe to delete",
        start="2026-06-20T08:00:00Z",
        end="2026-06-20T09:00:00Z",
    )
    assert "id" in result
