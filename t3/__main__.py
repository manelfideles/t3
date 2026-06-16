import logging

from telegram.ext import Application

from t3.bot import create_app
from t3.config import settings
from t3.db import init_db
from t3 import scheduler

logging.basicConfig(level=logging.INFO)


def main() -> None:
    conn = init_db(settings.database_url)

    async def on_startup(app: Application) -> None:
        scheduler.start(conn)

    async def on_shutdown(app: Application) -> None:
        scheduler.stop()

    app = create_app()
    app.post_init = on_startup
    app.post_shutdown = on_shutdown

    print("T3 bot starting — press Ctrl+C to stop")
    app.run_polling()


if __name__ == "__main__":
    main()
