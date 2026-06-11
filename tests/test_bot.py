from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import Application, CommandHandler


def test_create_app_returns_application(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.telegram_token", "fake-token-for-test")
    from t3.bot import create_app

    app = create_app()
    assert isinstance(app, Application)


def test_create_app_has_start_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("t3.bot.settings.telegram_token", "fake-token-for-test")
    from t3.bot import create_app

    app = create_app()
    handlers = app.handlers.get(0, [])
    command_handlers = [h for h in handlers if isinstance(h, CommandHandler)]
    commands = {cmd for h in command_handlers for cmd in h.commands}
    assert "start" in commands


@pytest.mark.anyio
async def test_start_handler_replies_with_greeting() -> None:
    from t3.bot import start

    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await start(update, context)

    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "T3" in reply_text
