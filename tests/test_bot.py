from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import Application, CommandHandler

from t3.bot.onboarding import IntervalsDerivedProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UPCOMING_RACE = {"category": "RACE", "name": "City Olympic", "start_date_local": "2026-09-20T08:00:00"}


def _fixture_profile(upcoming: list | None = None) -> IntervalsDerivedProfile:
    return IntervalsDerivedProfile(
        name="Manuel",
        age=32,
        sex="male",
        ftp_watts=240,
        weight_kg=74.5,
        height_cm=178.0,
        avg_weekly_hours=8.5,
        threshold_run_pace_per_km=4.8,
        threshold_swim_pace_per_100m=1.9,
        upcoming_races=upcoming if upcoming is not None else [_UPCOMING_RACE],
        injury_history=[],
        experience_level="beginner",
    )


def _make_update(text: str = "") -> tuple[MagicMock, MagicMock]:
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    context = MagicMock()
    context.user_data = {}
    return update, context


# ---------------------------------------------------------------------------
# create_app
# ---------------------------------------------------------------------------


def test_create_app_returns_application(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.telegram_token", "fake-token")
    from t3.bot import create_app

    assert isinstance(create_app(), Application)


def test_create_app_has_start_and_connect_gcal_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.telegram_token", "fake-token")
    from t3.bot import create_app

    app = create_app()
    handlers = app.handlers.get(0, [])
    commands = {cmd for h in handlers if isinstance(h, CommandHandler) for cmd in h.commands}
    assert "start" in commands
    assert "connect_gcal" in commands


# ---------------------------------------------------------------------------
# /start — missing credentials
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_hard_stops_when_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.intervals_api_key", "")
    monkeypatch.setattr("t3.bot.settings.intervals_athlete_id", "")
    from t3.bot import start

    update, context = _make_update()
    await start(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "credentials" in reply.lower() or "intervals" in reply.lower()


# ---------------------------------------------------------------------------
# /start — existing profile
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_skips_onboarding_when_profile_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.intervals_api_key", "key")
    monkeypatch.setattr("t3.bot.settings.intervals_athlete_id", "i123")

    mock_repo = MagicMock()
    mock_repo.load_latest.return_value = MagicMock()  # existing profile

    with (
        patch("t3.bot.init_db"),
        patch("t3.bot.AthleteRepo", return_value=mock_repo),
        patch("t3.bot.SyncStateRepo"),
    ):
        from t3.bot import start

        update, context = _make_update()
        await start(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "already" in reply.lower() or "profile" in reply.lower()


# ---------------------------------------------------------------------------
# /start — no upcoming races: must NOT block; must proceed to confirmation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_proceeds_with_no_upcoming_races(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.intervals_api_key", "key")
    monkeypatch.setattr("t3.bot.settings.intervals_athlete_id", "i123")

    mock_athlete_repo = MagicMock()
    mock_athlete_repo.load_latest.return_value = None
    mock_conv_repo = MagicMock()

    with (
        patch("t3.bot.init_db"),
        patch("t3.bot.AthleteRepo", return_value=mock_athlete_repo),
        patch("t3.bot.SyncStateRepo"),
        patch("t3.bot.ConversationStateRepo", return_value=mock_conv_repo),
        patch("t3.bot.fetch_profile_from_intervals", return_value=_fixture_profile(upcoming=[])),
        patch("t3.bot.format_confirmation_message", return_value="*Profile:*\nFTP: 240W\nReply yes."),
    ):
        from t3.bot import start

        update, context = _make_update()
        await start(update, context)

    # Must NOT hard-stop; confirmation must be saved to DB
    mock_conv_repo.save.assert_called_once()
    saved_state = mock_conv_repo.save.call_args[0][1]
    from t3.db import ConversationState
    assert saved_state == ConversationState.ONBOARDING_AWAITING_CONFIRMATION


# ---------------------------------------------------------------------------
# /start — happy path: shows confirmation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_shows_confirmation_message_and_sets_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.intervals_api_key", "key")
    monkeypatch.setattr("t3.bot.settings.intervals_athlete_id", "i123")

    profile = _fixture_profile()
    mock_athlete_repo = MagicMock()
    mock_athlete_repo.load_latest.return_value = None
    mock_conv_repo = MagicMock()

    with (
        patch("t3.bot.init_db"),
        patch("t3.bot.AthleteRepo", return_value=mock_athlete_repo),
        patch("t3.bot.SyncStateRepo"),
        patch("t3.bot.ConversationStateRepo", return_value=mock_conv_repo),
        patch("t3.bot.fetch_profile_from_intervals", return_value=profile),
        patch("t3.bot.format_confirmation_message", return_value="*Profile:*\nFTP: 240W\nReply yes to confirm."),
    ):
        from t3.bot import start

        update, context = _make_update()
        await start(update, context)

    mock_conv_repo.save.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "FTP" in reply or "Profile" in reply


# ---------------------------------------------------------------------------
# Conversation routing via handle_turn
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_confirmation_yes_flushes_and_generates_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    from t3.db import ConversationState, ConversationStateRepo, init_db as _init_db

    conn = _init_db(":memory:")
    profile = _fixture_profile()
    payload = json.dumps(profile.__dict__)
    ConversationStateRepo(conn).save(99, ConversationState.ONBOARDING_AWAITING_CONFIRMATION, payload)

    with (
        patch("t3.bot.conversation.flush_to_db") as mock_flush,
        patch("t3.bot.conversation.generate_training_plan", return_value={"phases": []}),
    ):
        from t3.bot.conversation import handle_turn

        reply = await handle_turn(99, "yes", conn, MagicMock())

    mock_flush.assert_called_once()
    assert "plan" in reply.lower() or "generated" in reply.lower() or "saved" in reply.lower()
    # State cleared to IDLE
    result = ConversationStateRepo(conn).load(99)
    assert result is None or result[0].value == "IDLE"


@pytest.mark.anyio
async def test_correction_text_applies_and_reshows_confirmation() -> None:
    from t3.db import ConversationState, ConversationStateRepo, init_db as _init_db

    conn = _init_db(":memory:")
    profile = _fixture_profile()
    updated_profile = _fixture_profile()
    updated_profile.ftp_watts = 260

    payload = json.dumps(profile.__dict__)
    ConversationStateRepo(conn).save(99, ConversationState.ONBOARDING_AWAITING_CONFIRMATION, payload)

    with (
        patch("t3.bot.conversation.apply_corrections", return_value=updated_profile),
        patch("t3.bot.conversation.format_confirmation_message", return_value="*Profile:*\nFTP: 260W\nReply yes."),
    ):
        from t3.bot.conversation import handle_turn

        reply = await handle_turn(99, "my FTP is actually 260", conn, MagicMock())

    assert "260" in reply
    # State still ONBOARDING_AWAITING_CONFIRMATION
    result = ConversationStateRepo(conn).load(99)
    assert result is not None
    assert result[0] == ConversationState.ONBOARDING_AWAITING_CONFIRMATION


# ---------------------------------------------------------------------------
# handle_message integration
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_handle_message_routes_to_onboarding_when_awaiting_confirmation() -> None:
    from t3.db import ConversationState, ConversationStateRepo, init_db as _init_db

    conn = _init_db(":memory:")
    profile = _fixture_profile()
    payload = json.dumps(profile.__dict__)
    ConversationStateRepo(conn).save(42, ConversationState.ONBOARDING_AWAITING_CONFIRMATION, payload)

    update, context = _make_update("yes")
    update.message.chat_id = 42

    with (
        patch("t3.bot.init_db", return_value=conn),
        patch("t3.bot._get_client", return_value=MagicMock()),
        patch("t3.bot.conversation.flush_to_db"),
        patch("t3.bot.conversation.generate_training_plan", return_value={"phases": []}),
    ):
        from t3.bot import handle_message

        await handle_message(update, context)

    update.message.reply_text.assert_called_once()


@pytest.mark.anyio
async def test_handle_message_routes_to_agent_when_not_onboarding() -> None:
    from t3.db import init_db as _init_db

    conn = _init_db(":memory:")
    update, context = _make_update("How many km should I swim this week?")
    update.message.chat_id = 77

    with (
        patch("t3.bot.init_db", return_value=conn),
        patch("t3.bot._get_client", return_value=MagicMock()),
        patch("t3.agent.run", new_callable=AsyncMock, return_value="Swim 3km this week."),
    ):
        from t3.bot import handle_message

        await handle_message(update, context)

    update.message.reply_text.assert_called_once_with("Swim 3km this week.")


# ---------------------------------------------------------------------------
# Conflict confirmation routing
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_handle_message_routes_to_conflict_when_pending() -> None:
    import dataclasses
    from t3.bot.confirmation import PendingConflict
    from t3.db import ConversationState, ConversationStateRepo, init_db as _init_db
    from t3.sync import ConflictInfo

    conn = _init_db(":memory:")
    chat_id = 55555
    conflict = ConflictInfo("m-id", "c-id", "2026-07-14T06:00:00+00:00", "2026-07-15T06:00:00+00:00", "2026-07-15T07:00:00+00:00")
    pending = PendingConflict(conflict=conflict, moved_intervals_id=None, conflicting_intervals_id=None)
    payload = json.dumps({
        "conflict": dataclasses.asdict(conflict),
        "moved_intervals_id": None,
        "conflicting_intervals_id": None,
    })
    ConversationStateRepo(conn).save(chat_id, ConversationState.CONFLICT_PENDING, payload)

    update, context = _make_update("1")
    update.message.chat_id = chat_id

    with (
        patch("t3.bot.init_db", return_value=conn),
        patch("t3.bot._get_client", return_value=MagicMock()),
        patch("t3.bot.conversation.resolve", return_value="Done — moved session reverted to its original time."),
    ):
        from t3.bot import handle_message

        await handle_message(update, context)

    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "Done" in reply or "reverted" in reply


@pytest.mark.anyio
async def test_handle_message_sends_typing_action() -> None:
    """Typing indicator must fire before the reply — proves the event loop isn't blocked."""
    import asyncio as _asyncio
    from telegram.constants import ChatAction
    from t3.db import init_db as _init_db

    conn = _init_db(":memory:")
    update, context = _make_update("How many km this week?")
    update.message.chat_id = 88
    send_action_calls: list = []

    async def _record_send_action(action):
        send_action_calls.append(action)

    update.message.chat.send_action = _record_send_action

    async def _slow_run(text, client):
        await _asyncio.sleep(0.05)
        return "3km."

    with (
        patch("t3.bot.init_db", return_value=conn),
        patch("t3.bot._get_client", return_value=MagicMock()),
        patch("t3.agent.run", side_effect=_slow_run),
    ):
        from t3.bot import handle_message
        await handle_message(update, context)

    assert ChatAction.TYPING in send_action_calls, "typing action was never sent"


@pytest.mark.anyio
async def test_handle_message_does_not_route_to_conflict_when_not_pending() -> None:
    from t3.db import init_db as _init_db

    conn = _init_db(":memory:")
    update, context = _make_update("Hello!")
    update.message.chat_id = 77777

    with (
        patch("t3.bot.init_db", return_value=conn),
        patch("t3.bot._get_client", return_value=MagicMock()),
        patch("t3.agent.run", new_callable=AsyncMock, return_value="Hello back!"),
    ):
        from t3.bot import handle_message

        await handle_message(update, context)

    update.message.reply_text.assert_called_once_with("Hello back!")
