from __future__ import annotations

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
    assert context.user_data.get("onboarding_state") is None


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
    ):
        from t3.bot import start

        update, context = _make_update()
        await start(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "already" in reply.lower() or "profile" in reply.lower()
    assert context.user_data.get("onboarding_state") is None


# ---------------------------------------------------------------------------
# /start — no upcoming races
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_stops_when_no_upcoming_races(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.intervals_api_key", "key")
    monkeypatch.setattr("t3.bot.settings.intervals_athlete_id", "i123")

    mock_repo = MagicMock()
    mock_repo.load_latest.return_value = None

    with (
        patch("t3.bot.init_db"),
        patch("t3.bot.AthleteRepo", return_value=mock_repo),
        patch("t3.bot.fetch_profile_from_intervals", return_value=_fixture_profile(upcoming=[])),
    ):
        from t3.bot import start

        update, context = _make_update()
        await start(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "race" in reply.lower()
    assert context.user_data.get("onboarding_state") is None


# ---------------------------------------------------------------------------
# /start — happy path: shows confirmation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_shows_confirmation_message_and_sets_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.intervals_api_key", "key")
    monkeypatch.setattr("t3.bot.settings.intervals_athlete_id", "i123")

    profile = _fixture_profile()
    mock_repo = MagicMock()
    mock_repo.load_latest.return_value = None

    with (
        patch("t3.bot.init_db"),
        patch("t3.bot.AthleteRepo", return_value=mock_repo),
        patch("t3.bot.fetch_profile_from_intervals", return_value=profile),
        patch("t3.bot.format_confirmation_message", return_value="*Profile:*\nFTP: 240W\nReply yes to confirm."),
    ):
        from t3.bot import start

        update, context = _make_update()
        await start(update, context)

    assert context.user_data["onboarding_state"] == "AWAITING_CONFIRMATION"
    assert context.user_data["pending_profile"] is profile
    reply = update.message.reply_text.call_args[0][0]
    assert "FTP" in reply or "Profile" in reply


# ---------------------------------------------------------------------------
# Confirmation flow — "yes" flushes and generates plan
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_confirmation_yes_flushes_and_generates_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.database_url", ":memory:")

    profile = _fixture_profile()
    update, context = _make_update("yes")
    context.user_data["onboarding_state"] = "AWAITING_CONFIRMATION"
    context.user_data["pending_profile"] = profile

    with (
        patch("t3.bot.init_db"),
        patch("t3.bot.flush_to_db") as mock_flush,
        patch("t3.tools.plan.generate_training_plan") as mock_plan,
    ):
        mock_plan.return_value = {"phases": []}
        from t3.bot import _handle_onboarding_reply

        await _handle_onboarding_reply(update, context, "yes")

    mock_flush.assert_called_once_with(profile, mock_flush.call_args[0][1])
    assert context.user_data.get("onboarding_state") is None
    assert context.user_data.get("pending_profile") is None
    calls = [c[0][0] for c in update.message.reply_text.call_args_list]
    assert any("plan" in t.lower() or "generat" in t.lower() for t in calls)


# ---------------------------------------------------------------------------
# Confirmation flow — correction text re-shows updated profile
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_correction_text_applies_and_reshows_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _fixture_profile()
    updated_profile = _fixture_profile()
    updated_profile.ftp_watts = 260

    update, context = _make_update("my FTP is actually 260")
    context.user_data["onboarding_state"] = "AWAITING_CONFIRMATION"
    context.user_data["pending_profile"] = profile

    with (
        patch("t3.bot.apply_corrections", return_value=updated_profile) as mock_apply,
        patch("t3.bot.format_confirmation_message", return_value="*Profile:*\nFTP: 260W\nReply yes."),
        patch("t3.bot._get_client", return_value=MagicMock()),
    ):
        from t3.bot import _handle_onboarding_reply

        await _handle_onboarding_reply(update, context, "my FTP is actually 260")

    mock_apply.assert_called_once()
    assert context.user_data["pending_profile"] is updated_profile
    assert context.user_data["onboarding_state"] == "AWAITING_CONFIRMATION"
    reply = update.message.reply_text.call_args[0][0]
    assert "260" in reply


# ---------------------------------------------------------------------------
# handle_message routes to onboarding when state is set
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_handle_message_routes_to_onboarding_when_awaiting_confirmation() -> None:
    profile = _fixture_profile()
    update, context = _make_update("yes")
    context.user_data["onboarding_state"] = "AWAITING_CONFIRMATION"
    context.user_data["pending_profile"] = profile

    with (
        patch("t3.bot.init_db"),
        patch("t3.bot.flush_to_db"),
        patch("t3.tools.plan.generate_training_plan", return_value={"phases": []}),
    ):
        from t3.bot import handle_message

        await handle_message(update, context)

    assert context.user_data.get("onboarding_state") is None


@pytest.mark.anyio
async def test_handle_message_routes_to_agent_when_not_onboarding() -> None:
    update, context = _make_update("How many km should I swim this week?")

    with patch("t3.bot.run", new_callable=AsyncMock, return_value="Swim 3km this week."):
        from t3.bot import handle_message

        await handle_message(update, context)

    update.message.reply_text.assert_called_once_with("Swim 3km this week.")
