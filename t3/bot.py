import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from t3.config import settings

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hello, I'm T3 — your triathlon training agent.")


async def connect_gcal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from t3 import gcal

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


def create_app() -> Application:
    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect_gcal", connect_gcal))
    return app
