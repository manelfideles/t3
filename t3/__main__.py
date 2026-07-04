from telegram.ext import Application

from t3 import scheduler
from t3.bot import create_app
from t3.config import settings

# logging.basicConfig(level="INFO")


def main() -> None:
    async def on_startup(app: Application) -> None:
        async def _notify(chat_id: int, text: str) -> None:
            await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

        scheduler.start(settings.database_url, _notify)

    async def on_shutdown(app: Application) -> None:
        scheduler.stop()

    app = create_app()
    app.post_init = on_startup
    app.post_shutdown = on_shutdown

    print("T3 bot starting — press Ctrl+C to stop")
    app.run_polling()


if __name__ == "__main__":
    main()
