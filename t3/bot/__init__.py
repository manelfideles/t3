import asyncio
import json
import logging

from google import genai
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from t3.bot.conversation import handle_turn
from t3.bot.onboarding import (
    fetch_profile_from_intervals,
    flush_to_db,
    format_confirmation_message,
)
from t3.config import settings
from t3.db import AthleteRepo, ConversationState, ConversationStateRepo, SyncStateRepo, init_db

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        from t3.agent import build_client as _build

        _client = _build()
    return _client


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    message = update.message

    if not settings.intervals_api_key or not settings.intervals_athlete_id:
        await message.reply_text(
            "Intervals.icu credentials are not configured. "
            "Please set INTERVALS_API_KEY and INTERVALS_ATHLETE_ID and restart."
        )
        return

    conn = init_db(settings.database_url)
    SyncStateRepo(conn).set_telegram_chat_id(message.chat_id)

    if AthleteRepo(conn).load_latest() is not None:
        await message.reply_text(
            "You already have a profile on file. Your training plan is ready — just ask me anything!"
        )
        return

    try:
        profile = fetch_profile_from_intervals()
    except Exception as exc:
        logger.exception("Failed to fetch Intervals.icu data")
        await message.reply_text(f"Could not fetch your Intervals.icu data: {exc}")
        return

    payload_json = json.dumps(profile.__dict__)
    ConversationStateRepo(conn).save(
        message.chat_id,
        ConversationState.ONBOARDING_AWAITING_CONFIRMATION,
        payload_json,
    )
    await message.reply_text(format_confirmation_message(profile), parse_mode="Markdown")


async def connect_gcal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    message = update.message
    from t3.integrations import gcal

    await message.reply_text(
        "Starting Google Calendar authorization.\nA link is coming — click it, approve access, then come back here."
    )

    async def send_url(url: str) -> None:
        await message.reply_text(f"Authorize here (link expires in 5 min):\n{url}")

    try:
        await gcal.run_oauth_flow(send_url)
        await message.reply_text("Google Calendar connected.")
    except asyncio.TimeoutError:
        await message.reply_text("Timed out. Send /connect_gcal to try again.")
    except Exception as exc:
        logger.exception("GCal OAuth error")
        await message.reply_text(f"Error: {exc}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    user_text = update.message.text or ""
    chat_id = update.message.chat_id

    conn = init_db(settings.database_url)
    reply = await handle_turn(chat_id, user_text, conn, _get_client())
    await update.message.reply_text(reply)


def create_app() -> Application:
    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect_gcal", connect_gcal))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
