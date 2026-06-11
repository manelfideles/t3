import logging

from t3.bot import create_app

logging.basicConfig(level=logging.INFO)


def main() -> None:
    app = create_app()
    print("T3 bot starting — press Ctrl+C to stop")
    app.run_polling()


if __name__ == "__main__":
    main()
