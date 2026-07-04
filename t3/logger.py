import logging
import os

from dotenv import load_dotenv

load_dotenv()


logger = logging.getLogger("t3")
log_level_str = os.getenv("LOG_LEVEL", "INFO")
log_level = getattr(logging, log_level_str.upper(), logging.INFO)
logger.setLevel(log_level)

if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
