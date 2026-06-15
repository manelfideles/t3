import logging

from t3.bot import create_app
from t3.config import settings
from t3.db import init_db
from t3 import scheduler

logging.basicConfig(level=logging.INFO)


def main() -> None:
    conn = init_db(settings.database_url)
    scheduler.start(conn)
    app = create_app()
    print("T3 bot starting — press Ctrl+C to stop")
    try:
        app.run_polling()
    finally:
        scheduler.stop()


if __name__ == "__main__":
    main()
