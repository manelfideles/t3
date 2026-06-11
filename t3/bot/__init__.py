import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from t3.agent import build_client, run
from t3.config import settings

logger = logging.getLogger(__name__)

_client = build_client()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hello, I'm T3 — your triathlon training agent.")


async def connect_gcal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from t3.integrations import gcal

    await update.message.reply_text(
        "Starting Google Calendar authorization.\n"
        "A link is coming — click it, approve access, then come back here."
    )

    async def send_url(url: str) -> None:
        await update.message.reply_text(
            f"Authorize here (link expires in 5 min):\n{url}"
        )

    try:
        await gcal.run_oauth_flow(send_url)
        await update.message.reply_text("Google Calendar connected.")
    except asyncio.TimeoutError:
        await update.message.reply_text("Timed out. Send /connect_gcal to try again.")
    except Exception as exc:
        logger.exception("GCal OAuth error")
        await update.message.reply_text(f"Error: {exc}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text or ""
    try:
        reply = await run(user_text, _client)
        await update.message.reply_text(reply or "I didn't get a response. Try again.")
    except Exception as exc:
        logger.exception("Agent error")
        msg = str(exc)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            await update.message.reply_text(
                "Gemini API rate limit hit. Wait a minute and try again, or check your quota at aistudio.google.com."
            )
        elif "503" in msg or "UNAVAILABLE" in msg:
            await update.message.reply_text(
                "Gemini is overloaded right now. Try again in a few seconds."
            )
        else:
            await update.message.reply_text(f"Something went wrong: {exc}")


def create_app() -> Application:
    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect_gcal", connect_gcal))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
