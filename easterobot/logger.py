import logging
import logging.handlers
import sys
from pathlib import Path

logger_discord = logging.getLogger("discord")
logger_discord.setLevel(logging.INFO)
logging.getLogger("discord.http").setLevel(logging.INFO)

HERE = Path(__file__).parent
LOG_DIR = HERE / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

file_handler = logging.handlers.RotatingFileHandler(
    filename=LOG_DIR / "easterobot.log",
    encoding="utf-8",
    maxBytes=1 << 16,
    backupCount=10,  # Rotate through 10 files
)
stdout_handler = logging.StreamHandler(sys.stdout)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(
    "[{asctime}] [{levelname}] [{name}]: {message}", DATE_FORMAT, style="{"
)
file_handler.setFormatter(formatter)
stdout_handler.setFormatter(formatter)
logger_discord.addHandler(file_handler)
logger_discord.addHandler(stdout_handler)

logger = logging.getLogger("easterobot")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(stdout_handler)
