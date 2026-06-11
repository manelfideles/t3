import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from t3.config import settings

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hello, I'm T3 — your triathlon training agent.")


def create_app() -> Application:
    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    return app
