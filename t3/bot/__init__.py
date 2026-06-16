import asyncio
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

from t3.agent import run
from t3.bot.onboarding import (
    apply_corrections,
    fetch_profile_from_intervals,
    flush_to_db,
    format_confirmation_message,
)
from t3.config import settings
from t3.db import AthleteRepo, init_db

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

_CONFIRMATION_WORDS = frozenset({"yes", "y", "confirm", "ok", "yep", "sure"})


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
    from t3.db import SyncStateRepo as _SyncStateRepo

    _SyncStateRepo(conn).set_telegram_chat_id(message.chat_id)
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

    if context.user_data is None:
        return
    context.user_data["pending_profile"] = profile
    context.user_data["onboarding_state"] = "AWAITING_CONFIRMATION"
    await message.reply_text(format_confirmation_message(profile), parse_mode="Markdown")


async def _handle_onboarding_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_text: str,
) -> None:
    message = update.message
    if message is None or context.user_data is None:
        return

    pending_profile = context.user_data.get("pending_profile")
    if pending_profile is None:
        context.user_data.pop("onboarding_state", None)
        return

    if user_text.strip().lower() in _CONFIRMATION_WORDS:
        conn = init_db(settings.database_url)
        flush_to_db(pending_profile, conn)
        context.user_data.pop("pending_profile", None)
        context.user_data.pop("onboarding_state", None)
        await message.reply_text("Profile saved! Generating your training plan now...")
        try:
            from t3.tools.plan import generate_training_plan

            generate_training_plan()
            await message.reply_text("Your training plan has been generated. Ask me anything to get started!")
        except Exception as exc:
            logger.exception("Plan generation error after onboarding")
            await message.reply_text(f"Profile saved, but plan generation failed: {exc}")
    else:
        try:
            updated = apply_corrections(pending_profile, user_text, _get_client())
            context.user_data["pending_profile"] = updated
            await message.reply_text(format_confirmation_message(updated), parse_mode="Markdown")
        except Exception as exc:
            logger.exception("Correction parsing error")
            await message.reply_text(f"Couldn't apply that correction: {exc}. Please try again.")


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

    if context.user_data is not None and context.user_data.get("onboarding_state") == "AWAITING_CONFIRMATION":
        await _handle_onboarding_reply(update, context, user_text)
        return

    try:
        reply = await run(user_text, _get_client())
        await update.message.reply_text(reply or "I didn't get a response. Try again.")
    except Exception as exc:
        logger.exception("Agent error")
        msg = str(exc)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            await update.message.reply_text(
                "Gemini API rate limit hit. Wait a minute and try again, or check your quota at aistudio.google.com."
            )
        elif "503" in msg or "UNAVAILABLE" in msg:
            await update.message.reply_text("Gemini is overloaded right now. Try again in a few seconds.")
        else:
            await update.message.reply_text(f"Something went wrong: {exc}")


def create_app() -> Application:
    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect_gcal", connect_gcal))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
